# BRIK Integrity warehouse setup

Public index (static): https://gkjz2dtsm7-max.github.io/brik-integrity/

## 1. Schema on Supabase
1. Create a free Supabase project (org of your choice).
2. SQL Editor → New query → paste `db/schema.sql` → Run.
3. Paste `db/seed_places.sql` → Run.
4. Project Settings → Database → Connection string (URI) → copy as `DATABASE_URL`.
   Prefer the **session / direct** URI for scripts; never commit it.

## 2. GitHub Actions secret
Repo → Settings → Secrets and variables → Actions → New repository secret:
- Name: `DATABASE_URL`
- Value: the Supabase Postgres URI

Nightly job: `.github/workflows/ingest-nightly.yml`

## 3. Local / one-shot ingest
```bash
export DATABASE_URL='postgresql://...'
python3 ingest/usaspending_gulf_ms.py
```

Pulls Gulf County FL + Mississippi awards by award-type group (contracts, grants, loans, direct_payments, other). Writes JSONL under `ingest/out/` (gitignored) and upserts into `awards` when `DATABASE_URL` is set.

## Rules
- Never invent awards, dockets, or bank account numbers.
- Elections (`elections.*`) never sum into grants totals.
- Bank IP / live account-routing values stay out of git and out of public Pages.
