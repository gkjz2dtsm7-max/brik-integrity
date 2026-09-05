-- Seed Gulf County FL + Mississippi state shell (no invented award dollars)
INSERT INTO places (fips_code, name, state, county, type)
VALUES
  ('12045', 'Gulf County', 'FL', 'Gulf', 'county'),
  ('28', 'Mississippi', 'MS', NULL, 'state')
ON CONFLICT (fips_code) DO UPDATE SET name = EXCLUDED.name, last_updated = now();
