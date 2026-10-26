# Azure Document Ingestion & Extraction Pipeline

A secure, auditable **document ingestion pipeline** that ingests documents from multiple
channels, extracts structured data with **Azure Document Intelligence (OCR + AI)**, validates it,
and lands clean JSON plus full lineage in a relational database for downstream
**collateral / deal-hub** workflows.

> All sample data is **100% fake**. Never commit real financial documents.

It runs in two modes:

| Mode | What it uses | Needs Azure? |
|---|---|---|
| `local` (default) | Folder inbox, mock extractor, SQLite, local landing zone | No |
| `azure` | Graph API, Document Intelligence, Blob Storage, Service Bus, App Insights | Yes |

The pipeline code is identical in both modes. Only the *plug-in components* change (see `factory.py`).

## Architecture

```
 Email (Graph) ─┐
 SharePoint ────┤                    ┌──────────────► Dead letter (Service Bus / folder)
 Portal ────────┼─► Connectors ─► Landing zone ─► Normalize ─► Classify ─► Extract ─► Validate
 Shared drive ──┘   (fetch)       (raw, immutable)  (to text)   (label)   (DI + OCR)    │
                                                                                         ├─► clean ──► JSON + SQL (COMPLETED)
                                                                                         └─► low confidence / invalid ──► Review queue ──► human fix (audited)
 Every step writes a lineage event; every human change writes an audit row.
```

## JD requirement → where it is in the code

| Job description requirement | File |
|---|---|
| Ingestion connectors (email, SharePoint, portal, shared drive) via Microsoft Graph | `connectors/graph_email.py`, `graph_sharepoint.py`, `graph_client.py`, `local_folder.py` |
| Multi-format normalization (PDF native/scanned, Word, Excel, CSV, JSON, images) | `normalize/normalizer.py` |
| Secure landing zone (encryption, RBAC, managed identity) | `landing/landing_zone.py` |
| Azure Document Intelligence + OCR | `extraction/di_extractor.py` |
| Validation: schema, completeness, duplicates, confidence thresholds | `validation/validator.py`, `pipeline.py` (duplicates) |
| Human-in-the-loop review | `cli.py` (`review`), `review_queue` table |
| Metadata, lineage, audit trail | `sql/schema.sql`, `storage/repository.py`, `sql/lineage_queries.sql` |
| Retry, idempotent reprocessing, dead-letter | `resilience/retry.py`, `resilience/dead_letter.py`, `pipeline.py` |
| JSON persisted for downstream | `pipeline.write_output` -> `data/output/*.json` |
| Purview-style classification / sensitivity labels + RBAC | `classification/classifier.py` (simulated) |
| SQL + relational DB | `sql/`, `storage/` |
| Observability | `logging_setup.py` (Application Insights) |

## Quick start (local, no Azure needed)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Mac/Linux: source .venv/bin/activate)
pip install python-dotenv pypdf python-docx openpyxl requests reportlab Pillow

# Windows PowerShell:  $env:PYTHONPATH="src"       Mac/Linux:  export PYTHONPATH=src
python scripts/generate_sample_docs.py
python -m docpipe run
python -m docpipe report
python -m docpipe review list
python -m docpipe review resolve 1 --reviewer alice --set amount=8900.00
python -m docpipe lineage 1
python -m docpipe lineage 8 --role analyst     # ACCESS DENIED (Highly Confidential)
python -m docpipe run                          # run again: idempotent, nothing is duplicated
python -m unittest discover -s tests -v
```

### What the sample run demonstrates

| Sample file | Expected result | Concept |
|---|---|---|
| `email/invoice_acme.pdf` | COMPLETED | happy path |
| `shared_drive/invoice_acme_copy.pdf` | skipped | **idempotency** (same SHA-256) |
| `portal/invoice_acme_resubmitted.txt` | DUPLICATE | **business-key duplicate** detection |
| `email/blurry_invoice.pdf` | NEEDS_REVIEW | **low confidence** -> human review |
| `portal/deal_missing_date.json` | NEEDS_REVIEW | **completeness** check |
| `sharepoint/loan_agreement.docx` | COMPLETED, *Highly Confidential* | **classification + RBAC** |
| `sharepoint/trade_sheet.xlsx`, `shared_drive/payment.csv` | COMPLETED | multi-format |
| `shared_drive/corrupt.pdf` | FAILED -> dead letter | **error handling** |
| `portal/scanned_invoice.png` | dead letter in local mode; OCR'd in azure mode | **OCR path** |

## Azure mode setup (summary)

1. Create: Storage account (+ container `raw-landing`), Document Intelligence resource,
   Service Bus namespace + queue, Azure SQL (optional), Application Insights, Key Vault.
2. Authenticate with **Managed Identity** (or `az login` locally). Grant roles:
   *Storage Blob Data Contributor*, *Cognitive Services User*, *Azure Service Bus Data Sender*.
3. Register an Entra ID app for Graph with **application** permissions `Mail.Read` and
   `Sites.Read.All` (or `Sites.Selected`), then grant admin consent. Keep the secret in Key Vault.
4. Copy `.env.example` -> `.env`, set `PIPELINE_MODE=azure`, `pip install -r requirements.txt`.
5. `python -m docpipe run --source all`

**Honest status:** the local mode is fully tested (`tests/`). The Azure/Graph code follows the
official SDK docs but must be verified against your own tenant and SDK versions before you
claim it as production-tested. Microsoft Purview is **simulated** (`classifier.py`), not integrated.

## Moving the database to Azure SQL

`storage/repository.py` is the only file containing SQL. To switch, replace `sqlite3` with `pyodbc`,
change `?` placeholders to `?` (pyodbc uses the same), `AUTOINCREMENT` -> `IDENTITY(1,1)`,
and `TEXT` -> `NVARCHAR(...)`.

## Project structure

```
src/docpipe/
  pipeline.py        <- start reading here (whole flow)
  cli.py  factory.py config.py models.py
  connectors/ landing/ normalize/ extraction/ validation/
  classification/ resilience/ storage/
sql/schema.sql  sql/lineage_queries.sql
scripts/generate_sample_docs.py
tests/test_pipeline.py
docs/interview_guide.md
```
