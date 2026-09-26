export type CoverageTier = "Limited" | "Developing" | "Strong";

export type DrugSummary = {
  id: string;
  name: string;
  primaryUse: string;
  otherUses: string[];
  leastResearched: {
    dimension: "Age" | "Sex" | "Race";
    group: string;
  };
  score: number;
  tier: CoverageTier;
  components: {
    age: number;
    sex: number;
    race: number;
  };
  trialCount: number;
  participantCount: number;
  updatedAt: string;
};

export type DemographicProfile = {
  age: number;
  sex: "Female" | "Male" | "All or not specified";
  race:
    | "American Indian or Alaska Native"
    | "Asian"
    | "Black or African American"
    | "Multiracial"
    | "Native Hawaiian or Pacific Islander"
    | "White"
    | "All or not specified";
};

/**
 * Every study in the backend is a completed Phase 3 trial (backend/schema.sql enforces that scope at
 * load time), so the only clinical filters left are the medicine and its use.
 */
export type SearchFilters = DemographicProfile & {
  drug: string;
  indication: string;
};

/** `GET /api/studies/stats`, with the ingest record that `backend/ingest.py` writes into `meta`. */
export type BackendStats = {
  studies: number;
  participants: number;
  withRaceComposition: number;
  distinctDrugs: number;
  ingest: {
    studies?: number;
    skipped?: Record<string, number>;
    loaded_at?: string;
    agg_filters?: string;
    scope?: { status?: string; phase?: string };
  } | null;
};

export type DashboardData = {
  drugs: DrugSummary[];
  stats: BackendStats;
  source: "backend" | "sample";
};

/** One supporting trial on the report page, derived from a `studies` row. */
export type EvidenceItem = {
  id: string;
  title: string;
  drug: string;
  participants: number;
  sex: string;
  ageRange: string;
  match: string;
  sourceUrl: string;
};

export type DrugReport = {
  drug: DrugSummary;
  profile: DemographicProfile;
  personalizedScore: number;
  summary: string;
  strengths: string[];
  gaps: string[];
  fdaContext: {
    indication: string;
    labelUpdated: string;
    note: string;
    sourceUrl: string;
  };
  evidence: EvidenceItem[];
};
