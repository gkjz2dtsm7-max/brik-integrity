"""Candidate URL order and safe upsert logging. Uses a fake password only."""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from urllib.parse import unquote, urlsplit

import usaspending_gulf_ms as ingest

PROJECT_REF = "hifuswqudwcvdtgvpbnh"
FAKE_PASSWORD = "pw-not-a-secret-xyz"
ENCODED_PASSWORD = "p%40ss%3Aword"
DIRECT_HOST = f"db.{PROJECT_REF}.supabase.co"
POOLER_HOSTS = (
    "aws-1-us-east-1.pooler.supabase.com",
    "aws-0-us-east-1.pooler.supabase.com",
)


def _direct_url(password: str = FAKE_PASSWORD, *, query: str = "", path: str = "/postgres", port: int = 5432) -> str:
    suffix = f"?{query}" if query else ""
    return f"postgresql://postgres:{password}@{DIRECT_HOST}:{port}{path}{suffix}"


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        return None

    def fetchall(self):
        return [("12045", "place-1"), ("28", "place-2")]


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _Cursor()


class _Error(Exception):
    def __init__(self, message: str = "", pgcode: str | None = None):
        super().__init__(message)
        self.pgcode = pgcode


class _OperationalError(_Error):
    pass


class _FakePsycopg:
    Error = _Error
    OperationalError = _OperationalError

    def __init__(self, fail_hosts: set[str] | None = None, pgcode: str | None = None):
        self.fail_hosts = fail_hosts or set()
        self.pgcode = pgcode
        self.calls: list[str] = []

    def connect(self, url: str):
        self.calls.append(url)
        host = urlsplit(url).hostname
        if host in self.fail_hosts:
            # Message deliberately contains the DSN. Logs must not echo it.
            raise _OperationalError(url, pgcode=self.pgcode)
        return _Conn()


class CandidateUrlTests(unittest.TestCase):
    def test_direct_url_prefers_session_poolers_then_original(self):
        original = _direct_url(ENCODED_PASSWORD, query="sslmode=require", path="/postgres", port=5432)
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            candidates = ingest.postgres_candidate_urls(original)

        self.assertEqual(buf.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[2], original)
        rendered = "\n".join(candidates)
        self.assertNotIn("p@ss:word", rendered)
        self.assertNotIn("%2540", rendered)

        first, second = candidates[0], candidates[1]
        for candidate, host in zip((first, second), POOLER_HOSTS):
            parts = urlsplit(candidate)
            self.assertEqual(parts.username, f"postgres.{PROJECT_REF}")
            self.assertEqual(unquote(parts.password), "p@ss:word")
            self.assertEqual(parts.hostname, host)
            self.assertEqual(parts.port, 5432)
            self.assertEqual(parts.path, "/postgres")
            self.assertEqual(parts.query, "sslmode=require")
            self.assertEqual(parts.password.count("@") if parts.password else 0, 0)

        self.assertEqual(urlsplit(original).hostname, DIRECT_HOST)
        self.assertEqual(urlsplit(original).username, "postgres")

    def test_ref_is_derived_not_hardcoded(self):
        ref = "a" * 20
        original = f"postgresql://postgres:secret@db.{ref}.supabase.co:6543/warehouse"
        candidates = ingest.postgres_candidate_urls(original)
        self.assertEqual(urlsplit(candidates[0]).username, f"postgres.{ref}")
        self.assertEqual(urlsplit(candidates[0]).port, 5432)
        self.assertEqual(urlsplit(candidates[0]).path, "/warehouse")
        self.assertEqual(urlsplit(candidates[2]).port, 6543)
        self.assertEqual(candidates[2], original)

    def test_existing_pooler_url_is_not_duplicated(self):
        original = (
            f"postgresql://postgres.{PROJECT_REF}:{FAKE_PASSWORD}"
            f"@{POOLER_HOSTS[0]}:5432/postgres"
        )
        candidates = ingest.postgres_candidate_urls(original)
        hosts = [urlsplit(url).hostname for url in candidates]
        self.assertEqual(hosts, list(POOLER_HOSTS))
        self.assertEqual(candidates[0], original)

    def test_plain_password_round_trip(self):
        original = _direct_url(FAKE_PASSWORD)
        candidates = ingest.postgres_candidate_urls(f"  {original}\n")
        self.assertEqual(unquote(urlsplit(candidates[0]).password), FAKE_PASSWORD)
        self.assertEqual(candidates[2], original)

    def test_non_supabase_url_is_unchanged(self):
        original = "postgresql://app:secret@db.internal:5432/app"
        self.assertEqual(ingest.postgres_candidate_urls(original), [original])

    def test_missing_password_does_not_invent_a_pooler_url(self):
        original = f"postgresql://postgres@{DIRECT_HOST}:5432/postgres"
        self.assertEqual(ingest.postgres_candidate_urls(original), [original])

    def test_blank_url(self):
        self.assertEqual(ingest.postgres_candidate_urls("  \n"), [])


class UpsertAttemptTests(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("DATABASE_URL")
        self._driver = ingest.psycopg2

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._previous
        ingest.psycopg2 = self._driver

    def _rows(self) -> list[dict]:
        return [
            {
                "Award ID": "ABC123",
                "_ingest_job": "gulf-county-fl-grants",
                "Award Amount": 10,
                "Description": "sample",
                "Awarding Agency": "agency",
                "Start Date": "2024-01-01",
                "End Date": "2024-12-31",
                "Recipient Name": "recipient",
            }
        ]

    def test_falls_through_poolers_then_direct(self):
        original = _direct_url()
        os.environ["DATABASE_URL"] = original
        fake = _FakePsycopg(fail_hosts=set(POOLER_HOSTS), pgcode="28P01")
        ingest.psycopg2 = fake
        err = io.StringIO()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            upserted = ingest.maybe_upsert_postgres(self._rows())
        self.assertEqual(upserted, 1)
        hosts = [urlsplit(url).hostname for url in fake.calls]
        self.assertEqual(hosts, [POOLER_HOSTS[0], POOLER_HOSTS[1], DIRECT_HOST])
        self.assertEqual(fake.calls[2], original)
        self.assertEqual(urlsplit(fake.calls[0]).username, f"postgres.{PROJECT_REF}")
        text = err.getvalue()
        self.assertEqual(text.count("trying next candidate"), 2)
        self.assertNotIn("JSONL only", text)
        self.assertIn("OperationalError", text)
        self.assertIn("pgcode=28P01", text)
        self.assertNotIn(FAKE_PASSWORD, text)
        self.assertNotIn(FAKE_PASSWORD, out.getvalue())
        self.assertNotIn("postgresql://", text)
        self.assertNotIn(DIRECT_HOST, text)
        self.assertNotIn(POOLER_HOSTS[0], text)

    def test_stops_after_first_success(self):
        os.environ["DATABASE_URL"] = _direct_url()
        fake = _FakePsycopg()
        ingest.psycopg2 = fake
        err = io.StringIO()
        with redirect_stderr(err):
            upserted = ingest.maybe_upsert_postgres(self._rows())
        self.assertEqual(upserted, 1)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(urlsplit(fake.calls[0]).hostname, POOLER_HOSTS[0])
        self.assertEqual(err.getvalue(), "")

    def test_all_candidates_fail_keeps_safe_log(self):
        os.environ["DATABASE_URL"] = _direct_url()
        fake = _FakePsycopg(
            fail_hosts={POOLER_HOSTS[0], POOLER_HOSTS[1], DIRECT_HOST},
            pgcode=None,
        )
        ingest.psycopg2 = fake
        err = io.StringIO()
        with redirect_stderr(err):
            upserted = ingest.maybe_upsert_postgres(self._rows())
        self.assertEqual(upserted, 0)
        self.assertEqual(len(fake.calls), 3)
        text = err.getvalue()
        self.assertEqual(text.count("JSONL only"), 1)
        self.assertEqual(text.count("trying next candidate"), 2)
        self.assertIn("pgcode=none", text)
        self.assertNotIn(FAKE_PASSWORD, text)
        self.assertNotIn("postgresql://", text)


class DerivationFailureRestoreTests(unittest.TestCase):
    """Separate so the monkeypatch cannot leak into other tests."""

    def setUp(self):
        self._previous = os.environ.get("DATABASE_URL")
        self._driver = ingest.psycopg2
        self._candidates = ingest.postgres_candidate_urls

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._previous
        ingest.psycopg2 = self._driver
        ingest.postgres_candidate_urls = self._candidates

    def test_derivation_failure_uses_original_and_hides_url(self):
        original = _direct_url()
        os.environ["DATABASE_URL"] = original

        def boom(url: str):
            raise RuntimeError(url)

        ingest.postgres_candidate_urls = boom
        fake = _FakePsycopg(fail_hosts={DIRECT_HOST}, pgcode=None)
        ingest.psycopg2 = fake
        err = io.StringIO()
        with redirect_stderr(err):
            upserted = ingest.maybe_upsert_postgres([])
        self.assertEqual(upserted, 0)
        self.assertEqual(fake.calls, [original])
        text = err.getvalue()
        self.assertIn("Postgres URL derivation failed (RuntimeError)", text)
        self.assertIn("pgcode=none", text)
        self.assertNotIn(FAKE_PASSWORD, text)
        self.assertNotIn("postgresql://", text)
        self.assertNotIn(DIRECT_HOST, text)


if __name__ == "__main__":
    unittest.main()
