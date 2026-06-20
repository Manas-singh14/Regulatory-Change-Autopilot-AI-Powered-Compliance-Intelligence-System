from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapeResult:
    regulator: str
    title: str
    url: str
    date_issued: str | None = None
    circular_no: str | None = None


@dataclass
class Circular:
    id: str
    regulator: str
    title: str
    url: str
    date_issued: str | None = None
    effective_on: str | None = None
    circular_no: str | None = None
    text_content: str | None = None
    fetched_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )