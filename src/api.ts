/* Frontend models and requests to the Flask API (backend/app.py, /api/v1).

   Same-origin by default: in production Flask serves the built app and the API from one URL; in development
   vite.config.ts proxies /api to Flask. Set VITE_API_BASE_URL when Flask is hosted elsewhere. There is no mock
   fallback; API errors appear in the relevant page. */

export type CoverageTier = "Limited" | "Developing" | "Strong";

export type Components = { age: number | null; sex: number | null; race: number | null };

export type GroupCell = { share: number | null; ppr: number | null; band: string; missingTrials: number };

export type DrugSummary = {
  id: string;
  name: string;
  primaryUse: string;
  otherUses: string[];
  diseaseArea?: string | null;
  leastResearched: { dimension: "Age" | "Sex" | "Race" | "Ethnicity"; group: string };
  score: number | null;
  tier: CoverageTier;
  components: Components;
  trialCount: number;
  participantCount: number;
  updatedAt: string | null;
  // extras the Flask API adds on top of the prototype's shape
  groups?: Record<string, GroupCell>;
  years?: (number | null)[];
  raceMissingShare?: number;
  designExcluded65Share?: number;
  usSiteShare?: number | null;
  brands?: string[];
  drugClass?: string | null;
  approvedOn?: string | null;
  isCombination?: boolean;
  ingredients?: string[];
  matchedName?: string;
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
  ethnicity: "Hispanic or Latino" | "Not Hispanic or Latino" | "All or not specified";
};

export type SearchFilters = DemographicProfile & {
  drug: string;
  indication: string;
  diseaseArea: string;
  minParticipants: string;
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
  years?: (number | null)[];
  sponsor?: string | null;
  sponsorClass?: string | null;
  sitesTotal?: number;
  sitesUs?: number;
  agesAllowed?: string;
  sexAllowed?: string;
  femaleShare?: number | null;
  age65Share?: number | null;
  meanAge?: number | null;
  raceReported?: boolean;
  raceTitle?: string | null;
};

/** One demographic group of one report: its share of pooled participants against two expected shares. */
export type Group = {
  key: string;
  label: string;
  dimension: string;
  count: number | null;
  trial_share: number | null;
  expected_pop: number;
  expected_disease: number | null;
  ppr_pop: number | null;
  ppr_disease: number | null;
  band_pop: string;
  band_disease: string | null;
  coverage: number;
  trials_reporting: number;
  trials_missing: number;
  trials_design_excluded: number;
};

export type Faers = {
  reports: number;
  female: number;
  male: number;
  female_share: number | null;
  baseline_female_share: number | null;
  ratio: number | null;
  by_year: { year: number; female: number; male: number }[];
  reactions_skew_female: { reaction: string; female: number; male: number; ratio: number }[];
  note: string;
};

export type ReportDetails = {
  groups: Group[];
  denominators: {
    population: string;
    disease: { question: string; year: string; proxy: boolean; source: string } | null;
  };
  evidence: {
    trials: number;
    participants: number;
    years: (number | null)[];
    source: string;
    found: number;
    comparator_only: number;
    missing: { race: number; ethnicity: number; age_categorical: number; sex: number };
    note: string | null;
    us_site_share: number | null;
    industry_share: number | null;
    mean_age: number | null;
  };
  faers: Faers | null;
  method: { metric: string; score: string; limits: string[] };
  approval: { date: string; application: string } | null;
};

export type DrugReport = {
  drug: DrugSummary;
  profile: DemographicProfile & { groups?: string[] };
  personalizedScore: number | null;
  populationScore?: number | null;
  diseaseScore?: number | null;
  scoreable?: boolean;
  summary: string;
  questions?: string[];
  strengths: string[];
  gaps: string[];
  fdaContext: {
    indication: string;
    labelUpdated: string | null;
    brand?: string | null;
    note: string;
    flags?: { type: string; section: string; quote: string }[];
    insufficient65?: boolean;
    sourceUrl: string;
  };
  evidence: EvidenceItem[];
  details?: ReportDetails;
  /** Context (label, FAERS, approval, class, prevalence) that could not be fetched this time. */
  warnings?: string[];
};

export type Meta = {
  drugsReviewed: number;
  trials: number;
  overallCoverage: number | null;
  refreshed: string | null;
  diseaseAreas: string[];
  sampleData: boolean;
  /** 2020 Census shares used as the reference population (age65 = share of adults). */
  population?: Record<string, number>;
  /** Participant-weighted shares across every harvested trial, for the home-page explainer. */
  registry?: {
    trials: number;
    participants: number;
    shares: Record<string, number | null>;
    notReported: Record<string, number>;
    meanAge: number | null;
  } | null;
};

const apiBase = (
  (import.meta as ImportMeta & { env: { VITE_API_BASE_URL?: string } }).env.VITE_API_BASE_URL ?? ""
).replace(/\/$/, "");

export class ApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}/api/v1${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("network", "The API is not reachable. Start the Flask server: python backend/app.py");
  }
  if (!response.ok) {
    let body: { error?: { code?: string; message?: string } } | null = null;
    try {
      body = await response.json();
    } catch {
      /* not JSON */
    }
    if (body?.error?.message) throw new ApiError(body.error.code ?? "error", body.error.message);
    throw new ApiError("http", `API returned ${response.status}`);
  }
  return (await response.json()) as T;
}

export function tierFor(score: number | null): CoverageTier {
  if (score == null) return "Limited";
  if (score >= 75) return "Strong";
  if (score >= 55) return "Developing";
  return "Limited";
}

const profileParams = (profile: DemographicProfile) => ({
  age: String(profile.age),
  sex: profile.sex,
  race: profile.race,
  ethnicity: profile.ethnicity,
});

export function getMeta(): Promise<Meta> {
  return request("/meta");
}

export function getDashboard(
  params: { query?: string; sort?: string; order?: string; limit?: number } = {},
): Promise<DrugSummary[]> {
  const query = new URLSearchParams(
    Object.entries(params)
      .filter(([, value]) => value !== undefined && value !== "")
      .map(([key, value]) => [key, String(value)]),
  );
  return request(`/drugs?${query}`);
}

export function searchDrugs(filters: SearchFilters): Promise<DrugSummary[]> {
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, value]) => value !== "")
      .map(([key, value]) => [key, String(value)]),
  );
  return request(`/search?${params}`);
}

export function suggest(query: string): Promise<string[]> {
  return request(`/suggest?q=${encodeURIComponent(query)}`);
}

export function getDrugReport(drugId: string, profile: DemographicProfile): Promise<DrugReport> {
  const params = new URLSearchParams(profileParams(profile));
  return request(`/drugs/${encodeURIComponent(drugId)}/report?${params}`);
}

export const pct = (value: number | null | undefined, digits = 0) =>
  value == null ? "—" : `${(100 * value).toFixed(digits)}%`;

export const BAND_LABEL: Record<string, string> = {
  very_under: "Very under-represented",
  under: "Under-represented",
  adequate: "Represented",
  over: "Over-represented",
  not_reported: "Not reported",
  na_by_design: "Not applicable by design",
};

export function reportPath(drugId: string, profile: DemographicProfile) {
  return `/report/${encodeURIComponent(drugId)}?${new URLSearchParams(profileParams(profile))}`;
}
