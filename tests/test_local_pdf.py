import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from pathlib import Path

from src.watcher.extractor import extract_pdf_text_from_file
from src.watcher.database import init_db, upsert_circular, make_circular_id
from src.watcher.models import Circular
from src.rag.ingestor import ingest_pending, search

console = Console()


def main():
    console.print("\n[bold green]Phase 1 — Local PDF Ingestion[/bold green]\n")

    init_db()

    pdf_dir = Path("data/circulars/pdfs")
    pdfs = list(pdf_dir.glob("*.pdf"))

    if not pdfs:
        console.print("[red]No PDFs found in data/circulars/pdfs/[/red]")
        console.print("Download some RBI circulars from rbi.org.in and put them there")
        return

    console.print(f"[yellow]Found {len(pdfs)} PDFs — extracting text...[/yellow]\n")

    saved = 0
    for pdf_path in pdfs:
        text = extract_pdf_text_from_file(str(pdf_path))
        if not text:
            console.print(f"[red]✗[/red] Could not extract: {pdf_path.name}")
            continue

        cid = make_circular_id(str(pdf_path))
        c = Circular(
            id=cid,
            regulator="RBI",
            title=pdf_path.stem,
            url=str(pdf_path),
            text_content=text,
        )
        if upsert_circular(c):
            console.print(f"[green]✓[/green] {pdf_path.name} — {len(text)} chars extracted")
            saved += 1

    console.print(f"\n[green]✓[/green] {saved} PDFs saved to DB\n")

    # Embed into Qdrant
    console.print("[yellow]Embedding into Qdrant...[/yellow]")
    count = ingest_pending()
    console.print(f"[green]✓[/green] Ingested {count} circulars\n")

    # Test semantic search
    console.print("[yellow]Testing semantic search...[/yellow]\n")
    queries = [
        "KYC norms for banks",
        "interest rate guidelines",
        "capital adequacy requirements",
        "NBFC regulations",
    ]

    for q in queries:
        results = search(q, top_k=2)
        if not results:
            continue
        console.print(f"[bold]Query:[/bold] {q}")
        for r in results:
            console.print(Panel(
                f"[cyan]{r['title'][:70]}[/cyan]\n"
                f"Score: {r['score']} | {r['date_issued'] or 'no date'}\n\n"
                f"{r['chunk_text'][:300]}...",
                expand=False
            ))
        console.print()

    console.print("[bold green]Phase 1 complete![/bold green]")
    console.print("Next: Gap analysis LLM chain with Groq\n")


if __name__ == "__main__":
    main()