"""The orchestrator. Read this file first: it shows the whole flow in one place.

received -> staged -> normalized -> classified -> extracted -> validated -> stored
Any PermanentError (or a TransientError that exhausts retries) -> dead letter."""
import hashlib
import json
import logging

from .classification.classifier import classify
from .config import Settings
from .models import RawDocument
from .normalize.normalizer import normalize
from .resilience.retry import retry
from .validation.validator import validate

log = logging.getLogger(__name__)
DONE_STATES = {"COMPLETED", "NEEDS_REVIEW", "DUPLICATE"}


class Pipeline:
    def __init__(self, settings: Settings, repo, landing, extractor, dead_letter, sleep=None):
        self.s, self.repo, self.landing = settings, repo, landing
        self.extractor, self.dead_letter = extractor, dead_letter
        kw = {"sleep": sleep} if sleep else {}
        self._extract = retry(max_attempts=settings.max_retries, **kw)(extractor.extract)

    def process(self, raw: RawDocument, force: bool = False) -> str:
        file_hash = hashlib.sha256(raw.content).hexdigest()
        existing = self.repo.get_by_hash(file_hash)

        # ---- Idempotency: same bytes already handled -> skip (unless forced) ----
        if existing and existing["status"] in DONE_STATES and not force:
            log.info("SKIP %s (already %s)", raw.filename, existing["status"])
            self.repo.add_audit("pipeline", "SKIPPED_ALREADY_PROCESSED", existing["id"])
            return "skipped"

        if existing:
            doc_id = existing["id"]
            self.repo.reset_for_reprocess(doc_id)
            self.repo.add_event(doc_id, "reprocess", "ok", "forced or retrying a failed file")
        else:
            doc_id = self.repo.create_document(file_hash, raw.filename, raw.source_channel,
                                               raw.source_ref, raw.received_at)
            self.repo.add_event(doc_id, "received", "ok",
                                f"{raw.source_channel}: {raw.source_ref}")
        try:
            return self._run(doc_id, raw, file_hash)
        except Exception as exc:   # PermanentError, exhausted TransientError, or anything unexpected
            reason = f"{type(exc).__name__}: {exc}"
            self.repo.update_document(doc_id, status="FAILED")
            self.repo.add_event(doc_id, "failed", "error", reason)
            self.repo.add_dead_letter(file_hash, raw.filename, reason, raw.source_channel)
            self.dead_letter.send(file_hash, raw.filename, reason, raw.source_channel)
            return "failed"

    def _run(self, doc_id: int, raw: RawDocument, file_hash: str) -> str:
        # 1. Stage raw file in the landing zone
        path = self.landing.store(raw, file_hash)
        self.repo.update_document(doc_id, landing_path=path)
        self.repo.add_event(doc_id, "staged", "ok", path)

        # 2. Normalize to standard format
        norm = normalize(raw)
        self.repo.update_document(doc_id, file_format=norm.file_format, page_count=norm.page_count)
        self.repo.add_event(doc_id, "normalized", "ok",
                            f"format={norm.file_format} needs_ocr={norm.needs_ocr}")

        # 3. Classify sensitivity
        label = classify(norm.text)
        self.repo.update_document(doc_id, sensitivity_label=label)
        self.repo.add_event(doc_id, "classified", "ok", label)

        # 4. Extract (retried on transient errors)
        result = self._extract(raw.filename, raw.content, norm)
        self.repo.add_event(doc_id, "extracted", "ok",
                            f"{len(result.fields)} fields via {result.model_id}@{result.model_version}")

        # 5. Validate
        v = validate(result, self.s.confidence_threshold)
        self.repo.save_fields(doc_id, result.fields, v.clean_values,
                              result.model_id, result.model_version)
        v_status = "ok" if v.passed else "warning"
        self.repo.add_event(doc_id, "validated", v_status, "; ".join(v.issues) or "all checks passed")

        # 6. Duplicate detection by business key (hash duplicates handled by idempotency)
        cv = v.clean_values
        if all(k in cv for k in ("document_number", "counterparty", "amount")):
            key = f"{cv['document_number']}|{cv['counterparty']}|{cv['amount']}"
            dup = self.repo.find_duplicate_by_key(key, doc_id)
            self.repo.update_document(doc_id, business_key=key)
            if dup:
                self.repo.update_document(doc_id, status="DUPLICATE", duplicate_of=dup["id"])
                self.repo.add_event(doc_id, "stored", "warning", f"duplicate of document {dup['id']}")
                return "duplicate"

        # 7. Route: clean -> COMPLETED, otherwise -> human review queue
        if v.needs_review:
            self.repo.update_document(doc_id, status="NEEDS_REVIEW")
            self.repo.add_review(doc_id, "; ".join(v.issues))
            outcome = "needs_review"
        else:
            self.repo.update_document(doc_id, status="COMPLETED")
            outcome = "completed"
        self.write_output(doc_id)
        self.repo.add_event(doc_id, "stored", "ok", f"outcome={outcome}")
        return outcome

    def write_output(self, doc_id: int) -> None:
        """Persist the structured JSON for downstream collateral / deal-hub consumers."""
        data = self.repo.build_output(doc_id)
        self.s.output_dir.mkdir(parents=True, exist_ok=True)
        (self.s.output_dir / f"{data['file_hash'][:12]}.json").write_text(json.dumps(data, indent=2))
