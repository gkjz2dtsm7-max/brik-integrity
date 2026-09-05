#!/usr/bin/env python3
"""Pull award-level rows from USAspending for Gulf County FL + Mississippi.
Writes JSONL under ingest/out/ and optional Postgres upsert when DATABASE_URL is set.
One award-type group per API call (USAspending rule).
Never invents fields — Missing stays Missing.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

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


def fetch_all(name: str, filters: dict, page_limit: int = 20) -> list[dict]:
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
            break
        batch = result.get("results") or []
        if not batch:
            break
        for r in batch:
            r["_ingest_job"] = name
            r["_ingested_at"] = datetime.now(timezone.utc).isoformat()
            rows.append(r)
        print(f"{name} page {page}: +{len(batch)} (total {len(rows)})")
        if not result.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
    return rows


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


def maybe_upsert_postgres(rows: list[dict]) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL unset — wrote JSONL only")
        return 0
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not installed — JSONL only", file=sys.stderr)
        return 0
    conn = psycopg2.connect(url)
    cur = conn.cursor()
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
    conn.commit()
    cur.close()
    conn.close()
    return n


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    jobs = []
    for geo in GEOS:
        for group_name, codes in GROUPS.items():
            name = f"{geo['slug']}-{group_name}"
            jobs.append(name)
            filters = {
                "award_type_codes": codes,
                "place_of_performance_locations": geo["locations"],
                "time_period": geo["time_period"],
            }
            rows = fetch_all(name, filters, page_limit=geo["page_limit"])
            path = OUT / f"{name}.jsonl"
            with path.open("w") as fh:
                for r in rows:
                    fh.write(json.dumps(r) + "\n")
            print(f"wrote {path} ({len(rows)} rows)")
            all_rows.extend(rows)
    stamped = OUT / f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    stamped.write_text(json.dumps({"rows": len(all_rows), "jobs": jobs}, indent=2))
    upserted = maybe_upsert_postgres(all_rows)
    print(f"done rows={len(all_rows)} upserted={upserted}")
    return 0 if all_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
