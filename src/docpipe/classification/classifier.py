"""Simulated sensitivity labelling (mimics what Microsoft Purview does at scale).
In production, Purview scans/labels the data estate and labels propagate with the
file. Here we show the *concept*: classify -> store label -> enforce access by label."""
import re

LABELS = ["Internal", "Confidential", "Highly Confidential"]   # low -> high

PATTERNS = {
    "Highly Confidential": [
        r"\b\d{3}-\d{2}-\d{4}\b",                 # SSN-like
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",      # IBAN-like
        r"\b(?:account|acct)\s*(?:no|number|#)?[:\s]*\d{8,}\b",
    ],
    "Confidential": [r"\b(loan|principal|agreement|borrower|invoice)\b"],
}

# RBAC: which labels each role may read
ROLE_ACCESS = {
    "analyst": {"Internal"},
    "reviewer": {"Internal", "Confidential"},
    "compliance": {"Internal", "Confidential", "Highly Confidential"},
}


def classify(text: str) -> str:
    for label in ("Highly Confidential", "Confidential"):
        if any(re.search(p, text, re.IGNORECASE) for p in PATTERNS[label]):
            return label
    return "Internal"


def can_read(role: str, label: str) -> bool:
    return label in ROLE_ACCESS.get(role, set())
