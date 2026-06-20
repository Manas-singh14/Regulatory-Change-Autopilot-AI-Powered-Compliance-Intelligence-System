import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import httpx
from rich.console import Console
from rich.table import Table

from src.watcher.scrapers import RBIScraper
from src.watcher.extractor import extract_pdf_text
from src.watcher.database import init_db, upsert_circular, make_circular_id
from src.watcher.models import Circular

console = Console()


async def main():
    console.print("\n[bold green]Regulatory Watcher — Test Run[/bold green]\n")

    init_db()
    console.print("[green]✓[/green] Database initialized")

    scraper = RBIScraper()
    console.print("\n[yellow]Scraping RBI...[/yellow]")

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (research bot)"}
    ) as client:
        results = await scraper.scrape(client)

        if not results:
            console.print("[red]No results — RBI site may have changed layout[/red]")
            return

        table = Table(title=f"RBI — {len(results)} items found")
        table.add_column("Title", style="cyan", max_width=50)
        table.add_column("Date", style="magenta")
        table.add_column("URL", style="dim", max_width=40)

        for r in results[:10]:
            table.add_row(
                r.title[:50],
                r.date_issued or "—",
                r.url[:40],
            )
        console.print(table)

        # Save first 5 to DB
        saved = 0
        for r in results[:5]:
            cid = make_circular_id(r.url)
            c = Circular(
                id=cid, regulator=r.regulator,
                title=r.title, url=r.url,
                date_issued=r.date_issued,
                circular_no=r.circular_no,
            )
            if upsert_circular(c):
                saved += 1

        console.print(f"\n[green]✓[/green] Saved {saved} new circulars to DB")
        console.print("\n[bold green]Phase 1 Step 1 complete![/bold green]")


if __name__ == "__main__":
    asyncio.run(main())