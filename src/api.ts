import { mockDrugs } from "./mockData";
import type {
  BackendStats,
  DashboardData,
  DemographicProfile,
  DrugReport,
  DrugSummary,
  EvidenceItem,
  SearchFilters,
} from "./types";

const apiEnv = (import.meta as ImportMeta & {
  env?: { VITE_API_BASE_URL?: string; VITE_USE_BACKEND?: string };
}).env;
const apiBase = (apiEnv?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const backendEnabled =
  Boolean(apiBase) || apiEnv?.VITE_USE_BACKEND === "true";

type BackendRace = {
  demographic: string;
  count: number;
  category: string;
  dimension: "race" | "ethnicity";
};

/**
 * One `studies` row as `GET /api/studies` returns it: the columns of backend/schema.sql plus
 * `source_url`, which the API derives from the NCT number, and the study's race rows.
 */
type BackendStudy = {
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
  race_composition: BackendRace[];
};

type StudiesResponse = {
  total: number;
  limit: number;
  offset: number;
  filters: Record<string, string | number>;
  studies: BackendStudy[];
};

type StatsResponse = {
  studies: number;
  participants: number;
  with_race_composition: number;
  distinct_drugs: number;
  ingest: BackendStats["ingest"];
};

type AggregateResponse = {
  studies: number;
  participants: number;
  studies_reporting_race: number;
  sex: { female: number | null; male: number | null };
  age_range: [number | null, number | null];
  race_composition: Array<{
    dimension: "race" | "ethnicity";
    category: string;
    count: number;
    studies: number;
  }>;
};

// The totals of the 2026-09-26 load (11,976 completed Phase 3 studies with posted results).
const fallbackStats: BackendStats = {
  studies: 11976,
  participants: 8866877,
  withRaceComposition: 6869,
  distinctDrugs: 5850,
  ingest: {
    loaded_at: "2026-09-26T19:28:36+00:00",
    scope: { status: "COMPLETED", phase: "PHASE3" },
  },
};

async function request<T>(path: string): Promise<T> {
  if (!backendEnabled) {
    throw new Error("Backend is not enabled for this frontend environment");
  }
  const response = await fetch(`${apiBase}/api/studies${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? `Backend returned ${response.status}`);
  }
  return (await response.json()) as T;
}

function titleCase(value: string) {
  return value
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .replace(/\bAnd\b/g, "and")
    .replace(/\bOr\b/g, "or");
}

/** The first MeSH-normalized drug of a study, dose stripped, as the dashboard's grouping key. */
function genericName(study: BackendStudy) {
  const candidate = (study.drug_mesh || study.drug || "").split(";")[0]?.trim();
  if (!candidate) return null;
  return titleCase(
    candidate
      .replace(/\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|%)\b/gi, "")
      .replace(/\s+/g, " ")
      .trim(),
  );
}

function tierFor(score: number): DrugSummary["tier"] {
  if (score >= 75) return "Strong";
  if (score >= 55) return "Developing";
  return "Limited";
}

/** Eligibility span in years; a missing bound means no bound (0 or 100 for this purpose). */
function ageSpan(study: BackendStudy) {
  return Math.min(100, Math.max(0, (study.age_upper ?? 100) - (study.age_lower ?? 0)));
}

function describeSex(sex: BackendStudy["sex"]) {
  return sex === "F" ? "Female only" : sex === "M" ? "Male only" : "Female and male";
}

function describeAge(study: BackendStudy) {
  const { age_lower: lower, age_upper: upper } = study;
  if (lower === null && upper === null) return "Any age";
  if (upper === null) return `${lower} and older`;
  if (lower === null) return `Up to ${upper}`;
  return `${lower} to ${upper}`;
}

function toDrugSummaries(studies: BackendStudy[], updatedAt?: string): DrugSummary[] {
  if (!Array.isArray(studies)) return [];
  const groups = new Map<string, BackendStudy[]>();
  for (const study of studies) {
    const name = genericName(study);
    if (!name) continue;
    groups.set(name, [...(groups.get(name) ?? []), study]);
  }

  return [...groups.entries()].map(([name, rows]) => {
    const participantCount = rows.reduce((sum, row) => sum + row.participants, 0);
    const uses = rows
      .flatMap((row) => row.condition.split(";"))
      .map((use) => use.trim())
      .filter(Boolean);
    const useCounts = new Map<string, number>();
    uses.forEach((use) => useCounts.set(use, (useCounts.get(use) ?? 0) + 1));
    const orderedUses = [...useCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([use]) => use);

    const ageCoverage = Math.round(
      rows.reduce((sum, row) => sum + ageSpan(row), 0) / rows.length,
    );
    const female = rows.reduce((sum, row) => sum + (row.female_count ?? 0), 0);
    const male = rows.reduce((sum, row) => sum + (row.male_count ?? 0), 0);
    const sexCoverage =
      female && male
        ? Math.round((Math.min(female, male) / Math.max(female, male)) * 100)
        : Math.round((rows.filter((row) => row.sex === "MF").length / rows.length) * 100);
    const raceCoverage = Math.round(
      (rows.filter((row) => row.race_reported).length / rows.length) * 100,
    );
    const components = {
      age: ageCoverage,
      sex: sexCoverage,
      race: raceCoverage,
    };
    const score = Math.round(
      (components.age + components.sex + components.race) / 3,
    );
    const weakest = Object.entries(components).sort((a, b) => a[1] - b[1])[0][0];
    const leastResearched =
      weakest === "age"
        ? { dimension: "Age" as const, group: "Narrow age eligibility" }
        : weakest === "sex"
          ? { dimension: "Sex" as const, group: "Enrollment imbalance" }
          : { dimension: "Race" as const, group: "Race reporting incomplete" };

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
      participantCount,
      updatedAt: updatedAt ?? new Date().toISOString(),
    };
  });
}

/** Display race -> the backend's harmonized `study_races.category`. */
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

/**
 * The backend's query string. Sex travels as the schema code (F or M; a mixed-sex study matches
 * either), race as a category. "All or not specified" sends nothing.
 */
function backendParams(
  profile?: DemographicProfile,
  filters?: Partial<SearchFilters>,
) {
  const params = new URLSearchParams({ limit: "200" });
  if (filters?.drug) params.set("drug", filters.drug.trim());
  if (filters?.indication) params.set("condition", filters.indication.trim());
  if (profile?.age !== undefined && profile.age >= 0) {
    params.set("age", String(profile.age));
  }
  if (profile?.sex === "Female") params.set("sex", "F");
  if (profile?.sex === "Male") params.set("sex", "M");
  const race = profile ? raceCategory(profile.race) : undefined;
  if (race) params.set("race", race);
  return params;
}

function toStats(stats: StatsResponse): BackendStats {
  return {
    studies: stats.studies,
    participants: stats.participants,
    withRaceComposition: stats.with_race_composition,
    distinctDrugs: stats.distinct_drugs,
    ingest: stats.ingest,
  };
}

export async function getDashboard(): Promise<DashboardData> {
  if (!backendEnabled) {
    return { drugs: mockDrugs, stats: fallbackStats, source: "sample" };
  }
  try {
    const [studyData, statsData] = await Promise.all([
      request<StudiesResponse>("?limit=200"),
      request<StatsResponse>("/stats"),
    ]);
    if (!Array.isArray(studyData?.studies) || !statsData) {
      throw new Error("Backend returned an invalid dashboard response");
    }
    return {
      drugs: toDrugSummaries(studyData.studies, statsData.ingest?.loaded_at),
      stats: toStats(statsData),
      source: "backend",
    };
  } catch {
    return { drugs: mockDrugs, stats: fallbackStats, source: "sample" };
  }
}

export async function searchDrugs(filters: SearchFilters): Promise<DrugSummary[]> {
  if (!backendEnabled) {
    return sampleSearch(filters);
  }
  try {
    const data = await request<StudiesResponse>(`?${backendParams(filters, filters)}`);
    return toDrugSummaries(data.studies);
  } catch {
    return sampleSearch(filters);
  }
}

function sampleSearch(filters: SearchFilters) {
  return mockDrugs.filter((drug) => {
    const nameMatches = filters.drug
      ? drug.name.toLowerCase().includes(filters.drug.toLowerCase().trim())
      : true;
    const uses = `${drug.primaryUse} ${drug.otherUses.join(" ")}`.toLowerCase();
    return (
      nameMatches &&
      (filters.indication
        ? uses.includes(filters.indication.toLowerCase().trim())
        : true)
    );
  });
}

function toEvidence(study: BackendStudy): EvidenceItem {
  const condition = study.condition.split(";")[0]?.trim() || "condition not listed";
  return {
    id: study.nct_id,
    title: `${study.drug} for ${condition}`,
    drug: study.drug_mesh,
    participants: study.participants,
    sex: describeSex(study.sex),
    ageRange: describeAge(study),
    match: study.race_reported ? "Race reported" : "Race not reported",
    sourceUrl: study.source_url,
  };
}

export async function getDrugReport(
  drugId: string,
  profile: DemographicProfile,
): Promise<DrugReport> {
  const matchingMock = mockDrugs.find((item) => item.id === drugId);
  const requestedName =
    matchingMock?.name ?? titleCase(drugId.replace(/-/g, " "));
  const fallbackDrug: DrugSummary = matchingMock ?? {
    ...mockDrugs[0],
    id: drugId,
    name: requestedName,
  };

  if (!backendEnabled) {
    return sampleReport(fallbackDrug, profile);
  }

  try {
    const params = backendParams(profile, { drug: requestedName });
    const [studyData, aggregate] = await Promise.all([
      request<StudiesResponse>(`?${params}`),
      request<AggregateResponse>(`/aggregate?${params}`),
    ]);
    const drug =
      toDrugSummaries(studyData.studies)[0] ??
      ({ ...fallbackDrug, name: titleCase(requestedName) } as DrugSummary);
    const targetRace = raceCategory(profile.race);
    const raceEntry = aggregate.race_composition.find(
      (item) => item.dimension === "race" && item.category === targetRace,
    );
    const raceTotal = aggregate.race_composition
      .filter((item) => item.dimension === "race")
      .reduce((sum, item) => sum + item.count, 0);
    const targetRaceCoverage =
      targetRace && raceTotal && raceEntry
        ? Math.min(100, Math.round((raceEntry.count / raceTotal) * 500))
        : drug.components.race;
    const personalizedScore = Math.round(
      (drug.components.age + drug.components.sex + targetRaceCoverage) / 3,
    );
    const [ageLower, ageUpper] = aggregate.age_range;
    const envelope =
      aggregate.studies === 0
        ? "No study sets an age envelope."
        : ageUpper === null
          ? `Eligibility starts as low as age ${ageLower ?? 0}, and at least one study set no upper age limit.`
          : `Eligibility spans ages ${ageLower ?? 0} to ${ageUpper} across the matching studies.`;

    return {
      drug,
      profile,
      personalizedScore,
      summary: `${studyData.total} completed Phase 3 studies with posted results match ${drug.name} and the selected eligibility profile. ${aggregate.studies_reporting_race} of those studies report race composition.`,
      strengths: [
        `${aggregate.participants.toLocaleString()} participants are represented across the matching evidence set.`,
        `${aggregate.studies_reporting_race} matching studies report race composition.`,
        envelope,
      ],
      gaps: [
        `${Math.max(0, aggregate.studies - aggregate.studies_reporting_race)} matching studies do not report usable race composition.`,
        "Age reflects protocol eligibility ranges, not the observed ages of enrolled participants.",
      ],
      fdaContext: {
        indication: drug.primaryUse,
        labelUpdated: "Not available",
        note: "The backend provides ClinicalTrials.gov evidence only. FDA labeling is not part of the current data plan.",
        sourceUrl: "https://open.fda.gov/apis/drug/label/",
      },
      evidence: studyData.studies.slice(0, 8).map(toEvidence),
    };
  } catch {
    return sampleReport(fallbackDrug, profile);
  }
}

function sampleReport(
  drug: DrugSummary,
  profile: DemographicProfile,
): DrugReport {
  const ageBand =
    profile.age >= 65 ? "older adults" : profile.age < 18 ? "children" : "adults";
  return {
    drug,
    profile,
    personalizedScore: drug.score,
    summary: `${drug.name} is shown with sample evidence because a Flask backend was not configured for this frontend environment.`,
    strengths: [`${drug.trialCount} sample studies are available.`],
    gaps: [
      `Evidence for ${ageBand} should be interpreted with study eligibility criteria.`,
    ],
    fdaContext: {
      indication: drug.primaryUse,
      labelUpdated: "Not available",
      note: "FDA labeling is not included in the backend.",
      sourceUrl: "https://open.fda.gov/apis/drug/label/",
    },
    evidence: [],
  };
}
