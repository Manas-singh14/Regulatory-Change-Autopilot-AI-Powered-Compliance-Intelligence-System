import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import asyncio
import httpx
from rich.console import Console
from rich.panel import Panel

from src.watcher.scrapers import RBIScraper
from src.watcher.extractor import extract_pdf_text
from src.watcher.database import init_db, upsert_circular, make_circular_id
from src.watcher.models import Circular
from src.rag.ingestor import ingest_pending, search

console = Console()


async def fetch_with_text(limit: int = 3):
    """Grab RBI circulars — follow detail page to find the real PDF URL."""
    scraper = RBIScraper()
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (research bot)"}
    ) as client:
        results = await scraper.scrape(client)
        saved = 0

        for r in results:
            if saved >= limit:
                break

            pdf_url = None

            # Case 1 — already a direct PDF link
            if r.url.lower().endswith(".pdf"):
                pdf_url = r.url

            # Case 2 — RBI detail page, scrape it to find PDF link
            else:
                try:
                    resp = await client.get(r.url, timeout=15)
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if ".pdf" in href.lower():
                            from urllib.parse import urljoin
                            pdf_url = urljoin("https://www.rbi.org.in", href)
                            break
                except Exception as e:
                    console.print(f"[red]Could not fetch detail page: {e}[/red]")
                    continue

            if not pdf_url:
                continue

            text = await extract_pdf_text(client, pdf_url)
            if not text:
                continue

            cid = make_circular_id(r.url)
            c = Circular(
                id=cid, regulator=r.regulator,
                title=r.title, url=pdf_url,
                date_issued=r.date_issued,
                circular_no=r.circular_no,
                text_content=text,
            )
            if upsert_circular(c):
                console.print(f"[green]✓[/green] Saved: {r.title[:60]}")
                saved += 1

        return saved

def main():
    console.print("\n[bold green]Phase 1 Step 2 — Embedding Test[/bold green]\n")

    init_db()

    # Step 1: fetch circulars WITH text
    console.print("[yellow]Fetching 3 RBI PDFs with text...[/yellow]")
    saved = asyncio.run(fetch_with_text(limit=3))
    console.print(f"[green]✓[/green] {saved} circulars with text saved\n")

    # Step 2: embed into Qdrant
    console.print("[yellow]Embedding into Qdrant (downloading model on first run ~80MB)...[/yellow]")
    count = ingest_pending()
    console.print(f"[green]✓[/green] Ingested {count} circulars\n")

    # Step 3: test semantic search
    console.print("[yellow]Testing semantic search...[/yellow]\n")
    queries = [
        "KYC norms for banks",
        "interest rate guidelines",
        "capital adequacy requirements",
    ]
    for q in queries:
        results = search(q, top_k=2)
        console.print(f"[bold]Query:[/bold] {q}")
        for r in results:
            console.print(Panel(
                f"[cyan]{r['title'][:70]}[/cyan]\n"
                f"Score: {r['score']} | {r['date_issued'] or 'no date'}\n\n"
                f"{r['chunk_text'][:200]}...",
                expand=False
            ))
        console.print()

    console.print("[bold green]Phase 1 Step 2 complete![/bold green]")
    console.print("Next: Gap analysis LLM chain with Groq\n")


if __name__ == "__main__":
    main()