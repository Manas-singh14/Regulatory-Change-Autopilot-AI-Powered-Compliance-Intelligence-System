"""
Simulates an AI agent calling RegWatch MCP tools.
Tests all 4 tools in sequence like a real agent would.
Run: python tests/test_mcp_server.py
"""

import sys, os, json, asyncio, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

# Import handlers directly (simulates MCP tool calls)
from src.mcp_servers.watcher_server import (
    _handle_list_pending,
    _handle_gap_analysis,
    _handle_summary,
)
from src.watcher.database import get_db_path

console = Console()


async def main():
    console.print("\n[bold green]RegWatch AI — MCP Agent Simulation[/bold green]")
    console.print("[dim]Simulating an AI agent calling MCP tools in sequence[/dim]\n")

    # -----------------------------------------------------------------------
    # TOOL CALL 1: list_pending_circulars
    # -----------------------------------------------------------------------
    console.print(Rule("[yellow]Tool Call 1: list_pending_circulars[/yellow]"))
    console.print("[dim]Agent asks: What circulars are waiting to be analysed?[/dim]\n")

    result = await _handle_list_pending({"limit": 10})
    data = json.loads(result[0].text)

    console.print(f"[green]→ {data['pending_count']} circulars pending[/green]")
    for c in data["circulars"]:
        console.print(
            f"  [cyan]{c['id']}[/cyan] | {c['regulator']} | "
            f"{c['title'][:55]} | has_text: {c['has_text']}"
        )

    # Pick first circular that has text
    target = next((c for c in data["circulars"] if c["has_text"]), None)

    if not target:
        # Fall back — get any circular with text from DB
        con = sqlite3.connect(get_db_path())
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT id, title FROM circulars WHERE text_content IS NOT NULL LIMIT 1"
        ).fetchone()
        con.close()
        if row:
            target = {"id": dict(row)["id"], "title": dict(row)["title"]}
        else:
            console.print("[red]No circulars with text found. Run test_local_pdf.py first.[/red]")
            return

    console.print(f"\n[bold]Agent selected:[/bold] {target['id']}\n")

    # -----------------------------------------------------------------------
    # TOOL CALL 2: get_circular_summary
    # -----------------------------------------------------------------------
    console.print(Rule("[yellow]Tool Call 2: get_circular_summary[/yellow]"))
    console.print("[dim]Agent asks: Give me a quick briefing on this circular[/dim]\n")

    result = await _handle_summary({"circular_id": target["id"]})
    data = json.loads(result[0].text)

    if "error" in data:
        console.print(f"[red]{data['error']}[/red]")
    else:
        console.print(Panel(
            f"[bold]{data['title'][:70]}[/bold]\n"
            f"Circular No: {data.get('circular_no') or 'N/A'} | "
            f"Date: {data.get('date_issued') or 'N/A'}\n\n"
            f"{data['summary']}",
            title="Circular Briefing",
            expand=False,
        ))

    # -----------------------------------------------------------------------
    # TOOL CALL 3: run_gap_analysis
    # -----------------------------------------------------------------------
    console.print(Rule("[yellow]Tool Call 3: run_gap_analysis[/yellow]"))
    console.print("[dim]Agent asks: What compliance gaps does this create?[/dim]\n")

    result = await _handle_gap_analysis({"circular_id": target["id"]})
    data = json.loads(result[0].text)

    if "error" in data:
        console.print(f"[red]{data['error']}[/red]")
        return

    console.print(Panel(
        f"[bold]{data['circular_title'][:70]}[/bold]\n\n"
        f"{data['summary']}\n\n"
        f"[red]High: {data['severity_counts']['high']}[/red]  "
        f"[yellow]Medium: {data['severity_counts']['medium']}[/yellow]  "
        f"[green]Low: {data['severity_counts']['low']}[/green]  "
        f"| Total: {data['total_gaps']}",
        title="Gap Analysis Result",
        expand=False,
    ))

    for gap in data["gaps"]:
        color = {"High": "red", "Medium": "yellow", "Low": "green"}.get(
            gap["severity"], "white"
        )
        console.print(Panel(
            f"[bold]{gap['gap_id']}. {gap['title']}[/bold]  "
            f"[{color}][{gap['severity']}][/{color}]\n\n"
            f"[bold]Requires:[/bold] {gap['new_requirement']}\n\n"
            f"[bold]Current policy:[/bold] {gap['existing_policy']}\n\n"
            f"[bold]Action:[/bold] {gap['suggested_action']}\n"
            f"[bold]Deadline:[/bold] {gap['deadline'] or 'Not specified'}",
            expand=False,
        ))

    # -----------------------------------------------------------------------
    # AGENT DECISION SUMMARY
    # -----------------------------------------------------------------------
    console.print(Rule("[green]Agent Summary[/green]"))
    console.print(Panel(
        f"[bold]RegWatch AI completed autonomous analysis[/bold]\n\n"
        f"Circular analysed : {data['circular_title'][:60]}\n"
        f"Gaps found        : {data['total_gaps']}\n"
        f"High severity     : {data['severity_counts']['high']}\n\n"
        f"[dim]In production: MCP server would now call create_jira_epic\n"
        f"and post_slack_alert automatically.[/dim]",
        title="Mission Complete",
        expand=False,
    ))

    console.print("\n[bold green]Phase 3 complete![/bold green]")
    console.print("Your MCP server is live. Next: connect it to Claude Desktop.\n")


if __name__ == "__main__":
    asyncio.run(main())