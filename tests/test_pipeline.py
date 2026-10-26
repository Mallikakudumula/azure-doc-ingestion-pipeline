"""Run with:  python -m unittest discover -s tests -v   (or: pytest)"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docpipe.classification.classifier import can_read, classify
from docpipe.config import Settings
from docpipe.extraction.mock_extractor import MockExtractor
from docpipe.landing.landing_zone import LocalLandingZone
from docpipe.models import ExtractedField, ExtractionResult, PermanentError, RawDocument, TransientError
from docpipe.normalize.normalizer import normalize
from docpipe.pipeline import Pipeline
from docpipe.resilience.dead_letter import LocalDeadLetter
from docpipe.resilience.retry import retry
from docpipe.storage.database import connect
from docpipe.storage.repository import Repository
from docpipe.validation.validator import parse_amount, parse_date, validate

GOOD = b"Invoice Number: INV-1\nVendor: Acme\nDate: 2025-01-31\nTotal: 1,000.50\nCurrency: USD\n"


def make_pipeline(tmp: Path, extractor=None) -> Pipeline:
    s = Settings(data_dir=tmp, max_retries=3)
    return Pipeline(s, Repository(connect(s.db_path)), LocalLandingZone(s.landing_dir),
                    extractor or MockExtractor(), LocalDeadLetter(s.dead_letter_dir), sleep=lambda _: None)


def raw(name: str, content: bytes, channel="email") -> RawDocument:
    return RawDocument(name, content, channel, name)


class NormalizerTests(unittest.TestCase):
    def test_csv_and_json(self):
        self.assertIn("Total: 5", normalize(raw("a.csv", b"Total,Vendor\n5,X\n")).text)
        self.assertIn("amount: 9", normalize(raw("a.json", b'{"amount": 9}')).text)

    def test_corrupt_and_unsupported(self):
        with self.assertRaises(PermanentError):
            normalize(raw("a.pdf", b"garbage"))
        with self.assertRaises(PermanentError):
            normalize(raw("a.exe", b"x"))

    def test_image_needs_ocr(self):
        self.assertTrue(normalize(raw("a.png", b"x")).needs_ocr)


class ValidatorTests(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(parse_amount("$1,234.50"), 1234.5)
        self.assertEqual(parse_date("14/03/2025"), "2025-03-14")

    def test_missing_and_low_confidence(self):
        r = ExtractionResult([ExtractedField("amount", "10", 0.5)], "m", "1")
        v = validate(r, 0.85)
        self.assertTrue(v.needs_review)
        self.assertTrue(any(i.startswith("missing_required_field") for i in v.issues))
        self.assertTrue(any(i.startswith("low_confidence") for i in v.issues))


class ClassifierTests(unittest.TestCase):
    def test_labels_and_rbac(self):
        self.assertEqual(classify("Account Number: 123456789012"), "Highly Confidential")
        self.assertEqual(classify("hello world"), "Internal")
        self.assertFalse(can_read("analyst", "Confidential"))
        self.assertTrue(can_read("compliance", "Highly Confidential"))


class RetryTests(unittest.TestCase):
    def test_retries_transient_then_succeeds(self):
        calls = {"n": 0}

        @retry(max_attempts=3, sleep=lambda _: None)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TransientError("timeout")
            return "ok"
        self.assertEqual(flaky(), "ok")
        self.assertEqual(calls["n"], 3)

    def test_permanent_not_retried(self):
        calls = {"n": 0}

        @retry(max_attempts=3, sleep=lambda _: None)
        def bad():
            calls["n"] += 1
            raise PermanentError("nope")
        with self.assertRaises(PermanentError):
            bad()
        self.assertEqual(calls["n"], 1)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        for p in self.tmp.rglob("*"):
            try: p.chmod(0o700)
            except OSError: pass
        self._tmp.cleanup()

    def test_happy_path_writes_json(self):
        p = make_pipeline(self.tmp)
        self.assertEqual(p.process(raw("i.txt", GOOD)), "completed")
        out = json.loads(next(p.s.output_dir.glob("*.json")).read_text())
        self.assertEqual(out["fields"]["amount"]["value"], "1000.5")

    def test_idempotent_same_bytes_skipped(self):
        p = make_pipeline(self.tmp)
        p.process(raw("i.txt", GOOD))
        self.assertEqual(p.process(raw("copy.txt", GOOD, "portal")), "skipped")
        self.assertEqual(p.repo.conn.execute("select count(*) from documents").fetchone()[0], 1)

    def test_business_key_duplicate(self):
        p = make_pipeline(self.tmp)
        p.process(raw("i.txt", GOOD))
        self.assertEqual(p.process(raw("j.txt", GOOD + b"\n")), "duplicate")

    def test_low_confidence_goes_to_review(self):
        p = make_pipeline(self.tmp)
        bad = GOOD.replace(b"1,000.50", b"1,O00.50")
        self.assertEqual(p.process(raw("i.txt", bad)), "needs_review")
        self.assertEqual(len(p.repo.pending_reviews()), 1)

    def test_corrupt_file_dead_lettered(self):
        p = make_pipeline(self.tmp)
        self.assertEqual(p.process(raw("x.pdf", b"junk")), "failed")
        self.assertEqual(len(list(p.s.dead_letter_dir.glob("*.json"))), 1)

    def test_transient_failure_recovers_via_retry(self):
        class Flaky(MockExtractor):
            n = 0
            def extract(self, *a):
                Flaky.n += 1
                if Flaky.n < 3:
                    raise TransientError("429")
                return super().extract(*a)
        p = make_pipeline(self.tmp, Flaky())
        self.assertEqual(p.process(raw("i.txt", GOOD)), "completed")

    def test_failed_file_is_reprocessed_on_next_run(self):
        class Down(MockExtractor):
            def extract(self, *a): raise TransientError("service down")
        p = make_pipeline(self.tmp, Down())
        self.assertEqual(p.process(raw("i.txt", GOOD)), "failed")
        p.extractor = p._extract = MockExtractor().extract       # service is back
        self.assertEqual(p.process(raw("i.txt", GOOD)), "completed")


if __name__ == "__main__":
    unittest.main()
