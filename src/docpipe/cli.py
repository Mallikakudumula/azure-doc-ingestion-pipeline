"""Command line interface:
  python -m docpipe.cli run [--source local|email|sharepoint|all] [--force]
  python -m docpipe.cli report
  python -m docpipe.cli review list
  python -m docpipe.cli review resolve <doc_id> --reviewer NAME [--set field=value ...]
  python -m docpipe.cli lineage <doc_id> [--role analyst|reviewer|compliance]"""
import argparse
import json
import logging

from .classification.classifier import can_read
from .config import load_settings
from .factory import build_connectors, build_pipeline
from .logging_setup import setup_logging
from .models import ExtractedField, ExtractionResult
from .validation.validator import validate

log = logging.getLogger("docpipe.cli")


def cmd_run(args, s, pipe):
    counts: dict[str, int] = {}
    for connector in build_connectors(s, args.source):
        for raw in connector.fetch():
            outcome = pipe.process(raw, force=args.force)
            counts[outcome] = counts.get(outcome, 0) + 1
    print("\nRun summary:", json.dumps(counts) if counts else "no documents found")


def cmd_report(args, s, pipe):
    print(f"{'channel':<14}{'status':<14}count")
    for r in pipe.repo.status_report():
        print(f"{r['source_channel']:<14}{r['status']:<14}{r['n']}")


def cmd_review(args, s, pipe):
    repo = pipe.repo
    if args.action == "list":
        rows = repo.pending_reviews()
        if not rows:
            print("Review queue is empty.")
        for r in rows:
            print(f"doc {r['document_id']:>3}  {r['filename']:<28} {r['reason']}")
        return
    doc_id = args.doc_id
    doc = repo.get_document(doc_id)
    if not doc:
        raise SystemExit(f"No document {doc_id}")
    fields = {f["field_name"]: f for f in repo.get_fields(doc_id)}
    # 1. apply human corrections (audited: old -> new)
    corrections = dict(item.split("=", 1) for item in (args.set or []))
    new_fields = []
    for name, f in fields.items():
        value = corrections.get(name, f["raw_value"])
        if name in corrections:
            repo.add_audit(args.reviewer, "FIELD_CORRECTED", doc_id, name, f["raw_value"], value)
        new_fields.append(ExtractedField(name, value, 1.0 if name in corrections else f["confidence"],
                                         f["page"] or 1))
    for name, value in corrections.items():
        if name not in fields:
            repo.add_audit(args.reviewer, "FIELD_ADDED", doc_id, name, None, value)
            new_fields.append(ExtractedField(name, value, 1.0))
    # 2. a human has now verified every field -> confidence 1.0, then re-validate rules
    verified = ExtractionResult([ExtractedField(f.name, f.value, 1.0, f.page) for f in new_fields],
                                "human-review", "1.0")
    v = validate(verified, s.confidence_threshold)
    if v.issues:
        raise SystemExit(f"Still invalid, not resolved: {v.issues}")
    repo.resolve_review(doc_id, args.reviewer)      # close the queue item first
    repo.reset_for_reprocess(doc_id)
    repo.save_fields(doc_id, verified.fields, v.clean_values, "human-review", "1.0")
    repo.update_document(doc_id, status="COMPLETED")
    repo.add_event(doc_id, "reviewed", "ok", f"resolved by {args.reviewer}")
    repo.add_audit(args.reviewer, "REVIEW_APPROVED", doc_id)
    pipe.write_output(doc_id)
    print(f"Document {doc_id} approved and stored.")


def cmd_lineage(args, s, pipe):
    repo = pipe.repo
    doc = repo.get_document(args.doc_id)
    if not doc:
        raise SystemExit(f"No document {args.doc_id}")
    if not can_read(args.role, doc["sensitivity_label"] or "Internal"):
        raise SystemExit(f"ACCESS DENIED: role '{args.role}' cannot read "
                         f"'{doc['sensitivity_label']}' documents")
    print(f"\nDocument {doc['id']}: {doc['filename']}  [{doc['sensitivity_label']}]  status={doc['status']}")
    print(f"source={doc['source_channel']}  raw copy={doc['landing_path']}")
    print("\nLineage:")
    for e in repo.get_events(doc["id"]):
        print(f"  {e['created_at']}  {e['stage']:<11}{e['status']:<8}{e['detail']}")
    print("\nFields:")
    for f in repo.get_fields(doc["id"]):
        print(f"  {f['field_name']:<16}{f['clean_value']!s:<22}conf={f['confidence']:.2f}  "
              f"page={f['page']}  {f['model_id']}@{f['model_version']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="docpipe")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run"); r.add_argument("--source", default="local",
                                              choices=["local", "email", "sharepoint", "all"])
    r.add_argument("--force", action="store_true")
    sub.add_parser("report")
    rv = sub.add_parser("review"); rv.add_argument("action", choices=["list", "resolve"])
    rv.add_argument("doc_id", nargs="?", type=int); rv.add_argument("--reviewer", default="reviewer1")
    rv.add_argument("--set", action="append", metavar="FIELD=VALUE")
    ln = sub.add_parser("lineage"); ln.add_argument("doc_id", type=int)
    ln.add_argument("--role", default="compliance", choices=["analyst", "reviewer", "compliance"])
    args = p.parse_args(argv)

    setup_logging()
    s = load_settings()
    pipe = build_pipeline(s)
    {"run": cmd_run, "report": cmd_report, "review": cmd_review, "lineage": cmd_lineage}[args.command](args, s, pipe)


if __name__ == "__main__":
    main()
