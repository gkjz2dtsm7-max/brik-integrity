"""Candidate URL order and safe upsert logging. Uses a fake password only."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
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


class _StatusError(Exception):
    def __init__(self, code: int, message: str = ""):
        super().__init__(message)
        self.code = code


class MissingAwardIdTests(unittest.TestCase):
    def test_missing_is_prior_minus_today_for_one_job(self):
        today = [
            {"Award ID": "STAY"},
            {"Award ID": " ALSO "},
            {"Award ID": None},
            {"Award ID": ""},
        ]
        missing = ingest.missing_award_ids({"STAY", "ALSO", "RHTCMS332063", "GONE"}, today)
        self.assertEqual(missing, ["GONE", "RHTCMS332063"])

    def test_empty_prior_detects_nothing(self):
        self.assertEqual(ingest.missing_award_ids(set(), [{"Award ID": "STAY"}]), [])


class DetailMappingTests(unittest.TestCase):
    def _rhtcms(self) -> dict:
        return {
            "id": 354136784,
            "generated_unique_award_id": "ASST_NON_RHTCMS332063_075",
            "fain": "RHTCMS332063",
            "category": "grant",
            "type": "F002",
            "type_description": "COOPERATIVE AGREEMENT",
            "description": "THE MS RHTP",
            "total_obligation": 205907220.16,
            "total_funding": 205907220.16,
            "total_outlay": None,
            "total_account_outlay": 0.0,
            "awarding_agency": {
                "toptier_agency": {
                    "name": "Department of Health and Human Services",
                    "code": "075",
                }
            },
            "period_of_performance": {"start_date": "2025-12-29", "end_date": "2030-10-30"},
            "recipient": {
                "recipient_name": "EXECUTIVE OFFICE OF THE STATE OF MISSISSIPPI",
                "location": {"state_code": "MS"},
            },
            "place_of_performance": {"state_code": "MS"},
        }

    def test_maps_detail_fields_without_filling_nulls(self):
        row = ingest.map_detail_to_row(
            self._rhtcms(),
            "mississippi-grants",
            "RHTCMS332063",
            "2026-10-06T00:00:00+00:00",
            fetched_id="ASST_NON_RHTCMS332063_075",
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["Award ID"], "RHTCMS332063")
        self.assertEqual(row["Recipient Name"], "EXECUTIVE OFFICE OF THE STATE OF MISSISSIPPI")
        self.assertEqual(row["Award Amount"], 205907220.16)
        self.assertIsNone(row["Total Outlays"])
        self.assertEqual(row["Description"], "THE MS RHTP")
        self.assertEqual(row["Awarding Agency"], "Department of Health and Human Services")
        self.assertEqual(row["Start Date"], "2025-12-29")
        self.assertEqual(row["End Date"], "2030-10-30")
        self.assertEqual(row["Place of Performance State Code"], "MS")
        self.assertEqual(row["Award Type"], "COOPERATIVE AGREEMENT")
        self.assertEqual(row["generated_internal_id"], "ASST_NON_RHTCMS332063_075")
        self.assertEqual(row["internal_id"], 354136784)
        self.assertEqual(row["_ingest_job"], "mississippi-grants")
        self.assertEqual(row["_source"], "detail_fallback")

    def test_does_not_borrow_funding_outlay_or_recipient_state(self):
        row = ingest.map_detail_to_row(
            {
                "fain": "ONLYFAIN",
                "total_funding": 10,
                "total_account_outlay": 0.0,
                "recipient": {"recipient_name": "REC", "location": {"state_code": "MS"}},
                "place_of_performance": {},
            },
            "mississippi-grants",
            "ONLYFAIN",
            "2026-10-06T00:00:00+00:00",
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertIsNone(row["Award Amount"])
        self.assertIsNone(row["Total Outlays"])
        self.assertIsNone(row["Place of Performance State Code"])
        self.assertIsNone(row["Awarding Agency"])
        self.assertEqual(row["_source"], ingest.SOURCE_DETAIL)

    def test_payload_without_award_identity_is_not_a_row(self):
        self.assertIsNone(
            ingest.map_detail_to_row(
                {"total_funding": 10, "description": "not an award"},
                "mississippi-grants",
                "RHTCMS332063",
                "2026-10-06T00:00:00+00:00",
                fetched_id="ASST_NON_RHTCMS332063_075",
            )
        )

    def test_grant_fain_uses_hhs_generated_id(self):
        self.assertEqual(
            ingest.detail_candidate_ids("RHTCMS332063", "mississippi-grants"),
            ["ASST_NON_RHTCMS332063_075"],
        )
        self.assertEqual(
            ingest.detail_candidate_ids("ASST_NON_RHTCMS332063_075", "mississippi-grants"),
            ["ASST_NON_RHTCMS332063_075"],
        )

    def test_non_grant_jobs_are_not_refetched(self):
        self.assertEqual(ingest.detail_candidate_ids("PIID123", "mississippi-contracts"), [])
        self.assertEqual(ingest.detail_candidate_ids("PIID123", "gulf-county-fl-loans"), [])


class DetailFallbackMergeTests(unittest.TestCase):
    def test_search_rows_are_not_double_counted(self):
        calls: list[str] = []

        def fetch(generated_id: str):
            calls.append(generated_id)
            if generated_id == "ASST_NON_KEEP_075":
                return (
                    {
                        "id": 9,
                        "fain": "KEEP",
                        "generated_unique_award_id": generated_id,
                        "type_description": "PROJECT GRANT (C)",
                        "description": "kept",
                        "total_obligation": 5,
                        "total_outlay": None,
                        "recipient": {"recipient_name": "REC"},
                        "awarding_agency": {
                            "toptier_agency": {"name": "Department of Health and Human Services"}
                        },
                        "period_of_performance": {"start_date": "2025-01-01", "end_date": "2026-01-01"},
                        "place_of_performance": {"state_code": "MS"},
                    },
                    "ok",
                )
            if generated_id == "ASST_NON_DUPE_075":
                return ({"fain": "STAY", "total_obligation": 99, "description": "duplicate"}, "ok")
            return (None, "gone")

        search = [
            {
                "Award ID": "STAY",
                "Award Amount": 1,
                "_source": ingest.SOURCE_SEARCH,
                "_ingest_job": "mississippi-grants",
            },
            {
                "Award ID": "ALSO",
                "Award Amount": 2,
                "_source": ingest.SOURCE_SEARCH,
                "_ingest_job": "mississippi-grants",
            },
        ]
        merged, nxt = ingest.apply_job_fallback(
            "mississippi-grants",
            {"STAY", "KEEP", "GONE", "DUPE"},
            search,
            fetch_detail=fetch,
            ingested_at="2026-10-06T00:00:00+00:00",
        )
        self.assertEqual(calls, ["ASST_NON_DUPE_075", "ASST_NON_GONE_075", "ASST_NON_KEEP_075"])
        self.assertEqual([row["Award ID"] for row in merged], ["STAY", "ALSO", "KEEP"])
        self.assertEqual(sum(1 for row in merged if row["Award ID"] == "STAY"), 1)
        stay = merged[0]
        self.assertEqual(stay["_source"], "spending_by_award")
        self.assertEqual(stay["Award Amount"], 1)
        self.assertEqual(merged[-1]["_source"], "detail_fallback")
        self.assertEqual(merged[-1]["Award Amount"], 5)
        self.assertIsNone(merged[-1]["Total Outlays"])
        self.assertEqual(nxt, {"ALSO", "KEEP", "STAY"})

    def test_transient_detail_failure_stays_tracked_and_404_does_not(self):
        def fetch(generated_id: str):
            if generated_id.endswith("RETRY_075"):
                return (None, "retry")
            return (None, "gone")

        search = [{"Award ID": "TODAY", "_source": ingest.SOURCE_SEARCH}]
        merged, nxt = ingest.apply_job_fallback(
            "mississippi-grants",
            {"TODAY", "RETRY", "GONE"},
            search,
            fetch_detail=fetch,
            ingested_at="2026-10-06T00:00:00+00:00",
        )
        self.assertEqual([row["Award ID"] for row in merged], ["TODAY"])
        self.assertEqual(merged[0]["_source"], ingest.SOURCE_SEARCH)
        self.assertEqual(nxt, {"RETRY", "TODAY"})

    def test_contract_drop_is_not_fetched(self):
        def fetch(generated_id: str):
            raise AssertionError(generated_id)

        search = [{"Award ID": "NEW", "_source": ingest.SOURCE_SEARCH}]
        merged, nxt = ingest.apply_job_fallback(
            "mississippi-contracts",
            {"OLD", "NEW"},
            search,
            fetch_detail=fetch,
            ingested_at="2026-10-06T00:00:00+00:00",
        )
        self.assertEqual([row["Award ID"] for row in merged], ["NEW"])
        self.assertEqual(nxt, {"NEW"})


class PriorAwardIdStoreTests(unittest.TestCase):
    def test_missing_file_seeds_empty(self):
        missing = ingest.OUT / "does-not-exist-prior.json"
        out = io.StringIO()
        with redirect_stdout(out):
            loaded = ingest.load_prior_award_ids(missing)
        self.assertEqual(loaded, {})
        self.assertIn("seeding empty", out.getvalue())
        self.assertNotIn(str(missing.parent), out.getvalue())

    def test_round_trip_sorts_jobs_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prior_award_ids.json"
            ingest.save_prior_award_ids(
                {"mississippi-grants": {"B", "A"}, "gulf-county-fl-grants": {"C"}},
                path,
            )
            loaded = ingest.load_prior_award_ids(path)
            self.assertEqual(loaded["mississippi-grants"], {"A", "B"})
            self.assertEqual(json.loads(path.read_text())["jobs"]["mississippi-grants"], ["A", "B"])

    def test_corrupt_file_seeds_empty_without_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prior_award_ids.json"
            path.write_text("{not json secret-token")
            err = io.StringIO()
            with redirect_stderr(err):
                loaded = ingest.load_prior_award_ids(path)
            self.assertEqual(loaded, {})
            text = err.getvalue()
            self.assertIn("JSONDecodeError", text)
            self.assertNotIn("secret-token", text)


class DetailFetchLogTests(unittest.TestCase):
    def setUp(self):
        self._urlopen = ingest.urllib.request.urlopen

    def tearDown(self):
        ingest.urllib.request.urlopen = self._urlopen

    def test_failure_log_has_status_only(self):
        secret = "pw-not-a-secret-xyz"

        def boom(req, timeout=120):
            raise _StatusError(503, f"postgresql://postgres:{secret}@db.example {req.full_url}")

        ingest.urllib.request.urlopen = boom
        err = io.StringIO()
        with redirect_stderr(err):
            payload, outcome = ingest.fetch_award_detail("ASST_NON_RHTCMS332063_075")
        self.assertIsNone(payload)
        self.assertEqual(outcome, "retry")
        text = err.getvalue()
        self.assertIn("503", text)
        self.assertNotIn(secret, text)
        self.assertNotIn("postgresql://", text)
        self.assertNotIn("usaspending.gov", text)
        self.assertNotIn("RHTCMS332063", text)

    def test_not_found_is_gone_and_log_omits_body(self):
        def boom(req, timeout=120):
            raise _StatusError(404, "no such award secret-body")

        ingest.urllib.request.urlopen = boom
        err = io.StringIO()
        with redirect_stderr(err):
            payload, outcome = ingest.fetch_award_detail("ASST_NON_MISSING_075")
        self.assertIsNone(payload)
        self.assertEqual(outcome, "gone")
        self.assertNotIn("secret-body", err.getvalue())
        self.assertIn("404", err.getvalue())


if __name__ == "__main__":
    unittest.main()
