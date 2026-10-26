"""All SQL lives here. Swap this class to target Azure SQL (pyodbc) in production."""
import json
import sqlite3
from typing import Any

from .. import PIPELINE_VERSION
from ..models import utcnow


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ---- documents ----
    def get_by_hash(self, file_hash: str):
        return self.conn.execute("SELECT * FROM documents WHERE file_hash=?", (file_hash,)).fetchone()

    def get_document(self, doc_id: int):
        return self.conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()

    def create_document(self, file_hash, filename, channel, source_ref, received_at) -> int:
        cur = self.conn.execute(
            "INSERT INTO documents (file_hash,filename,source_channel,source_ref,status,"
            "received_at,updated_at,pipeline_version) VALUES (?,?,?,?,?,?,?,?)",
            (file_hash, filename, channel, source_ref, "RECEIVED", received_at or utcnow(),
             utcnow(), PIPELINE_VERSION))
        self.conn.commit()
        return cur.lastrowid

    def update_document(self, doc_id: int, **cols: Any) -> None:
        cols["updated_at"] = utcnow()
        cols["pipeline_version"] = PIPELINE_VERSION
        sets = ", ".join(f"{k}=?" for k in cols)
        self.conn.execute(f"UPDATE documents SET {sets} WHERE id=?", (*cols.values(), doc_id))
        self.conn.commit()

    def reset_for_reprocess(self, doc_id: int) -> None:
        """Idempotent reprocessing: clear derived data, keep the document row + history."""
        self.conn.execute("DELETE FROM extracted_fields WHERE document_id=?", (doc_id,))
        self.conn.execute("DELETE FROM review_queue WHERE document_id=? AND status='PENDING'", (doc_id,))
        self.conn.commit()

    def find_duplicate_by_key(self, business_key: str, exclude_id: int):
        return self.conn.execute(
            "SELECT id FROM documents WHERE business_key=? AND id<>? "
            "AND status IN ('COMPLETED','NEEDS_REVIEW') ORDER BY id LIMIT 1",
            (business_key, exclude_id)).fetchone()

    # ---- fields ----
    def save_fields(self, doc_id, fields, clean_values, model_id, model_version) -> None:
        for f in fields:
            clean = clean_values.get(f.name)
            self.conn.execute(
                "INSERT OR REPLACE INTO extracted_fields (document_id,field_name,raw_value,"
                "clean_value,confidence,page,model_id,model_version) VALUES (?,?,?,?,?,?,?,?)",
                (doc_id, f.name, str(f.value), None if clean is None else str(clean),
                 f.confidence, f.page, model_id, model_version))
        self.conn.commit()

    def get_fields(self, doc_id: int):
        return self.conn.execute(
            "SELECT * FROM extracted_fields WHERE document_id=? ORDER BY id", (doc_id,)).fetchall()

    # ---- lineage / audit ----
    def add_event(self, doc_id: int, stage: str, status: str = "ok", detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO lineage_events (document_id,stage,status,detail,created_at,pipeline_version)"
            " VALUES (?,?,?,?,?,?)", (doc_id, stage, status, detail, utcnow(), PIPELINE_VERSION))
        self.conn.commit()

    def get_events(self, doc_id: int):
        return self.conn.execute(
            "SELECT * FROM lineage_events WHERE document_id=? ORDER BY id", (doc_id,)).fetchall()

    def add_audit(self, actor, action, doc_id=None, field=None, old=None, new=None) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (ts,actor,action,document_id,field_name,old_value,new_value)"
            " VALUES (?,?,?,?,?,?,?)", (utcnow(), actor, action, doc_id, field, old, new))
        self.conn.commit()

    # ---- review queue ----
    def add_review(self, doc_id: int, reason: str) -> None:
        self.conn.execute("INSERT INTO review_queue (document_id,reason,created_at) VALUES (?,?,?)",
                          (doc_id, reason, utcnow()))
        self.conn.commit()

    def pending_reviews(self):
        return self.conn.execute(
            "SELECT r.id AS review_id, d.id AS document_id, d.filename, r.reason, r.created_at "
            "FROM review_queue r JOIN documents d ON d.id=r.document_id "
            "WHERE r.status='PENDING' ORDER BY r.id").fetchall()

    def resolve_review(self, doc_id: int, reviewer: str) -> None:
        self.conn.execute("UPDATE review_queue SET status='RESOLVED', resolved_at=?, reviewer=? "
                          "WHERE document_id=? AND status='PENDING'", (utcnow(), reviewer, doc_id))
        self.conn.commit()

    # ---- dead letters ----
    def add_dead_letter(self, file_hash, filename, reason, channel) -> None:
        self.conn.execute(
            "INSERT INTO dead_letters (file_hash,filename,reason,source_channel,created_at)"
            " VALUES (?,?,?,?,?)", (file_hash, filename, reason, channel, utcnow()))
        self.conn.commit()

    # ---- reporting ----
    def status_report(self):
        return self.conn.execute(
            "SELECT source_channel, status, COUNT(*) AS n FROM documents "
            "GROUP BY source_channel, status ORDER BY source_channel, status").fetchall()

    def build_output(self, doc_id: int) -> dict:
        d = self.get_document(doc_id)
        return {
            "document_id": d["id"], "file_hash": d["file_hash"], "filename": d["filename"],
            "source_channel": d["source_channel"], "landing_path": d["landing_path"],
            "sensitivity_label": d["sensitivity_label"], "status": d["status"],
            "pipeline_version": d["pipeline_version"],
            "fields": {f["field_name"]: {"value": f["clean_value"], "confidence": f["confidence"],
                                         "page": f["page"], "model": f"{f['model_id']}@{f['model_version']}"}
                       for f in self.get_fields(doc_id)},
        }
