-- BRIK Integrity Schema
-- Federal award intelligence + state overlay + evidence packets
-- Deploy to Supabase: paste this entire file into SQL editor and run
-- NEVER store real bank account/routing values in public repos or seed data.

-- Table: places
CREATE TABLE IF NOT EXISTS places (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fips_code VARCHAR(10) UNIQUE,
  name VARCHAR(255) NOT NULL,
  state VARCHAR(2) NOT NULL,
  county VARCHAR(255),
  type VARCHAR(50),
  population INT,
  federal_total_fy2025 DECIMAL(15,2) DEFAULT 0,
  last_updated TIMESTAMP DEFAULT now(),
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS awards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usaspending_id VARCHAR(255) UNIQUE NOT NULL,
  award_type VARCHAR(50),
  title VARCHAR(500),
  description TEXT,
  agency_name VARCHAR(255),
  agency_code VARCHAR(10),
  amount DECIMAL(15,2),
  start_date DATE,
  end_date DATE,
  recipient_name VARCHAR(255),
  recipient_type VARCHAR(100),
  place_id UUID REFERENCES places(id),
  fips_code VARCHAR(10),
  state VARCHAR(2),
  county VARCHAR(255),
  city VARCHAR(255),
  fiscal_year INT,
  url VARCHAR(500),
  last_updated TIMESTAMP DEFAULT now(),
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS disbursers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  title VARCHAR(255),
  agency VARCHAR(255),
  state VARCHAR(2),
  email VARCHAR(255),
  phone VARCHAR(20),
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS certifiers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  agency VARCHAR(255),
  state VARCHAR(2),
  certification_type VARCHAR(100),
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS second_hop_payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id UUID NOT NULL REFERENCES awards(id),
  vendor_name VARCHAR(255),
  vendor_type VARCHAR(100),
  amount DECIMAL(15,2),
  payment_date DATE,
  invoice_number VARCHAR(100),
  description TEXT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS restricted_use_text (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id UUID NOT NULL REFERENCES awards(id),
  restriction_type VARCHAR(100),
  text TEXT,
  source VARCHAR(255),
  created_at TIMESTAMP DEFAULT now()
);

-- Parking / intermediary metadata only — never put live bank numbers in seeds or git
CREATE TABLE IF NOT EXISTS parking_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id UUID NOT NULL REFERENCES awards(id),
  account_holder VARCHAR(255),
  account_type VARCHAR(100),
  account_number VARCHAR(100),
  routing_number VARCHAR(20),
  amount DECIMAL(15,2),
  duration_days INT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outcome_clocks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id UUID NOT NULL REFERENCES awards(id),
  milestone_name VARCHAR(255),
  required_date DATE,
  reported_date DATE,
  outcome_measure VARCHAR(255),
  target_value INT,
  actual_value INT,
  status VARCHAR(50),
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_packets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  award_id UUID,
  place_id UUID,
  packet_type VARCHAR(100),
  title VARCHAR(500),
  description TEXT,
  file_url VARCHAR(500),
  file_hash VARCHAR(64),
  source_agency VARCHAR(255),
  date_created DATE,
  date_uploaded TIMESTAMP DEFAULT now(),
  certifier_id UUID REFERENCES certifiers(id),
  created_at TIMESTAMP DEFAULT now(),
  CONSTRAINT fk_award FOREIGN KEY (award_id) REFERENCES awards(id),
  CONSTRAINT fk_place FOREIGN KEY (place_id) REFERENCES places(id)
);

CREATE SCHEMA IF NOT EXISTS elections;

CREATE TABLE IF NOT EXISTS elections.donations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  donor_name VARCHAR(255),
  recipient_name VARCHAR(255),
  recipient_type VARCHAR(100),
  amount DECIMAL(15,2),
  transaction_date DATE,
  election_year INT,
  fec_id VARCHAR(100),
  state VARCHAR(2),
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_awards_place ON awards(place_id);
CREATE INDEX IF NOT EXISTS idx_awards_state ON awards(state);
CREATE INDEX IF NOT EXISTS idx_awards_county ON awards(county);
CREATE INDEX IF NOT EXISTS idx_awards_fiscal_year ON awards(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_awards_fips ON awards(fips_code);
CREATE INDEX IF NOT EXISTS idx_places_state ON places(state);
CREATE INDEX IF NOT EXISTS idx_places_fips ON places(fips_code);
CREATE INDEX IF NOT EXISTS idx_second_hop_award ON second_hop_payments(award_id);
CREATE INDEX IF NOT EXISTS idx_evidence_award ON evidence_packets(award_id);
CREATE INDEX IF NOT EXISTS idx_evidence_place ON evidence_packets(place_id);
CREATE INDEX IF NOT EXISTS idx_outcome_award ON outcome_clocks(award_id);

ALTER TABLE awards ENABLE ROW LEVEL SECURITY;
ALTER TABLE places ENABLE ROW LEVEL SECURITY;
