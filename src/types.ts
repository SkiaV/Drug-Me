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

export type SearchFilters = DemographicProfile & {
  drug: string;
  indication: string;
  status: string;
  phase: string;
  location: string;
  sponsor: string;
  fromDate: string;
  toDate: string;
};

export type EvidenceItem = {
  id: string;
  title: string;
  phase: string;
  status: string;
  enrollment: number;
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
