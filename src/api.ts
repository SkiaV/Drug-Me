import { mockDrugs } from "./mockData";
import type {
  DemographicProfile,
  DrugReport,
  DrugSummary,
  SearchFilters,
} from "./types";

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, fallback: () => T): Promise<T> {
  try {
    const response = await fetch(`${apiBase}/api/v1${path}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`API returned ${response.status}`);
    return (await response.json()) as T;
  } catch {
    await new Promise((resolve) => window.setTimeout(resolve, 180));
    return fallback();
  }
}

function tierFor(score: number): DrugSummary["tier"] {
  if (score >= 75) return "Strong";
  if (score >= 55) return "Developing";
  return "Limited";
}

function profileScore(drug: DrugSummary, profile: DemographicProfile) {
  const ageScore =
    profile.age >= 65 ? drug.components.age : Math.min(96, drug.components.age + 8);
  const sexScore =
    profile.sex === "All or not specified"
      ? drug.components.sex
      : drug.components.sex - (profile.sex === "Female" ? 2 : 0);
  const raceScore =
    profile.race === "All or not specified"
      ? drug.components.race
      : drug.components.race -
        (profile.race === "White" ? 0 : profile.race.includes("Black") ? 11 : 7);

  return Math.max(20, Math.round((ageScore + sexScore + raceScore) / 3));
}

export function getDashboard(): Promise<DrugSummary[]> {
  return request("/drugs", () => mockDrugs);
}

export function searchDrugs(filters: SearchFilters): Promise<DrugSummary[]> {
  const params = new URLSearchParams(
    Object.entries(filters).map(([key, value]) => [key, String(value)]),
  );

  return request(`/search?${params}`, () => {
    return mockDrugs
      .filter((drug) => {
        const nameMatches = filters.drug
          ? drug.name.toLowerCase().includes(filters.drug.toLowerCase().trim())
          : true;
        const uses = `${drug.primaryUse} ${drug.otherUses.join(" ")}`.toLowerCase();
        const indicationMatches = filters.indication
          ? uses.includes(filters.indication.toLowerCase().trim())
          : true;
        return nameMatches && indicationMatches;
      })
      .map((drug) => {
        const score = profileScore(drug, filters);
        return { ...drug, score, tier: tierFor(score) };
      });
  });
}

export function getDrugReport(
  drugId: string,
  profile: DemographicProfile,
): Promise<DrugReport> {
  const params = new URLSearchParams({
    age: String(profile.age),
    sex: profile.sex,
    race: profile.race,
  });

  return request(`/drugs/${drugId}/report?${params}`, () => {
    const drug = mockDrugs.find((item) => item.id === drugId) ?? mockDrugs[0];
    const personalizedScore = profileScore(drug, profile);
    const ageBand = profile.age >= 65 ? "older adults" : profile.age < 18 ? "children" : "adults";
    return {
      drug,
      profile,
      personalizedScore,
      summary: `${drug.name} has ${tierFor(personalizedScore).toLowerCase()} evidence coverage for the selected demographic profile. The largest limitation in the available trial record is ${drug.leastResearched.dimension.toLowerCase()} representation.`,
      strengths: [
        `${drug.trialCount} relevant studies were identified across registered and completed trials.`,
        `Sex representation scored ${drug.components.sex}% in the generalized evidence base.`,
      ],
      gaps: [
        `${drug.leastResearched.group} remain the least represented group in this evidence set.`,
        `Evidence for ${ageBand} should be interpreted with the available enrollment counts and study eligibility criteria.`,
      ],
      fdaContext: {
        indication: drug.primaryUse,
        labelUpdated: "2024-11-19",
        note: "FDA labeling provides approved-use context but does not independently establish demographic representativeness.",
        sourceUrl: "https://open.fda.gov/apis/drug/label/",
      },
      evidence: [
        {
          id: "NCT05824182",
          title: `${drug.name} outcomes across diverse care settings`,
          phase: "Phase 4",
          status: "Completed",
          enrollment: 2480,
          match: "High relevance",
          sourceUrl: "https://clinicaltrials.gov/",
        },
        {
          id: "NCT04491851",
          title: `Long-term effectiveness and safety of ${drug.name}`,
          phase: "Phase 3",
          status: "Completed",
          enrollment: 1184,
          match: "Moderate relevance",
          sourceUrl: "https://clinicaltrials.gov/",
        },
        {
          id: "NCT06120733",
          title: `Real-world treatment patterns for ${drug.primaryUse.toLowerCase()}`,
          phase: "Observational",
          status: "Recruiting",
          enrollment: 3600,
          match: "Moderate relevance",
          sourceUrl: "https://clinicaltrials.gov/",
        },
      ],
    };
  });
}
