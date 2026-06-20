"""
Gap Analysis Engine.
Takes a new RBI circular + retrieves relevant policy chunks from Qdrant,
then uses Groq LLM to identify compliance gaps.
Returns structured JSON output.
"""

import json
import logging
import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel

from src.rag.ingestor import search

load_dotenv()
logger = logging.getLogger("rag.gap_analyser")


# ---------------------------------------------------------------------------
# Pydantic models for structured output
# ---------------------------------------------------------------------------

class ComplianceGap(BaseModel):
    gap_id: int
    title: str
    severity: str            # "High", "Medium", "Low"
    new_requirement: str     # What the new circular requires
    existing_policy: str     # What current policy says (or lacks)
    suggested_action: str    # What the compliance team should do
    deadline: str | None     # If circular mentions effective date


class GapAnalysisResult(BaseModel):
    circular_title: str
    circular_no: str | None
    total_gaps: int
    high: int
    medium: int
    low: int
    gaps: list[ComplianceGap]
    summary: str


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior compliance analyst specializing in Indian 
financial regulation (RBI, SEBI, IRDAI). Your job is to compare a NEW regulatory 
circular against EXISTING policy excerpts and identify compliance gaps.

A compliance gap is anything the new circular REQUIRES that the existing policies 
do NOT adequately address.

Always respond with valid JSON only. No preamble, no explanation outside the JSON.
"""

GAP_ANALYSIS_PROMPT = """
## NEW CIRCULAR
{circular_text}

## EXISTING POLICY EXCERPTS (retrieved from policy database)
{policy_context}

## YOUR TASK
Analyze the new circular against the existing policy excerpts above.
Identify every compliance gap — things the circular requires that existing 
policies don't cover or insufficiently address.

Respond with this exact JSON structure:
{{
  "circular_title": "<title of the circular>",
  "circular_no": "<circular number if found>",
  "total_gaps": <number>,
  "high": <count of High severity gaps>,
  "medium": <count of Medium severity gaps>,
  "low": <count of Low severity gaps>,
  "summary": "<2-3 sentence summary of the overall compliance situation>",
  "gaps": [
    {{
      "gap_id": 1,
      "title": "<short title of this gap>",
      "severity": "High|Medium|Low",
      "new_requirement": "<exactly what the circular requires>",
      "existing_policy": "<what existing policy says or 'Not addressed in current policies'>",
      "suggested_action": "<concrete action the compliance team should take>",
      "deadline": "<effective date from circular or null>"
    }}
  ]
}}

Severity guide:
- High: Legal/regulatory risk if not addressed immediately
- Medium: Must be addressed but not immediate legal risk  
- Low: Best practice improvement, low risk
"""


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def analyse_gaps(
    circular_text: str,
    circular_title: str = "Unknown Circular",
    circular_no: str | None = None,
    top_k_context: int = 5,
) -> GapAnalysisResult:
    """
    Run gap analysis on a new circular.
    
    Args:
        circular_text: Full extracted text of the new circular
        circular_title: Title of the circular
        circular_no: Circular number (e.g. RBI/2026-27/143)
        top_k_context: How many existing policy chunks to retrieve
    
    Returns:
        GapAnalysisResult with structured gaps
    """

    # Step 1: Retrieve relevant existing policy chunks via semantic search
    logger.info(f"Retrieving context for: {circular_title}")
    context_chunks = search(circular_text[:500], top_k=top_k_context)

    if context_chunks:
        policy_context = "\n\n---\n\n".join([
            f"[{c['regulator']}] {c['title']}\n{c['chunk_text']}"
            for c in context_chunks
        ])
    else:
        policy_context = "No existing policy documents found in database yet."

    # Step 2: Build prompt
    prompt = GAP_ANALYSIS_PROMPT.format(
        circular_text=circular_text[:3000],  # cap to avoid token limits
        policy_context=policy_context[:2000],
    )

    # Step 3: Call Groq
    logger.info("Calling Groq for gap analysis...")
    llm = ChatGroq(
        model="llama-3.1-8b-instant",  # or "llama-3.1-8b-chat" if you prefer chat model
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.1,  # low temp for consistent structured output
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    # Step 4: Parse JSON response
    try:
        # Strip markdown fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Raw response: {raw[:500]}")
        # Return a minimal result rather than crash
        return GapAnalysisResult(
            circular_title=circular_title,
            circular_no=circular_no,
            total_gaps=0,
            high=0, medium=0, low=0,
            gaps=[],
            summary="Gap analysis failed — could not parse LLM response.",
        )

    # Step 5: Map to Pydantic model
    gaps = [ComplianceGap(**g) for g in data.get("gaps", [])]

    return GapAnalysisResult(
        circular_title=data.get("circular_title", circular_title),
        circular_no=data.get("circular_no", circular_no),
        total_gaps=data.get("total_gaps", len(gaps)),
        high=data.get("high", 0),
        medium=data.get("medium", 0),
        low=data.get("low", 0),
        gaps=gaps,
        summary=data.get("summary", ""),
    )