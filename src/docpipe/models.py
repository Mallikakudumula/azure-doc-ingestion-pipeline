"""Plain data objects passed between pipeline stages."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PermanentError(Exception):
    """Will never succeed on retry (corrupt file, unsupported type) -> dead letter."""


class TransientError(Exception):
    """Might succeed on retry (timeout, throttling, 5xx) -> retried with backoff."""


@dataclass
class RawDocument:
    filename: str
    content: bytes
    source_channel: str          # email | sharepoint | portal | shared_drive
    source_ref: str              # message id, drive item id, or file path
    received_at: str = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedDocument:
    file_format: str             # pdf, docx, xlsx, csv, json, image, txt
    text: str                    # standard processing format: plain text
    page_count: int = 1
    needs_ocr: bool = False      # scanned PDF / image -> requires OCR


@dataclass
class ExtractedField:
    name: str
    value: Any
    confidence: float
    page: int = 1


@dataclass
class ExtractionResult:
    fields: list[ExtractedField]
    model_id: str
    model_version: str


@dataclass
class ValidationResult:
    passed: bool = True
    needs_review: bool = False
    is_duplicate: bool = False
    issues: list[str] = field(default_factory=list)
    clean_values: dict[str, Any] = field(default_factory=dict)
