# National ledger status 2026-09-05

Pulled live from USAspending API spending_by_geography, place_of_performance, FY2025 (2024-10-01 to 2025-09-30).

1. Place pages: 50 states + DC + AS, GU, MP, PR, VI + Gulf County + Winona + unspecified POP row.
2. Each state card has the FY2025 POP dollar total and per-capita figure from the API.
3. State overlay link is on the card (Florida FACTS, Texas Comptroller, MS Transparency, etc.).
4-8. Disburser graph, second-hop, parking watch, and outcome clock are structured on every card. Named people attach when an award row is pinned. Founding cases already pin those fields for FL Gulf and MS.
9. Elections / donations are a separate rail on every card and are never added into the grant total.

Source call date: 2026-09-05.
Repo files: docs/places.js (rows), docs/data.js (decoder + cases), docs/index.html (UI).
