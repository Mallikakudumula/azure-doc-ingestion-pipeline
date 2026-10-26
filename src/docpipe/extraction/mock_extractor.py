"""Offline stand-in for Azure Document Intelligence so the whole pipeline runs
on a laptop. It reads 'Label: value' lines and assigns a confidence score.
DEMO HEURISTIC: values that look like bad OCR (letters inside numbers) get a low
score, which lets you see the human-review path without paying for Azure."""
import re

from ..models import ExtractedField, ExtractionResult, NormalizedDocument, PermanentError
from .fields import LABEL_TO_FIELD

LINE = re.compile(r"^\s*([A-Za-z #._/]+?)\s*[:=]\s*(.+?)\s*$")


def _confidence(field: str, value: str) -> float:
    if field in ("amount", "document_date") and re.search(r"[OoIl|]", value) \
            and re.search(r"\d", value):
        return 0.55       # looks like an OCR misread, e.g. '12,4O0.00'
    return 0.97


class MockExtractor:
    model_id = "mock-text-extractor"
    model_version = "1.0"

    def extract(self, filename: str, content: bytes, doc: NormalizedDocument) -> ExtractionResult:
        if doc.needs_ocr:
            raise PermanentError("Scanned/image document needs real OCR: "
                                 "run with PIPELINE_MODE=azure (Document Intelligence)")
        found: dict[str, ExtractedField] = {}
        for line in doc.text.splitlines():
            m = LINE.match(line)
            if not m:
                continue
            field = LABEL_TO_FIELD.get(m.group(1).strip().lower())
            if field and field not in found:
                value = m.group(2).strip()
                found[field] = ExtractedField(field, value, _confidence(field, value))
        return ExtractionResult(list(found.values()), self.model_id, self.model_version)
