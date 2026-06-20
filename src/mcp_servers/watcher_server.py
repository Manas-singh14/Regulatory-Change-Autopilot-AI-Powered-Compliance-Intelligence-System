"""
RegWatch AI — MCP Server
Exposes regulatory watching + gap analysis as tools
that any MCP-compatible AI agent can call.

Run with: python -m src.mcp_servers.watcher_server
"""

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("regwatch.mcp")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("regwatch-ai")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [

        Tool(
            name="watch_regulator_feed",
            description=(
                "Scrapes RBI, SEBI, and/or IRDAI for new circulars. "
                "Downloads PDFs, extracts text, saves to database. "
                "Returns a summary of new documents found."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "regulators": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["RBI", "SEBI", "IRDAI"]},
                        "description": "Which regulators to watch. Default: all three.",
                        "default": ["RBI", "SEBI", "IRDAI"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max circulars to fetch per regulator. Default 5.",
                        "default": 5,
                    },
                },
            },
        ),

        Tool(
            name="run_gap_analysis",
            description=(
                "Runs compliance gap analysis on a specific circular. "
                "Compares it against internal policies stored in the vector DB. "
                "Returns structured gaps with severity, requirements, and actions."
            ),
            inputSchema={
                "type": "object",
                "required": ["circular_id"],
                "properties": {
                    "circular_id": {
                        "type": "string",
                        "description": "ID of the circular from the database.",
                    },
                },
            },
        ),

        Tool(
            name="list_pending_circulars",
            description=(
                "Lists circulars that have been fetched but not yet "
                "gap-analysed. Use this to see what needs processing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "regulator": {
                        "type": "string",
                        "enum": ["RBI", "SEBI", "IRDAI"],
                        "description": "Filter by regulator (optional).",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                    },
                },
            },
        ),

        Tool(
            name="get_circular_summary",
            description=(
                "Returns a plain-English summary of any circular in the database. "
                "Useful for quick briefings without full gap analysis."
            ),
            inputSchema={
                "type": "object",
                "required": ["circular_id"],
                "properties": {
                    "circular_id": {
                        "type": "string",
                        "description": "ID of the circular to summarise.",
                    },
                },
            },
        ),

    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "watch_regulator_feed":
        return await _handle_watch(arguments)
    elif name == "run_gap_analysis":
        return await _handle_gap_analysis(arguments)
    elif name == "list_pending_circulars":
        return await _handle_list_pending(arguments)
    elif name == "get_circular_summary":
        return await _handle_summary(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# watch_regulator_feed
# ---------------------------------------------------------------------------

async def _handle_watch(args: dict) -> list[TextContent]:
    from src.watcher.auto_scraper import run_auto_pipeline

    limit = args.get("limit", 5)
    result = await run_auto_pipeline(max_new=limit)

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# run_gap_analysis
# ---------------------------------------------------------------------------

async def _handle_gap_analysis(args: dict) -> list[TextContent]:
    from src.watcher.database import get_db_path
    from src.rag.gap_analyser import analyse_gaps

    circular_id = args["circular_id"]

    # Fetch circular from DB
    con = sqlite3.connect(get_db_path())
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM circulars WHERE id = ?", (circular_id,)
    ).fetchone()
    con.close()

    if not row:
        return [TextContent(type="text", text=json.dumps({
            "error": f"Circular {circular_id} not found in database"
        }))]

    row = dict(row)
    if not row.get("text_content"):
        return [TextContent(type="text", text=json.dumps({
            "error": "Circular has no extracted text — cannot analyse"
        }))]

    # Run gap analysis
    result = analyse_gaps(
        circular_text=row["text_content"],
        circular_title=row["title"],
        circular_no=row.get("circular_no"),
    )

    # Mark as ingested/analysed
    con = sqlite3.connect(get_db_path())
    con.execute(
        "UPDATE circulars SET ingested = 1 WHERE id = ?", (circular_id,)
    )
    con.commit()
    con.close()

    output = {
        "status": "success",
        "circular_id": circular_id,
        "circular_title": result.circular_title,
        "circular_no": result.circular_no,
        "summary": result.summary,
        "total_gaps": result.total_gaps,
        "severity_counts": {
            "high": result.high,
            "medium": result.medium,
            "low": result.low,
        },
        "gaps": [
            {
                "gap_id": g.gap_id,
                "title": g.title,
                "severity": g.severity,
                "new_requirement": g.new_requirement,
                "existing_policy": g.existing_policy,
                "suggested_action": g.suggested_action,
                "deadline": g.deadline,
            }
            for g in result.gaps
        ],
    }
    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ---------------------------------------------------------------------------
# list_pending_circulars
# ---------------------------------------------------------------------------

async def _handle_list_pending(args: dict) -> list[TextContent]:
    from src.watcher.database import get_circulars

    rows = get_circulars(
        regulator=args.get("regulator"),
        ingested=False,
        limit=args.get("limit", 10),
    )

    # Strip full text — keep it lean
    clean = []
    for r in rows:
        clean.append({
            "id":          r["id"],
            "regulator":   r["regulator"],
            "title":       r["title"][:80],
            "date_issued": r["date_issued"],
            "circular_no": r["circular_no"],
            "has_text":    bool(r.get("text_content")),
            "fetched_at":  r["fetched_at"],
        })

    return [TextContent(type="text", text=json.dumps({
        "pending_count": len(clean),
        "circulars": clean,
    }, indent=2))]


# ---------------------------------------------------------------------------
# get_circular_summary
# ---------------------------------------------------------------------------

async def _handle_summary(args: dict) -> list[TextContent]:
    import sqlite3
    from src.watcher.database import get_db_path
    from langchain_groq import ChatGroq

    circular_id = args["circular_id"]

    con = sqlite3.connect(get_db_path())
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM circulars WHERE id = ?", (circular_id,)
    ).fetchone()
    con.close()

    if not row:
        return [TextContent(type="text", text=json.dumps({
            "error": f"Circular {circular_id} not found"
        }))]

    row = dict(row)
    text = row.get("text_content", "")
    if not text:
        return [TextContent(type="text", text=json.dumps({
            "error": "No text available for this circular"
        }))]

    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.2,
    )

    prompt = f"""Summarise this RBI circular in 3-4 sentences for a compliance analyst.
Be specific — mention the exact rule change, who it applies to, and effective date.

CIRCULAR:
{text[:2000]}

SUMMARY:"""
    

    response = llm.invoke([{"role": "user", "content": prompt}])

    return [TextContent(type="text", text=json.dumps({
        "circular_id":   circular_id,
        "title":         row["title"][:80],
        "date_issued":   row["date_issued"],
        "circular_no":   row["circular_no"],
        "summary":       response.content.strip(),
    }, indent=2))]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())