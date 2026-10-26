-- 1) "Where did this value in the deal hub come from?"
SELECT d.id, d.filename, d.source_channel, d.source_ref, d.landing_path,
       f.field_name, f.clean_value, f.confidence, f.page, f.model_id, f.model_version
FROM extracted_fields f JOIN documents d ON d.id = f.document_id
WHERE f.field_name = 'document_number' AND f.clean_value = 'INV-1001';

-- 2) Full journey of one document
SELECT stage, status, detail, created_at FROM lineage_events
WHERE document_id = 1 ORDER BY id;

-- 3) Documents waiting for human review
SELECT d.id, d.filename, r.reason, r.created_at
FROM review_queue r JOIN documents d ON d.id = r.document_id
WHERE r.status = 'PENDING';

-- 4) Who corrected what (audit trail)
SELECT ts, actor, document_id, field_name, old_value, new_value
FROM audit_log WHERE action = 'FIELD_CORRECTED' ORDER BY ts;

-- 5) Reconciliation: counts per status and channel
SELECT source_channel, status, COUNT(*) AS n FROM documents GROUP BY source_channel, status;

-- 6) Duplicate business keys
SELECT business_key, COUNT(*) AS n FROM documents
WHERE business_key IS NOT NULL GROUP BY business_key HAVING n > 1;
