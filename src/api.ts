import { mockDrugs } from "./mockData";
import type {
  BackendStats,
  DashboardData,
  DemographicProfile,
  DrugReport,
  DrugSummary,
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

type BackendStudy = {
  nct_id: string;
  title: string;
  drug: string | null;
  drug_mesh: string | null;
  condition: string | null;
  sex: string;
  age_min: number;
  age_max: number;
  female_count: number | null;
  male_count: number | null;
  participants: number | null;
  phase: string | null;
  status: string | null;
  start_date: string | null;
  has_results: number;
  race_reported: number;
  source_url: string;
  fetched_at: string;
  race_composition: BackendRace[];
};

type StudiesResponse = {
  total: number;
  limit: number;
  offset: number;
  studies: BackendStudy[];
};

type StatsResponse = {
  studies: number;
  with_results: number;
  with_race_composition: number;
  distinct_drugs: number;
  distinct_conditions: number;
  ingest: BackendStats["ingest"];
};

type AggregateResponse = {
  studies: number;
  participants: number | null;
  studies_reporting_race: number;
  sex_counts: { female: number | null; male: number | null };
  age_range: [number | null, number | null];
  race_composition: Array<BackendRace & { studies: number }>;
};

const fallbackStats: BackendStats = {
  studies: 18406,
  withResults: 14776,
  withRaceComposition: 10418,
  distinctDrugs: 1248,
  distinctConditions: 2906,
  ingest: { finished_at: "2025-05-14T12:00:00Z" },
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

function toDrugSummaries(studies: BackendStudy[]): DrugSummary[] {
  if (!Array.isArray(studies)) return [];
  const groups = new Map<string, BackendStudy[]>();
  for (const study of studies) {
    const name = genericName(study);
    if (!name) continue;
    groups.set(name, [...(groups.get(name) ?? []), study]);
  }

  return [...groups.entries()].map(([name, rows]) => {
    const participantCount = rows.reduce(
      (sum, row) => sum + (row.participants ?? 0),
      0,
    );
    const uses = rows
      .flatMap((row) => (row.condition ?? "").split(";"))
      .map((use) => use.trim())
      .filter(Boolean);
    const useCounts = new Map<string, number>();
    uses.forEach((use) => useCounts.set(use, (useCounts.get(use) ?? 0) + 1));
    const orderedUses = [...useCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([use]) => use);

    const ageCoverage = Math.round(
      rows.reduce(
        (sum, row) => sum + Math.min(100, Math.max(0, row.age_max - row.age_min)),
        0,
      ) / rows.length,
    );
    const female = rows.reduce((sum, row) => sum + (row.female_count ?? 0), 0);
    const male = rows.reduce((sum, row) => sum + (row.male_count ?? 0), 0);
    const sexCoverage =
      female && male
        ? Math.round((Math.min(female, male) / Math.max(female, male)) * 100)
        : Math.round(
            (rows.filter((row) => row.sex === "Male and Female").length /
              rows.length) *
              100,
          );
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
      updatedAt:
        rows.map((row) => row.fetched_at).filter(Boolean).sort().slice(-1)[0] ??
        new Date().toISOString(),
    };
  });
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

function backendParams(
  profile?: DemographicProfile,
  filters?: Partial<SearchFilters>,
) {
  const params = new URLSearchParams({ limit: "200" });
  if (filters?.drug) params.set("drug", filters.drug);
  if (filters?.indication) params.set("condition", filters.indication);
  if (profile?.age !== undefined && profile.age >= 0) {
    params.set("age", String(profile.age));
  }
  if (profile?.sex && profile.sex !== "All or not specified") {
    params.set("sex", profile.sex);
  }
  const race = profile ? raceCategory(profile.race) : undefined;
  if (race) params.set("race", race);
  return params;
}

function clientFilter(studies: BackendStudy[], filters: SearchFilters) {
  return studies.filter((study) => {
    const statusMatches =
      filters.status === "All statuses" ||
      study.status?.replace(/_/g, " ").toLowerCase() ===
        filters.status.toLowerCase();
    const phaseMatches =
      filters.phase === "All phases" ||
      study.phase?.replace(/_/g, " ").toLowerCase() ===
        filters.phase.replace(" ", "").toLowerCase();
    const fromMatches =
      !filters.fromDate || !study.start_date || study.start_date >= filters.fromDate;
    const toMatches =
      !filters.toDate || !study.start_date || study.start_date <= filters.toDate;
    return statusMatches && phaseMatches && fromMatches && toMatches;
  });
}

export async function getDashboard(): Promise<DashboardData> {
  if (!backendEnabled) {
    return { drugs: mockDrugs, stats: fallbackStats, source: "sample" };
  }
  try {
    const [studyData, statsData] = await Promise.all([
      request<StudiesResponse>("?limit=200&has_results=1"),
      request<StatsResponse>("/stats"),
    ]);
    if (!Array.isArray(studyData?.studies) || !statsData) {
      throw new Error("Backend returned an invalid dashboard response");
    }
    return {
      drugs: toDrugSummaries(studyData.studies),
      stats: {
        studies: statsData.studies,
        withResults: statsData.with_results,
        withRaceComposition: statsData.with_race_composition,
        distinctDrugs: statsData.distinct_drugs,
        distinctConditions: statsData.distinct_conditions,
        ingest: statsData.ingest,
      },
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
    const params = backendParams(filters, filters);
    params.set("has_results", "1");
    const data = await request<StudiesResponse>(`?${params}`);
    return toDrugSummaries(clientFilter(data.studies, filters));
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
    params.set("has_results", "1");
    const [studyData, aggregate] = await Promise.all([
      request<StudiesResponse>(`?${params}`),
      request<AggregateResponse>(`/aggregate?${params}`),
    ]);
    const drug =
      toDrugSummaries(studyData.studies)[0] ??
      ({ ...fallbackDrug, name: titleCase(requestedName) } as DrugSummary);
    const targetRace = raceCategory(profile.race);
    const raceEntry = aggregate.race_composition.find(
      (item) => item.category === targetRace,
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

    return {
      drug,
      profile,
      personalizedScore,
      summary: `${studyData.total} studies in the uploaded ClinicalTrials.gov dataset match ${drug.name} and the selected eligibility profile. ${aggregate.studies_reporting_race} of those studies report race composition.`,
      strengths: [
        `${(aggregate.participants ?? 0).toLocaleString()} participants are represented across the matching evidence set.`,
        `${aggregate.studies_reporting_race} matching studies report race composition.`,
      ],
      gaps: [
        `${Math.max(0, aggregate.studies - aggregate.studies_reporting_race)} matching studies do not report usable race composition.`,
        "Age reflects protocol eligibility ranges, not the observed ages of enrolled participants.",
      ],
      fdaContext: {
        indication: drug.primaryUse,
        labelUpdated: "Not available",
        note: "The uploaded backend currently provides ClinicalTrials.gov evidence only. An openFDA labeling endpoint has not yet been included.",
        sourceUrl: "https://open.fda.gov/apis/drug/label/",
      },
      evidence: studyData.studies.slice(0, 8).map((study) => ({
        id: study.nct_id,
        title: study.title,
        phase: titleCase((study.phase ?? "Not reported").replace(/_/g, " ")),
        status: titleCase((study.status ?? "Not reported").replace(/_/g, " ")),
        enrollment: study.participants ?? 0,
        match: study.race_reported ? "Demographics reported" : "Limited reporting",
        sourceUrl: study.source_url,
      })),
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
      note: "FDA labeling is not included in the uploaded backend.",
      sourceUrl: "https://open.fda.gov/apis/drug/label/",
    },
    evidence: [],
  };
}
