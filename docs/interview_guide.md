# Interview Guide: how to explain this project

## 30-second pitch
"I built an ingestion and extraction pipeline for financial documents. It pulls files from email,
SharePoint, portals and shared drives, stages them in an encrypted landing zone, normalizes
PDF/Word/Excel/CSV/JSON/images, extracts fields with Azure Document Intelligence, validates them,
and stores clean JSON with full lineage. Low-confidence results go to human review, and failures
go to a dead-letter queue. Re-running it never creates duplicates."

## Be honest about scope
- Built with **synthetic data**, simulating a regulated environment.
- Local mode is tested; Azure connectors follow Microsoft docs and need a tenant to verify.
- Purview is **simulated** with rule-based labels. I understand the concept, not production Purview.

## Likely questions and answers

**Why a landing zone for raw files?** Raw data is the source of truth. It is stored once, unchanged,
under a hash name, so any result can be reproduced or audited and any bug fixed by reprocessing.

**How is it idempotent?** Each file's SHA-256 is the key (`documents.file_hash` is UNIQUE). If the hash is
already COMPLETED/NEEDS_REVIEW/DUPLICATE, the run skips it. Failed files are retried. `--force` clears
derived data and rebuilds it.

**Retry vs dead letter?** Transient errors (timeouts, HTTP 429/5xx) are retried with exponential backoff
plus jitter. Permanent errors (corrupt file, unsupported type) can't succeed, so retrying wastes money; they go
straight to the dead-letter queue with a reason.

**How did you choose the confidence threshold?** It's configurable (default 0.85). In production I'd measure
a sample of reviewed documents and pick the threshold that balances reviewer workload against error rate,
and use stricter thresholds for critical fields like amount.

**How do you detect duplicates?** Two levels: exact (same bytes -> same hash) and logical (same
document_number + counterparty + amount from a different file).

**How is lineage captured?** `lineage_events` records every stage transition with timestamp and pipeline
version; `extracted_fields` stores model id/version, confidence and page per value, so any value can be traced
back to its source file (see `sql/lineage_queries.sql`).

**How is it secure?** Encryption at rest (Blob default), Managed Identity instead of keys, RBAC roles,
secrets in Key Vault, sensitivity labels enforced per role (`can_read`), read-only raw copies, and an audit log.

**Why only call Document Intelligence for some files?** Text-based formats (CSV/JSON/Excel/native PDF) don't need
OCR, so I extract them directly and save cost. Scans and images go to Document Intelligence.

**What would you improve?** Orchestration with Azure Functions/Durable Functions, a queue between stages for
scale, custom Document Intelligence models for deal-specific documents, a Streamlit review UI, CI pipeline,
integration tests against a dev tenant, Purview integration.
