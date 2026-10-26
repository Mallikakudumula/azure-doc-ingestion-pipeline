"""Validation rules: schema, completeness, confidence threshold.
(Duplicate detection needs the database, so the pipeline sets is_duplicate.)"""
import re
from datetime import datetime

from ..extraction.fields import REQUIRED_FIELDS
from ..models import ExtractionResult, ValidationResult

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%B %d, %Y")


def parse_amount(value) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    return round(float(cleaned), 2)       # raises ValueError if not numeric


def parse_date(value) -> str:
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date '{value}'")


def validate(result: ExtractionResult, threshold: float) -> ValidationResult:
    v = ValidationResult()
    by_name = {f.name: f for f in result.fields}

    # 1. Completeness
    for name in REQUIRED_FIELDS:
        if name not in by_name or str(by_name[name].value).strip() == "":
            v.issues.append(f"missing_required_field:{name}")

    # 2. Schema / type checks (also produces the cleaned values)
    for name, f in by_name.items():
        try:
            if name == "amount":
                v.clean_values[name] = parse_amount(f.value)
            elif name == "document_date":
                v.clean_values[name] = parse_date(f.value)
            elif name == "currency":
                cur = str(f.value).strip().upper()
                if not re.fullmatch(r"[A-Z]{3}", cur):
                    raise ValueError(f"'{f.value}' is not a 3-letter currency code")
                v.clean_values[name] = cur
            else:
                v.clean_values[name] = str(f.value).strip()
        except ValueError as exc:
            v.issues.append(f"invalid_{name}:{exc}")

    # 3. Confidence threshold -> human-in-the-loop
    low = [f"{f.name}={f.confidence:.2f}" for f in result.fields if f.confidence < threshold]
    if low:
        v.issues.append("low_confidence:" + ",".join(low))

    v.needs_review = bool(v.issues)
    v.passed = not v.issues
    return v
