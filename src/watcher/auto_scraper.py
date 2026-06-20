"""
Regulatory Change Autopilot — AI-Powered Compliance Intelligence System
Auto Scraper: RSS Feed detection + Playwright PDF download.

Strategy:
  1. Poll RBI RSS feed (no Cloudflare block) to detect new circulars
  2. Use Playwright (real browser) to bypass Cloudflare and download PDFs
  3. Auto-ingest into vector store

Run standalone: python -m src.watcher.auto_scraper
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from src.watcher.database import init_db, make_circular_id, upsert_circular
from src.watcher.extractor import _extract_text_from_bytes
from src.watcher.models import Circular

load_dotenv()
logger = logging.getLogger("autopilot.auto_scraper")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RBI_RSS_FEEDS = [
    "https://www.rbi.org.in/scripts/rss.aspx",
]

PDF_DOWNLOAD_DIR = Path(
    os.getenv("PDF_DIR", "./data/circulars/pdfs/auto")
)


# ---------------------------------------------------------------------------
# Step 1 — RSS Feed Parser (no Cloudflare, always works)
# ---------------------------------------------------------------------------

# Real RBI circular index URL — Playwright will scrape this
RBI_CIRCULAR_INDEX = "https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx"


async def fetch_rss_items(url: str) -> list[dict]:
    """
    Use Playwright to scrape RBI circular index page.
    Returns list of {title, link, pub_date, desc}
    """
    items = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            logger.info(f"Playwright: fetching circular index...")
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Extract all circular rows from the table
            rows = await page.eval_on_selector_all(
                "table tr",
                """rows => rows.map(row => {
                    const link = row.querySelector('a');
                    const cells = row.querySelectorAll('td');
                    if (!link) return null;
                    return {
                        title: link.innerText.trim(),
                        link: link.href,
                        pub_date: cells.length > 1 ? cells[1].innerText.trim() : '',
                        desc: ''
                    };
                }).filter(r => r && r.title && r.link)
                """
            )

            items = [r for r in rows if r and r.get("link", "").startswith("http")]
            logger.info(f"Playwright: found {len(items)} circulars on index page")
            await browser.close()

    except Exception as e:
        logger.error(f"Playwright scrape error: {e}")

    return items


async def get_new_rss_circulars() -> list[dict]:
    """
    Scrape RBI circular index and return only
    items not yet in the database.
    """
    import sqlite3
    from src.watcher.database import get_db_path

    all_items = await fetch_rss_items(RBI_CIRCULAR_INDEX)

    if not all_items:
        return []

    # Filter out already-stored circulars
    con = sqlite3.connect(get_db_path())
    new_items = []
    for item in all_items:
        cid = make_circular_id(item["link"])
        exists = con.execute(
            "SELECT id FROM circulars WHERE id = ?", (cid,)
        ).fetchone()
        if not exists:
            new_items.append(item)
    con.close()

    logger.info(f"New circulars not in DB: {len(new_items)}")
    return new_items


# ---------------------------------------------------------------------------
# Step 2 — Playwright PDF Downloader (bypasses Cloudflare)
# ---------------------------------------------------------------------------

async def find_and_download_pdf(
    page_url: str,
    save_dir: Path,
) -> bytes | None:
    """
    Use a real Playwright browser to:
    1. Open the circular detail page (bypasses Cloudflare JS challenge)
    2. Find the PDF link on the page
    3. Download the PDF bytes

    Returns raw PDF bytes or None if not found.
    """
    save_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = await context.new_page()
        pdf_bytes = None

        try:
            logger.info(f"Playwright: opening {page_url}")
            await page.goto(page_url, wait_until="networkidle", timeout=30000)

            # Find PDF links on the page
            pdf_links = await page.eval_on_selector_all(
                "a[href]",
                """els => els
                    .map(e => e.href)
                    .filter(h => h.toLowerCase().includes('.pdf'))
                """,
            )

            # Also check iframes
            if not pdf_links:
                for frame in page.frames:
                    try:
                        frame_links = await frame.eval_on_selector_all(
                            "a[href]",
                            "els => els.map(e=>e.href).filter(h=>h.includes('.pdf'))",
                        )
                        pdf_links.extend(frame_links)
                    except Exception:
                        pass

            if not pdf_links:
                logger.warning(f"No PDF links found on {page_url}")
                return None

            pdf_url = pdf_links[0]
            logger.info(f"Playwright: found PDF → {pdf_url}")

            # Download using the same browser session (bypasses auth/cookies)
            response = await page.request.get(pdf_url)
            pdf_bytes = await response.body()

            if len(pdf_bytes) < 1000:
                logger.warning("Downloaded file too small — likely not a PDF")
                pdf_bytes = None

        except Exception as e:
            logger.error(f"Playwright error on {page_url}: {e}")
        finally:
            await browser.close()

        return pdf_bytes


# ---------------------------------------------------------------------------
# Step 3 — Full Auto Pipeline
# ---------------------------------------------------------------------------

async def run_auto_pipeline(max_new: int = 5) -> dict:
    """
    Full automated pipeline:
    RSS detect → Playwright download → text extract → DB save → embed

    Always returns a consistent dict with these keys:
      status, timestamp, rss_items_found, processed, failed, circulars, errors
    """
    init_db()
    PDF_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 50)
    logger.info("Regulatory Change Autopilot — Auto Scraper Starting")
    logger.info("=" * 50)

    # Step 1: Detect new circulars via RSS
    logger.info("Step 1: Checking RSS feeds...")
    new_items = await get_new_rss_circulars()

    # Always return consistent keys — even when nothing is found
    if not new_items:
        logger.info("No new circulars found — system is up to date")
        return {
            "status":          "up_to_date",
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "rss_items_found": 0,
            "processed":       0,
            "failed":          0,
            "circulars":       [],
            "errors":          [],
        }

    logger.info(f"Found {len(new_items)} new items — processing up to {max_new}")
    new_items = new_items[:max_new]

    # Step 2: Download PDFs via Playwright
    processed: list[dict] = []
    failed: list[dict]    = []

    for item in new_items:
        logger.info(f"Processing: {item['title'][:60]}")

        # Extract circular number from title/description
        circular_no = None
        match = re.search(
            r"RBI[/\s][0-9]{4}-[0-9]{2,4}[/\s][0-9]+",
            item["title"] + " " + item["desc"],
        )
        if match:
            circular_no = match.group().replace(" ", "/")

        # Download PDF via Playwright (real browser, bypasses Cloudflare)
        pdf_bytes = await find_and_download_pdf(
            page_url=item["link"],
            save_dir=PDF_DOWNLOAD_DIR,
        )

        if not pdf_bytes:
            logger.warning(f"Skipping — no PDF found: {item['title'][:50]}")
            failed.append({"title": item["title"], "reason": "no_pdf"})
            continue

        # Extract text from PDF bytes
        text = _extract_text_from_bytes(pdf_bytes)
        if not text:
            logger.warning(f"Skipping — text extraction failed: {item['title'][:50]}")
            failed.append({"title": item["title"], "reason": "no_text"})
            continue

        # Save circular to SQLite
        cid = make_circular_id(item["link"])
        circular = Circular(
            id=cid,
            regulator="RBI",
            title=item["title"],
            url=item["link"],
            date_issued=item.get("pub_date"),
            circular_no=circular_no,
            text_content=text,
        )

        if upsert_circular(circular):
            # Save PDF backup to disk
            safe_name = re.sub(r"[^\w\-]", "_", item["title"][:50])
            pdf_path = PDF_DOWNLOAD_DIR / f"{safe_name}.pdf"
            pdf_path.write_bytes(pdf_bytes)

            processed.append({
                "id":          cid,
                "title":       item["title"][:80],
                "circular_no": circular_no,
                "date_issued": item.get("pub_date"),
                "chars":       len(text),
                "pdf_saved":   str(pdf_path),
            })
            logger.info(f"✓ Saved: {item['title'][:60]} ({len(text)} chars)")

    # Step 3: Embed all new circulars into Qdrant
    if processed:
        logger.info(f"Step 3: Embedding {len(processed)} circulars into Qdrant...")
        from src.rag.ingestor import ingest_pending
        ingested = ingest_pending()
        logger.info(f"Embedded {ingested} circulars")

    summary = {
        "status":          "complete",
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "rss_items_found": len(new_items),
        "processed":       len(processed),
        "failed":          len(failed),
        "circulars":       processed,
        "errors":          failed,
    }

    logger.info(f"Pipeline complete — processed: {len(processed)} | failed: {len(failed)}")
    return summary


# ---------------------------------------------------------------------------
# Scheduler — runs every 30 minutes automatically
# ---------------------------------------------------------------------------

async def run_scheduler(interval_minutes: int = 30) -> None:
    """
    Keeps the auto pipeline running on a schedule.
    Run with: python -m src.watcher.auto_scraper --schedule
    """
    from rich.console import Console
    console = Console()

    console.print(
        f"\n[bold green]Regulatory Change Autopilot[/bold green] "
        f"[dim]scheduler started — checking every {interval_minutes} mins[/dim]\n"
    )

    while True:
        console.print(
            f"[yellow]{datetime.now().strftime('%H:%M:%S')}[/yellow] "
            f"Running auto pipeline..."
        )
        try:
            result = await run_auto_pipeline(max_new=5)
            if result["processed"] > 0:
                console.print(
                    f"[green]✓ {result['processed']} new circulars processed[/green]"
                )
                for c in result["circulars"]:
                    console.print(f"  [cyan]{c['title'][:70]}[/cyan]")
            else:
                console.print("[dim]  No new circulars — system up to date[/dim]")
        except Exception as e:
            console.print(f"[red]Pipeline error: {e}[/red]")

        console.print(
            f"[dim]Next check in {interval_minutes} minutes...[/dim]\n"
        )
        await asyncio.sleep(interval_minutes * 60)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json
    logging.basicConfig(level=logging.INFO)

    if "--schedule" in sys.argv:
        asyncio.run(run_scheduler(interval_minutes=30))
    else:
        result = asyncio.run(run_auto_pipeline(max_new=3))
        print(json.dumps(result, indent=2))