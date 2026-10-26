"""The target schema + aliases used to map text labels to canonical field names."""
CANONICAL_FIELDS = ["document_number", "counterparty", "document_date", "amount", "currency"]
REQUIRED_FIELDS = ["document_number", "counterparty", "document_date", "amount"]

ALIASES = {
    "document_number": ["invoice number", "invoice no", "invoice id", "document number",
                        "loan id", "agreement number", "reference", "ref no"],
    "counterparty": ["vendor", "vendor name", "counterparty", "borrower", "customer",
                     "customer name", "supplier"],
    "document_date": ["date", "invoice date", "document date", "agreement date", "issue date"],
    "amount": ["total", "amount", "total amount", "invoice total", "loan amount", "principal"],
    "currency": ["currency", "ccy"],
}
LABEL_TO_FIELD = {a: f for f, names in ALIASES.items() for a in names}
