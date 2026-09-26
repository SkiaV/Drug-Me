export type CoverageTier = "Limited" | "Developing" | "Strong";

export type DrugSummary = {
  id: string;
  name: string;
  primaryUse: string;
  otherUses: string[];
  leastResearched: { dimension: "Age" | "Sex" | "Race"; group: string };
  score: number;
  tier: CoverageTier;
  components: { age: number; sex: number; race: number };
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

export type SearchFilters = DemographicProfile & { drug: string; indication: string };

export type BackendStats = {
  studies: number;
  participants: number;
  with_race_composition: number;
  distinct_drugs: number;
  ingest: { loaded_at?: string } | null;
};

export type DashboardData = { drugs: DrugSummary[]; stats: BackendStats };

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
  fdaContext: { indication: string; labelUpdated: string; note: string; sourceUrl: string };
  evidence: EvidenceItem[];
};

type Study = {
  nct_id: string;
  drug: string;
  drug_mesh: string;
  condition: string;
  sex: "M" | "F" | "MF";
  age_lower: number | null;
  age_upper: number | null;
  female_count: number | null;
  male_count: number | null;
  participants: number;
  race_reported: 0 | 1;
  source_url: string;
  race_composition: { demographic: string; count: number; category: string; dimension: "race" | "ethnicity" }[];
};

type StudyList = { total: number; studies: Study[] };
type Aggregate = {
  studies: number;
  participants: number;
  studies_reporting_race: number;
  sex: { female: number | null; male: number | null };
  age_range: [number | null, number | null];
  race_composition: { dimension: "race" | "ethnicity"; category: string; count: number; studies: number }[];
};

const apiBase = (
  (import.meta as ImportMeta & { env: { VITE_API_BASE_URL?: string } }).env.VITE_API_BASE_URL ||
  "http://127.0.0.1:5001"
).replace(/\/$/, "");

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? `API returned ${response.status}`);
  }
  return (await response.json()) as T;
}

function tierFor(score: number): DrugSummary["tier"] {
  if (score >= 75) return "Strong";
  if (score >= 55) return "Developing";
  return "Limited";
}

function titleCase(value: string) {
  return value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function drugName(study: Study) {
  return titleCase((study.drug_mesh || study.drug).split(";")[0].trim().replace(/\s+/g, " "));
}

function raceCategory(race: DemographicProfile["race"]) {
  const categories: Partial<Record<DemographicProfile["race"], string>> = {
    "American Indian or Alaska Native": "aian",
    Asian: "asian",
    "Black or African American": "black",
    Multiracial: "multiracial",
    "Native Hawaiian or Pacific Islander": "nhpi",
    White: "white",
  };
  return categories[race];
}

function searchParams(profile?: DemographicProfile, filters?: Partial<SearchFilters>) {
  const params = new URLSearchParams({ limit: "200" });
  if (filters?.drug) params.set("drug", filters.drug.trim());
  if (filters?.indication) params.set("condition", filters.indication.trim());
  if (profile && profile.age >= 0) params.set("age", String(profile.age));
  if (profile?.sex === "Female") params.set("sex", "F");
  if (profile?.sex === "Male") params.set("sex", "M");
  const race = profile ? raceCategory(profile.race) : undefined;
  if (race) params.set("race", race);
  return params;
}

function leastSex(rows: Study[]) {
  const reported = rows.filter((row) => row.female_count !== null && row.male_count !== null);
  if (!reported.length) return "Sex enrollment unavailable";
  const female = reported.reduce((sum, row) => sum + (row.female_count ?? 0), 0);
  const male = reported.reduce((sum, row) => sum + (row.male_count ?? 0), 0);
  return female === male ? "Female and male participants (tied)" : female < male ? "Female participants" : "Male participants";
}

function leastRace(rows: Study[]) {
  const totals = new Map<string, number>();
  const labels = new Map<string, string>();
  for (const row of rows) for (const race of row.race_composition) {
    if (race.dimension !== "race" || race.category === "unknown") continue;
    totals.set(race.category, (totals.get(race.category) ?? 0) + race.count);
    labels.set(race.category, race.demographic);
  }
  if (totals.size < 2) return "Insufficient race-group data";
  const lowest = Math.min(...totals.values());
  const groups = [...totals].filter(([, count]) => count === lowest).map(([category]) => labels.get(category) ?? category);
  return groups.length > 1 ? `${groups.join(", ")} (tied)` : `${groups[0]} participants (reported)`;
}

function leastAge(rows: Study[]) {
  const bands = [
    { label: "Children (<18)", min: 0, max: 17 },
    { label: "Adults (18-64)", min: 18, max: 64 },
    { label: "Adults 65+", min: 65, max: 100 },
  ].map((band) => ({
    ...band,
    count: rows.filter((row) => (row.age_lower ?? 0) <= band.max && (row.age_upper ?? 100) >= band.min).length,
  }));
  const lowest = Math.min(...bands.map((band) => band.count));
  const groups = bands.filter((band) => band.count === lowest).map((band) => band.label);
  return groups.length > 1 ? `${groups.join(", ")} eligibility (tied)` : `${groups[0]} eligibility`;
}

function summarize(studies: Study[], updatedAt?: string): DrugSummary[] {
  const groups = new Map<string, Study[]>();
  for (const study of studies) {
    const name = drugName(study);
    groups.set(name, [...(groups.get(name) ?? []), study]);
  }

  return [...groups].map(([name, rows]) => {
    const uses = rows.flatMap((row) => row.condition.split(";").map((value) => value.trim())).filter(Boolean);
    const useCounts = new Map<string, number>();
    uses.forEach((use) => useCounts.set(use, (useCounts.get(use) ?? 0) + 1));
    const orderedUses = [...useCounts].sort((a, b) => b[1] - a[1]).map(([use]) => use);
    const female = rows.reduce((sum, row) => sum + (row.female_count ?? 0), 0);
    const male = rows.reduce((sum, row) => sum + (row.male_count ?? 0), 0);
    const components = {
      age: Math.round(rows.reduce((sum, row) => sum + Math.min(100, (row.age_upper ?? 100) - (row.age_lower ?? 0)), 0) / rows.length),
      sex: female && male ? Math.round((Math.min(female, male) / Math.max(female, male)) * 100) : Math.round((rows.filter((row) => row.sex === "MF").length / rows.length) * 100),
      race: Math.round((rows.filter((row) => row.race_reported).length / rows.length) * 100),
    };
    const weakest = Object.entries(components).sort((a, b) => a[1] - b[1])[0][0];
    const leastResearched = weakest === "age"
      ? { dimension: "Age" as const, group: leastAge(rows) }
      : weakest === "sex"
        ? { dimension: "Sex" as const, group: leastSex(rows) }
        : { dimension: "Race" as const, group: leastRace(rows) };
    const score = Math.round((components.age + components.sex + components.race) / 3);
    return {
      id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
      name,
      primaryUse: orderedUses[0] ? titleCase(orderedUses[0]) : "Use not reported",
      otherUses: orderedUses.slice(1, 8).map(titleCase),
      leastResearched,
      score,
      tier: tierFor(score),
      components,
      trialCount: rows.length,
      participantCount: rows.reduce((sum, row) => sum + row.participants, 0),
      updatedAt: updatedAt ?? "Not reported",
    };
  });
}

export async function getDashboard(): Promise<DashboardData> {
  const [result, stats] = await Promise.all([
    request<StudyList>("/api/studies?limit=200"),
    request<BackendStats>("/api/studies/stats"),
  ]);
  return { drugs: summarize(result.studies, stats.ingest?.loaded_at), stats };
}

export async function searchDrugs(filters: SearchFilters): Promise<DrugSummary[]> {
  const params = searchParams(filters, filters);
  const result = await request<StudyList>(`/api/studies?${params}`);
  return summarize(result.studies);
}

export async function getDrugReport(drugId: string, profile: DemographicProfile): Promise<DrugReport> {
  const drugQuery = drugId.replace(/-/g, "%");
  const allParams = searchParams(undefined, { drug: drugQuery });
  const profileParams = searchParams(profile, { drug: drugQuery });
  const [allStudies, matching, aggregate] = await Promise.all([
    request<StudyList>(`/api/studies?${allParams}`),
    request<StudyList>(`/api/studies?${profileParams}`),
    request<Aggregate>(`/api/studies/aggregate?${profileParams}`),
  ]);
  const drug = summarize(allStudies.studies)[0] ?? summarize(matching.studies)[0];
  if (!drug) throw new Error(`No studies found for ${drugId.replace(/-/g, " ")}.`);

  const category = raceCategory(profile.race);
  const raceCount = aggregate.race_composition.find((item) => item.dimension === "race" && item.category === category)?.count ?? 0;
  const raceTotal = aggregate.race_composition.filter((item) => item.dimension === "race").reduce((sum, item) => sum + item.count, 0);
  const raceScore = raceTotal ? Math.min(100, Math.round((raceCount / raceTotal) * 500)) : drug.components.race;
  const personalizedScore = Math.round((drug.components.age + drug.components.sex + raceScore) / 3);
  const lower = aggregate.age_range[0] ?? 0;
  const upper = aggregate.age_range[1];
  const ageNote = aggregate.studies === 0 ? "No matching studies set an age envelope." : upper === null
    ? `Eligibility starts as low as age ${lower}; at least one study has no upper age limit.`
    : `Eligibility spans ages ${lower} to ${upper} across matching studies.`;

  return {
    drug: { ...drug, trialCount: allStudies.total },
    profile,
    personalizedScore,
    summary: `${matching.total} completed Phase III studies match ${drug.name} and the selected profile. ${aggregate.studies_reporting_race} report race composition.`,
    strengths: [
      `${aggregate.participants.toLocaleString()} participants are represented in the matching evidence.`,
      `${aggregate.studies_reporting_race} matching studies report race composition.`,
      ageNote,
    ],
    gaps: [
      `${Math.max(0, aggregate.studies - aggregate.studies_reporting_race)} matching studies do not report race composition.`,
      "Age reflects protocol eligibility ranges, not the observed ages of participants.",
    ],
    fdaContext: {
      indication: drug.primaryUse,
      labelUpdated: "Not available",
      note: "The SQLite backend contains ClinicalTrials.gov data only; FDA labeling is not connected.",
      sourceUrl: "https://open.fda.gov/apis/drug/label/",
    },
    evidence: matching.studies.slice(0, 8).map((study) => ({
      id: study.nct_id,
      title: `${study.drug} — ${study.condition}`,
      phase: "Phase III",
      status: "Completed",
      enrollment: study.participants,
      match: study.race_reported ? "Race reported" : "Race not reported",
      sourceUrl: study.source_url,
    })),
  };
}
