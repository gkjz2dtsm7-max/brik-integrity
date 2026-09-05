# USAspending ingest (Gulf County FL + Mississippi)

`usaspending_gulf_ms.py` pulls award-level rows, one award-type group per request
(contracts / grants / loans / direct_payments / other).

- Writes JSONL under `ingest/out/` (gitignored).
- Optional Postgres upsert when `DATABASE_URL` is set (see `db/schema.sql`).
- Sample rows (2 lines each) live in `ingest/samples/` for review — never invents awards.

Nightly: `.github/workflows/ingest-nightly.yml` (needs repo secret `DATABASE_URL`).
