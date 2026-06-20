"""
Takes circulars from SQLite, chunks the text,
embeds with HuggingFace, stores in Qdrant.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from src.watcher.database import get_circulars, mark_ingested

load_dotenv()
logger = logging.getLogger("rag.ingestor")

COLLECTION_NAME = "circulars"
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"   # free, local, 384 dims
CHUNK_SIZE       = 512
CHUNK_OVERLAP    = 50


def get_qdrant_client() -> QdrantClient:
    path = os.getenv("QDRANT_PATH", "./data/vectors")
    Path(path).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=path)


def ensure_collection(client: QdrantClient) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks.
    Tries to split on newlines to keep sections together.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += size - overlap
    return chunks


def ingest_pending(limit: int = 50) -> int:
    """
    Fetch all un-ingested circulars from DB,
    embed them, push to Qdrant.
    Returns number of circulars ingested.
    """
    circulars = get_circulars(ingested=False, limit=limit)

    if not circulars:
        logger.info("No pending circulars to ingest")
        return 0

    logger.info(f"Ingesting {len(circulars)} circulars...")

    # Load model once (downloads on first run ~80MB)
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = get_qdrant_client()
    ensure_collection(client)

    ingested_count = 0

    for circular in circulars:
        text = circular.get("text_content")
        if not text:
            # No text yet — mark ingested anyway to avoid re-processing
            logger.warning(f"No text for {circular['id']} — skipping embed")
            mark_ingested(circular["id"])
            continue

        chunks = chunk_text(text)
        logger.info(f"  [{circular['regulator']}] {circular['title'][:50]} — {len(chunks)} chunks")

        points = []
        for i, chunk in enumerate(chunks):
            embedding = model.encode(chunk).tolist()
            point_id = abs(hash(f"{circular['id']}_{i}")) % (2**31)

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "circular_id":  circular["id"],
                    "regulator":    circular["regulator"],
                    "title":        circular["title"],
                    "url":          circular["url"],
                    "date_issued":  circular["date_issued"],
                    "circular_no":  circular["circular_no"],
                    "chunk_index":  i,
                    "chunk_text":   chunk,
                },
            ))

        if points:
            client.upsert(collection_name=COLLECTION_NAME, points=points)

        mark_ingested(circular["id"])
        ingested_count += 1

    logger.info(f"Done. Ingested {ingested_count} circulars.")
    return ingested_count


def search(query: str, top_k: int = 5, regulator: str | None = None) -> list[dict]:
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = get_qdrant_client()

    query_vector = model.encode(query).tolist()

    search_filter = None
    if regulator:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        search_filter = Filter(
            must=[FieldCondition(
                key="regulator",
                match=MatchValue(value=regulator.upper())
            )]
        )

    hits = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    ).points

    return [
        {
            "score":       round(hit.score, 4),
            "regulator":   hit.payload["regulator"],
            "title":       hit.payload["title"],
            "circular_no": hit.payload.get("circular_no"),
            "date_issued": hit.payload.get("date_issued"),
            "url":         hit.payload["url"],
            "chunk_text":  hit.payload["chunk_text"],
        }
        for hit in hits
    ]