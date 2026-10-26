# Design decisions

1. **Plug-in architecture.** `Connector`, `LandingZone`, extractor and `DeadLetterSink` are small interfaces.
   Local and Azure implementations are swapped in `factory.py`, so the core (`pipeline.py`) is testable offline.
2. **One standard format.** Every file becomes plain text (`NormalizedDocument`), so one extraction/validation path serves all formats.
3. **Hash = idempotency key.** SHA-256 of raw bytes uniquely identifies a document.
4. **Errors are typed.** `TransientError` -> retry; `PermanentError` -> dead letter.
5. **Everything is recorded.** Each stage writes a `lineage_events` row; human edits write `audit_log` rows.
6. **Validate before trusting.** Raw extracted values are kept (`raw_value`) beside cleaned ones (`clean_value`).
7. **Statuses:** RECEIVED -> COMPLETED | NEEDS_REVIEW | DUPLICATE | FAILED.
