# USAspending ingest (Gulf County FL + Mississippi)

`usaspending_gulf_ms.py` pulls award-level rows, one award-type group per request
(contracts / grants / loans / direct_payments / other).

- Writes JSONL under `ingest/out/` (gitignored, not published to Pages).
- Optional Postgres upsert when `DATABASE_URL` is set (see `db/schema.sql`).
- Sample rows (2 lines each) live in `ingest/samples/` for review — never invents awards.

Nightly: `.github/workflows/ingest-nightly.yml` (needs repo secret `DATABASE_URL`).

## Prior award IDs

`spending_by_award` is a top-N index. Awards can leave that index and still exist on
`GET /api/v2/awards/<generated_unique_award_id>/`.

`ingest/out/prior_award_ids.json` is the only file under `ingest/out/` that is committed.
It stores Award IDs per job (`mississippi-grants`, and the other geo/group jobs).
The nightly workflow commits it after a successful run so the next runner can read it.
JSONL stays gitignored and is not uploaded to Pages.

If that file is missing or unreadable, the run seeds an empty set. Awards that already
fell out of search before the first saved list are not rediscovered until a search
pull sees them again (or their Award IDs are added to the sidecar).

After each successful job fetch, `missing = prior IDs − today's Award IDs` for that
job only. Grant jobs fetch each missing id from the detail endpoint. A FAIN is
requested as `ASST_NON_<Award ID>_075` (HHS assistance). That pattern is verified
for `RHTCMS332063`: the detail URL returns 200, `GET /awards/RHTCMS332063/` is 404,
and `spending_by_award` with `award_ids` returns 0. Other jobs are not re-fetched.

Recovered rows use the same JSONL and upsert path as search rows, with
`_source` set to `detail_fallback`. Search rows keep `_source` `spending_by_award`
and are not written twice. Null detail fields stay null.

After a successful job, the sidecar for that job becomes today's search Award IDs,
plus recovered detail ids, plus ids whose detail call failed transiently.
A 404/400/410 drops the id. A failed search leaves that job's prior list unchanged.
