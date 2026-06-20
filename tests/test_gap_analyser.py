import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.watcher.extractor import extract_pdf_text_from_file
from src.watcher.database import init_db, upsert_circular, make_circular_id
from src.watcher.models import Circular
from src.rag.ingestor import ingest_pending, search
from src.rag.gap_analyser import analyse_gaps

console = Console()

SEVERITY_COLORS = {
    "High":   "red",
    "Medium": "yellow",
    "Low":    "green",
}


def load_internal_policy():
    """Load and embed the internal policy document into Qdrant."""
    policy_path = Path("data/circulars/pdfs/internal_policy.txt")
    if not policy_path.exists():
        console.print("[red]internal_policy.txt not found[/red]")
        return False

    text = policy_path.read_text(encoding="utf-8")
    cid = make_circular_id(str(policy_path))

    c = Circular(
        id=cid,
        regulator="INTERNAL",
        title="DemoFinance Internal Compliance Policy v2.1",
        url=str(policy_path),
        text_content=text,
    )

    from src.watcher.database import upsert_circular
    is_new = upsert_circular(c)

    if is_new:
        console.print("[green]✓[/green] Internal policy loaded into DB")
        count = ingest_pending()
        console.print(f"[green]✓[/green] Embedded into Qdrant ({count} docs)\n")
    else:
        console.print("[dim]Internal policy already in DB[/dim]\n")

    return True


def main():
    console.print("\n[bold green]Phase 2 — Gap Analysis with Groq[/bold green]\n")

    init_db()

    # Step 1: Load internal policy into vector store
    console.print("[yellow]Loading internal policy document...[/yellow]")
    if not load_internal_policy():
        return

    # Step 2: Pick an RBI circular to analyse
    pdf_dir = Path("data/circulars/pdfs")
    pdfs = [p for p in pdf_dir.glob("*.pdf")]

    if not pdfs:
        console.print("[red]No RBI PDFs found[/red]")
        return

    # Use the largest PDF — usually has most content
    target = sorted(pdfs, key=lambda p: p.stat().st_size, reverse=True)[0]
    console.print(f"[yellow]Analysing circular:[/yellow] {target.name}\n")

    # Step 3: Extract circular text
    text = extract_pdf_text_from_file(str(target))
    if not text:
        console.print("[red]Could not extract text[/red]")
        return

    console.print(f"[dim]Extracted {len(text)} chars from circular[/dim]")
    console.print("[yellow]Calling Groq for gap analysis...[/yellow]\n")

    # Step 4: Run gap analysis
    # This retrieves internal policy chunks from Qdrant as context
    result = analyse_gaps(
        circular_text=text,
        circular_title=target.stem,
    )

    # Step 5: Print results
    console.print(Panel(
        f"[bold]{result.circular_title}[/bold]\n"
        f"Circular No: {result.circular_no or 'N/A'}\n\n"
        f"{result.summary}",
        title="Gap Analysis Summary",
        expand=False,
    ))

    # Severity table
    counts = Table(box=box.SIMPLE)
    counts.add_column("Severity", style="bold")
    counts.add_column("Count", justify="center")
    counts.add_row("[red]High[/red]",         str(result.high))
    counts.add_row("[yellow]Medium[/yellow]", str(result.medium))
    counts.add_row("[green]Low[/green]",      str(result.low))
    counts.add_row("[bold]Total[/bold]",      str(result.total_gaps))
    console.print(counts)

    # Each gap
    console.print(f"\n[bold]Compliance Gaps:[/bold]\n")
    for gap in result.gaps:
        color = SEVERITY_COLORS.get(gap.severity, "white")
        console.print(Panel(
            f"[bold]{gap.gap_id}. {gap.title}[/bold]\n"
            f"Severity: [{color}]{gap.severity}[/{color}]\n\n"
            f"[bold]New Requirement:[/bold]\n{gap.new_requirement}\n\n"
            f"[bold]Existing Policy:[/bold]\n{gap.existing_policy}\n\n"
            f"[bold]Suggested Action:[/bold]\n{gap.suggested_action}\n\n"
            f"[bold]Deadline:[/bold] {gap.deadline or 'Not specified'}",
            expand=False,
        ))

    console.print("\n[bold green]Phase 2 complete![/bold green]")
    console.print("Next: MCP server wiring\n")


if __name__ == "__main__":
    main()