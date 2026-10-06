#!/usr/bin/env python3
"""Pull award-level rows from USAspending for Gulf County FL + Mississippi.
Writes JSONL under ingest/out/ and optional Postgres upsert when DATABASE_URL is set.
One award-type group per API call (USAspending rule).
Never invents fields — Missing stays Missing.

spending_by_award is a top-N index. Award IDs from each successful job are stored in
ingest/out/prior_award_ids.json. IDs that disappear from a later search are read from
the award detail endpoint and kept on the same JSONL/upsert path with
_source=detail_fallback. JSONL stays off GitHub Pages.

GitHub-hosted runners are IPv4-only. db.<ref>.supabase.co is AAAA-only, so the
upsert tries the us-east-1 session pooler (IPv4) before the original URL.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

# Optional driver: JSONL ingest still runs when psycopg2 is not installed.
try:
    import psycopg2
except ImportError:
    psycopg2 = None

OUT = Path(__file__).resolve().parent / "out"
API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DETAIL_API = "https://api.usaspending.gov/api/v2/awards/"
PRIOR_IDS_PATH = OUT / "prior_award_ids.json"
SOURCE_SEARCH = "spending_by_award"
SOURCE_DETAIL = "detail_fallback"
# HHS assistance generated id, verified: ASST_NON_RHTCMS332063_075 returns the award
# while GET /awards/RHTCMS332063/ is 404 and spending_by_award award_ids returns 0.
HHS_ASSISTANCE_AGENCY = "075"
_GENERATED_AWARD_ID = re.compile(r"^(?:ASST_NON|ASST_AGG|CONT_AWD|CONT_IDV)_")
DetailFetcher = Callable[[str], tuple[dict | None, str]]

GROUPS = {
    "contracts": ["A", "B", "C", "D"],
    "grants": ["02", "03", "04", "05"],
    "loans": ["07", "08"],
    "direct_payments": ["06", "10"],
    "other": ["09", "11", "-1"],
}

# Seed geography: Gulf County FL (FIPS 12045 → county 045) + Mississippi statewide
GEOS = [
    {
        "slug": "gulf-county-fl",
        "page_limit": 10,
        "locations": [{"country": "USA", "state": "FL", "county": "045"}],
        "time_period": [{"start_date": "2020-10-01", "end_date": "2026-09-30"}],
    },
    {
        "slug": "mississippi",
        "page_limit": 5,
        "locations": [{"country": "USA", "state": "MS"}],
        "time_period": [{"start_date": "2024-10-01", "end_date": "2026-09-30"}],
    },
]

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Award Amount",
    "Total Outlays",
    "Description",
    "Awarding Agency",
    "Start Date",
    "End Date",
    "Place of Performance State Code",
    "Award Type",
]


def post(payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        API,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "brik-integrity-ingest/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def sort_field_for(name: str) -> str:
    # Loan awards reject "Award Amount" / "Face Value of Loan" as sort keys.
    return "Award ID" if name.endswith("-loans") else "Award Amount"


def annotate_search_row(row: dict, job: str, ingested_at: str) -> dict:
    row["_ingest_job"] = job
    row["_ingested_at"] = ingested_at
    row["_source"] = SOURCE_SEARCH
    return row


def fetch_all(name: str, filters: dict, page_limit: int = 20) -> tuple[list[dict], bool]:
    """Return (rows, ok). ok is False when a page request fails so a partial top-N is not treated as complete."""
    rows: list[dict] = []
    page = 1
    while page <= page_limit:
        body = {
            "filters": filters,
            "fields": FIELDS + (["Face Value of Loan"] if name.endswith("-loans") else []),
            # loans: Face Value is a field, not a valid sort
            "limit": 100,
            "page": page,
            "sort": sort_field_for(name),
            "order": "desc",
            "subawards": False,
        }
        try:
            result = post(body)
        except Exception as e:
            detail = ""
            if hasattr(e, "read"):
                try:
                    detail = e.read().decode()[:400]
                except Exception:
                    detail = str(e)
            print(f"ERROR {name} page {page}: {e} {detail}", file=sys.stderr)
            return rows, False
        batch = result.get("results") or []
        if not batch:
            return rows, True
        ingested_at = datetime.now(timezone.utc).isoformat()
        for r in batch:
            annotate_search_row(r, name, ingested_at)
            rows.append(r)
        print(f"{name} page {page}: +{len(batch)} (total {len(rows)})")
        if not result.get("page_metadata", {}).get("hasNext"):
            return rows, True
        page += 1
    return rows, True


def infer_award_type(job: str, row: dict) -> str | None:
    if job.endswith("-contracts"):
        return "contract"
    if job.endswith("-grants"):
        return "grant"
    if job.endswith("-loans"):
        return "loan"
    if job.endswith("-direct_payments"):
        return "direct_payment"
    if job.endswith("-other"):
        return "other"
    return row.get("Award Type")


def infer_geo(job: str) -> tuple[str | None, str | None, str | None]:
    """state, county, fips_code for seed places."""
    if job.startswith("gulf-county-fl"):
        return "FL", "Gulf", "12045"
    if job.startswith("mississippi"):
        return "MS", None, "28"
    return None, None, None


def award_id_of(row: dict) -> str:
    value = row.get("Award ID")
    if value is None:
        return ""
    return str(value).strip()


def missing_award_ids(prior: set[str], today_rows: list[dict]) -> list[str]:
    """Award IDs tracked for this job that spending_by_award did not return today."""
    today = {award_id_of(row) for row in today_rows}
    today.discard("")
    return sorted((prior or set()) - today)


def detail_candidate_ids(award_id: str, job: str) -> list[str]:
    """Detail path ids. Grants without a generated id use ASST_NON_<FAIN>_075."""
    cleaned = award_id.strip()
    if not cleaned:
        return []
    if _GENERATED_AWARD_ID.match(cleaned):
        return [cleaned]
    if job.endswith("-grants"):
        return [f"ASST_NON_{cleaned}_{HHS_ASSISTANCE_AGENCY}"]
    return []


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def map_detail_to_row(
    detail: dict,
    job: str,
    award_id: str,
    ingested_at: str,
    fetched_id: str | None = None,
) -> dict | None:
    """Map an award-detail payload onto the spending_by_award row keys.

    Only copies values the detail payload actually carries. Null stays null.
    """
    if not isinstance(detail, dict):
        return None
    fain = detail.get("fain")
    fain_id = fain.strip() if isinstance(fain, str) else ""
    api_generated = detail.get("generated_unique_award_id")
    api_generated_id = api_generated.strip() if isinstance(api_generated, str) else ""
    # Identity has to come from the payload. The URL we called is not enough.
    if not fain_id and not api_generated_id:
        return None
    mapped_id = fain_id or award_id.strip()
    if not mapped_id:
        return None
    generated = api_generated_id or fetched_id
    recipient = _as_dict(detail.get("recipient"))
    period = _as_dict(detail.get("period_of_performance"))
    place = _as_dict(detail.get("place_of_performance"))
    agency = _as_dict(_as_dict(detail.get("awarding_agency")).get("toptier_agency"))
    return {
        "Award ID": mapped_id,
        "Recipient Name": recipient.get("recipient_name"),
        "Award Amount": detail.get("total_obligation"),
        "Total Outlays": detail.get("total_outlay"),
        "Description": detail.get("description"),
        "Awarding Agency": agency.get("name"),
        "Start Date": period.get("start_date"),
        "End Date": period.get("end_date"),
        "Place of Performance State Code": place.get("state_code"),
        "Award Type": detail.get("type_description"),
        "generated_internal_id": generated,
        "internal_id": detail.get("id"),
        "_ingest_job": job,
        "_ingested_at": ingested_at,
        "_source": SOURCE_DETAIL,
    }


def merge_search_and_fallback(search_rows: list[dict], fallback_rows: list[dict]) -> list[dict]:
    """Keep search rows first. A detail row whose Award ID is already present is dropped."""
    seen = {award_id_of(row) for row in search_rows}
    seen.discard("")
    merged = list(search_rows)
    for row in fallback_rows:
        award_id = award_id_of(row)
        if not award_id or award_id in seen:
            continue
        seen.add(award_id)
        merged.append(row)
    return merged


def next_prior_ids(search_rows: list[dict], fallback_rows: list[dict], retry_ids: set[str]) -> set[str]:
    """IDs to track after a successful job: today's search, recovered detail rows, and transient misses."""
    ids = {award_id_of(row) for row in search_rows}
    ids.discard("")
    for row in fallback_rows:
        award_id = award_id_of(row)
        if award_id:
            ids.add(award_id)
    ids.update(award_id.strip() for award_id in retry_ids if award_id and award_id.strip())
    return ids


def apply_job_fallback(
    job: str,
    prior_ids: set[str],
    search_rows: list[dict],
    *,
    fetch_detail: DetailFetcher,
    ingested_at: str | None = None,
) -> tuple[list[dict], set[str]]:
    """Fetch detail rows for this job's missing IDs and return merged rows plus the next prior set."""
    stamped = ingested_at or datetime.now(timezone.utc).isoformat()
    missing = missing_award_ids(prior_ids, search_rows)
    search_ids = {award_id_of(row) for row in search_rows}
    search_ids.discard("")
    fallback: list[dict] = []
    retry: set[str] = set()
    for award_id in missing:
        candidates = detail_candidate_ids(award_id, job)
        if not candidates:
            continue
        for candidate in candidates:
            payload, outcome = fetch_detail(candidate)
            if outcome == "gone":
                continue
            if outcome != "ok":
                retry.add(award_id)
                break
            row = map_detail_to_row(payload or {}, job, award_id, stamped, fetched_id=candidate)
            if row is None:
                retry.add(award_id)
                break
            mapped_id = award_id_of(row)
            if mapped_id in search_ids or any(award_id_of(existing) == mapped_id for existing in fallback):
                break
            fallback.append(row)
            break
    merged = merge_search_and_fallback(search_rows, fallback)
    return merged, next_prior_ids(search_rows, fallback, retry)


def detail_error_outcome(exc: BaseException) -> str:
    """404/400/410 means the generated id is not an award. Anything else is retried next run."""
    code = getattr(exc, "code", None)
    if code in (400, 404, 410):
        return "gone"
    return "retry"


def fetch_award_detail(generated_id: str) -> tuple[dict | None, str]:
    """GET /api/v2/awards/<generated_unique_award_id>/. Logs status only, never a URL or secret."""
    url = f"{DETAIL_API}{quote(generated_id, safe='')}/"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "brik-integrity-ingest/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as exc:
        outcome = detail_error_outcome(exc)
        code = getattr(exc, "code", None)
        status = code if isinstance(code, int) else type(exc).__name__
        print(f"detail fallback {outcome} ({status})", file=sys.stderr)
        return None, outcome
    if not isinstance(payload, dict):
        print("detail fallback retry (invalid payload)", file=sys.stderr)
        return None, "retry"
    return payload, "ok"


def load_prior_award_ids(path: Path | None = None) -> dict[str, set[str]]:
    """Per-job Award IDs. A missing or unreadable file seeds an empty set."""
    path = path or PRIOR_IDS_PATH
    if not path.is_file():
        print(f"prior award ids missing ({path.name}); seeding empty")
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"prior award ids unreadable ({type(exc).__name__}); seeding empty", file=sys.stderr)
        return {}
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, dict):
        print("prior award ids missing jobs object; seeding empty", file=sys.stderr)
        return {}
    parsed: dict[str, set[str]] = {}
    for job, raw_ids in jobs.items():
        if not isinstance(job, str) or not isinstance(raw_ids, list):
            continue
        parsed[job] = {
            str(award_id).strip()
            for award_id in raw_ids
            if award_id is not None and str(award_id).strip()
        }
    return parsed


def save_prior_award_ids(ids_by_job: dict[str, set[str]], path: Path | None = None) -> None:
    path = path or PRIOR_IDS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"jobs": {job: sorted(ids) for job, ids in sorted(ids_by_job.items())}}
    path.write_text(json.dumps(payload, indent=2) + "\n")


# IPv4 session poolers for the us-east-1 Supabase project. Port 5432 is session
# mode. Tried before the direct host, which publishes only AAAA.
_SESSION_POOLER_HOSTS = (
    "aws-1-us-east-1.pooler.supabase.com",
    "aws-0-us-east-1.pooler.supabase.com",
)
_SESSION_POOLER_PORT = 5432
_DIRECT_HOST = re.compile(r"^db\.([a-z0-9]{20})\.supabase\.co$")
_POOLER_USER = re.compile(r"^postgres\.([a-z0-9]{20})$")
_EndpointKey = tuple[str, str | None, str, int, str, str]


def _split_userinfo(netloc: str) -> tuple[str, str | None]:
    """Raw user and password substrings from a netloc. Password is not decoded."""
    if "@" not in netloc:
        return "", None
    userinfo, _host = netloc.rsplit("@", 1)
    if ":" not in userinfo:
        return userinfo, None
    user, password = userinfo.split(":", 1)
    return user, password


def _quote_password(raw_password: str) -> str:
    """Encode a password for userinfo without double-encoding %XX sequences."""
    return quote(unquote(raw_password), safe="")


def _supabase_project_ref(database_url: str) -> str | None:
    parts = urlsplit(database_url)
    host_match = _DIRECT_HOST.fullmatch((parts.hostname or "").lower())
    if host_match:
        return host_match.group(1)
    raw_user, _password = _split_userinfo(parts.netloc)
    user_match = _POOLER_USER.fullmatch(unquote(raw_user))
    if user_match:
        return user_match.group(1)
    return None


def _endpoint_key(database_url: str) -> _EndpointKey:
    parts = urlsplit(database_url)
    raw_user, raw_password = _split_userinfo(parts.netloc)
    password = None if raw_password is None else unquote(raw_password)
    return (
        unquote(raw_user),
        password,
        (parts.hostname or "").lower(),
        parts.port or _SESSION_POOLER_PORT,
        parts.path or "",
        parts.query,
    )


def _session_pooler_url(database_url: str, ref: str, host: str, raw_password: str) -> str:
    parts = urlsplit(database_url)
    username = quote(f"postgres.{ref}", safe="")
    netloc = f"{username}:{_quote_password(raw_password)}@{host}:{_SESSION_POOLER_PORT}"
    path = parts.path or "/postgres"
    scheme = parts.scheme or "postgresql"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def postgres_candidate_urls(database_url: str) -> list[str]:
    """Session-pooler URLs first, then the original DATABASE_URL.

    Does not print the URL or the password. Non-Supabase URLs are returned unchanged.
    """
    original = database_url.strip()
    if not original:
        return []
    parts = urlsplit(original)
    ref = _supabase_project_ref(original)
    _raw_user, raw_password = _split_userinfo(parts.netloc)
    if ref is None or raw_password is None:
        return [original]

    candidates: list[str] = []
    seen: set[_EndpointKey] = set()
    for host in _SESSION_POOLER_HOSTS:
        candidate = _session_pooler_url(original, ref, host, raw_password)
        key = _endpoint_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    if _endpoint_key(original) not in seen:
        candidates.append(original)
    return candidates


def _log_pg_failure(exc: BaseException, *, final: bool) -> None:
    """Log exception type and pgcode only. Never the DSN, URL, or password."""
    pgcode = getattr(exc, "pgcode", None) or "none"
    detail = f"Postgres upsert failed ({type(exc).__name__}, pgcode={pgcode})"
    if final:
        print(f"{detail} — JSONL only", file=sys.stderr)
        return
    print(f"{detail}; trying next candidate", file=sys.stderr)


def _upsert_rows(conn, rows: list[dict]) -> int:
    with conn.cursor() as cur:
        # ensure seed places exist
        cur.execute(
            """
            INSERT INTO places (fips_code, name, state, county, type) VALUES
              ('12045', 'Gulf County', 'FL', 'Gulf', 'county'),
              ('28', 'Mississippi', 'MS', NULL, 'state')
            ON CONFLICT (fips_code) DO NOTHING
            """
        )
        place_ids: dict[str, str] = {}
        cur.execute("SELECT fips_code, id FROM places WHERE fips_code IN ('12045','28')")
        for fips, pid in cur.fetchall():
            place_ids[str(fips)] = str(pid)

        n = 0
        for r in rows:
            source_id = str(r.get("Award ID") or r.get("generated_internal_id") or "")
            if not source_id:
                continue
            job = str(r.get("_ingest_job") or "")
            state, county, fips = infer_geo(job)
            place_id = place_ids.get(fips or "")
            amount = r.get("Award Amount")
            if amount is None and job.endswith("-loans"):
                amount = r.get("Face Value of Loan")
            cur.execute(
                """
                INSERT INTO awards (
                  usaspending_id, award_type, title, description, agency_name,
                  amount, start_date, end_date, recipient_name, place_id,
                  fips_code, state, county, url, last_updated
                ) VALUES (
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, now()
                )
                ON CONFLICT (usaspending_id) DO UPDATE SET
                  amount = EXCLUDED.amount,
                  description = EXCLUDED.description,
                  agency_name = EXCLUDED.agency_name,
                  last_updated = now()
                """,
                (
                    source_id,
                    infer_award_type(job, r),
                    (r.get("Description") or "")[:500] or None,
                    r.get("Description"),
                    r.get("Awarding Agency"),
                    amount,
                    r.get("Start Date") or None,
                    r.get("End Date") or None,
                    r.get("Recipient Name"),
                    place_id,
                    fips,
                    state or r.get("Place of Performance State Code"),
                    county,
                    f"https://www.usaspending.gov/award/{source_id}" if source_id else None,
                ),
            )
            n += 1
        return n


def maybe_upsert_postgres(rows: list[dict]) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL unset — wrote JSONL only")
        return 0
    if psycopg2 is None:
        print("psycopg2 not installed — JSONL only", file=sys.stderr)
        return 0
    try:
        candidates = postgres_candidate_urls(url)
    except Exception as exc:
        print(
            f"Postgres URL derivation failed ({type(exc).__name__}); using DATABASE_URL",
            file=sys.stderr,
        )
        candidates = [url]
    if not candidates:
        candidates = [url]
    for index, candidate in enumerate(candidates):
        try:
            with psycopg2.connect(candidate) as conn:
                return _upsert_rows(conn, rows)
        except psycopg2.Error as exc:
            _log_pg_failure(exc, final=index == len(candidates) - 1)
    return 0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    prior = load_prior_award_ids()
    updated: dict[str, set[str]] = {job: set(ids) for job, ids in prior.items()}
    all_rows: list[dict] = []
    jobs = []
    any_success = False
    for geo in GEOS:
        for group_name, codes in GROUPS.items():
            name = f"{geo['slug']}-{group_name}"
            jobs.append(name)
            filters = {
                "award_type_codes": codes,
                "place_of_performance_locations": geo["locations"],
                "time_period": geo["time_period"],
            }
            search_rows, ok = fetch_all(name, filters, page_limit=geo["page_limit"])
            rows = search_rows
            if ok:
                any_success = True
                job_prior = prior.get(name, set())
                rows, nxt = apply_job_fallback(
                    name,
                    job_prior,
                    search_rows,
                    fetch_detail=fetch_award_detail,
                )
                updated[name] = nxt
                recovered = sum(1 for row in rows if row.get("_source") == SOURCE_DETAIL)
                print(
                    f"{name} detail_fallback missing={len(missing_award_ids(job_prior, search_rows))} "
                    f"recovered={recovered} tracking={len(nxt)}"
                )
            else:
                print(f"{name} search failed; prior award ids unchanged", file=sys.stderr)
            path = OUT / f"{name}.jsonl"
            with path.open("w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
            print(f"wrote {path.name} ({len(rows)} rows)")
            all_rows.extend(rows)
    if any_success:
        save_prior_award_ids(updated)
        print(f"wrote {PRIOR_IDS_PATH.name} ({sum(len(ids) for ids in updated.values())} ids)")
    stamped = OUT / f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    stamped.write_text(json.dumps({"rows": len(all_rows), "jobs": jobs}, indent=2))
    upserted = maybe_upsert_postgres(all_rows)
    print(f"done rows={len(all_rows)} upserted={upserted}")
    return 0 if all_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
