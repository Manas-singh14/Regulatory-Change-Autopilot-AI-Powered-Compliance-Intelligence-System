"""
Test the full auto scraper pipeline.
Regulatory Change Autopilot — AI-Powered Compliance Intelligence System

Run: python tests/test_auto_scraper.py
"""

import sys, os, asyncio, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from src.watcher.auto_scraper import (
    get_new_rss_circulars,
    find_and_download_pdf,
    run_auto_pipeline,
)
from src.watcher.database import init_db

console = Console()


async def main():
    console.print(
        "\n[bold green]Regulatory Change Autopilot[/bold green] "
        "[dim]— AI-Powered Compliance Intelligence System[/dim]\n"
    )

    init_db()

    # ---------------------------------------------------------------
    # Test 1: RSS Feed
    # ---------------------------------------------------------------
    console.print(Rule("[yellow]Test 1: RSS Feed Detection[/yellow]"))
    console.print("[dim]Checking RBI RSS feed for new circulars...[/dim]\n")

    new_items = await get_new_rss_circulars()

    if new_items:
        console.print(f"[green]✓ {len(new_items)} new circulars detected via RSS[/green]\n")
        for item in new_items[:5]:
            console.print(
                f"  [cyan]{item['title'][:70]}[/cyan]\n"
                f"  [dim]{item['pub_date']} | {item['link'][:60]}[/dim]\n"
            )
    else:
        console.print("[dim]No new circulars in RSS (all already in DB)[/dim]\n")

    # ---------------------------------------------------------------
    # Test 2: Full auto pipeline
    # ---------------------------------------------------------------
    console.print(Rule("[yellow]Test 2: Full Auto Pipeline[/yellow]"))
    console.print(
        "[dim]RSS detect → Playwright download → "
        "extract → embed...[/dim]\n"
    )

    result = await run_auto_pipeline(max_new=2)

    console.print(Panel(
        f"[bold]Pipeline Complete[/bold]\n\n"
        f"RSS items found : {result['rss_items_found']}\n"
        f"Processed       : {result['processed']}\n"
        f"Failed          : {result['failed']}\n"
        f"Timestamp       : {result['timestamp']}",
        title="Auto Scraper Result",
        expand=False,
    ))

    if result["circulars"]:
        console.print("\n[bold]Newly ingested circulars:[/bold]")
        for c in result["circulars"]:
            console.print(Panel(
                f"[cyan]{c['title'][:70]}[/cyan]\n"
                f"Circular No : {c.get('circular_no') or 'N/A'}\n"
                f"Date        : {c.get('date_issued') or 'N/A'}\n"
                f"Text chars  : {c['chars']}\n"
                f"PDF saved   : {c['pdf_saved']}",
                expand=False,
            ))

    if result["errors"]:
        console.print("\n[yellow]Failed items:[/yellow]")
        for e in result["errors"]:
            console.print(f"  [red]✗[/red] {e['title'][:60]} — {e['reason']}")

    console.print("\n[bold green]Auto scraper test complete![/bold green]")
    console.print(
        "[dim]To run continuously every 30 mins:[/dim]\n"
        "[bold]python -m src.watcher.auto_scraper --schedule[/bold]\n"
    )


if __name__ == "__main__":
    asyncio.run(main())