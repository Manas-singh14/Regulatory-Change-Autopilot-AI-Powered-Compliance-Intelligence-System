import io
import logging
import re

import fitz
import httpx

logger = logging.getLogger("watcher.extractor")


async def extract_pdf_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        pdf_bytes = resp.content
        if len(pdf_bytes) < 1000:
            return None
        return _extract_text_from_bytes(pdf_bytes)
    except Exception as e:
        logger.error(f"Failed to extract PDF from {url}: {e}")
        return None


def _extract_text_from_bytes(pdf_bytes: bytes) -> str | None:
    try:
        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        pages_text = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                pages_text.append(f"[Page {page_num + 1}]\n{text}")
        doc.close()
        if not pages_text:
            return None
        return _clean_text("\n\n".join(pages_text))
    except Exception as e:
        logger.error(f"PyMuPDF error: {e}")
        return None


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^[-_=]{3,}\s*$", "", text, flags=re.MULTILINE)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def extract_pdf_text_from_file(file_path: str) -> str | None:
    """
    Synchronous version — extract text from a local PDF file.
    Use this for PDFs already downloaded to disk.
    """
    try:
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
        return _extract_text_from_bytes(pdf_bytes)
    except Exception as e:
        logger.error(f"Failed to read local PDF {file_path}: {e}")
        return None