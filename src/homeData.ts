import { getStats } from "./api";

/* Numbers behind the home page.
   - The explainer's registry-wide shares are a snapshot (2026-09-26) of the ClinicalTrials.gov harvest behind the
     Drug Me research build: every Phase 3 trial with posted results, participant-weighted. The reference
     population is the 2020 Census (age65 = share of adults).
   - The banner's study count comes from this repo's own SQLite backend when it is running. */

export type HomeMeta = {
  /** Studies behind this site; filled from the backend when it answers. */
  trials: number | null;
  refreshed: string | null;
  registry: {
    trials: number;
    participants: number;
    shares: Record<string, number | null>;
    notReported: Record<string, number>;
  } | null;
  population: Record<string, number> | null;
};

export const homeMetaSnapshot: HomeMeta = {
  trials: null,
  refreshed: null,
  registry: {
    trials: 14776,
    participants: 10483860,
    shares: { age65: 0.137, black: 0.097 },
    notReported: { race: 0.42 },
  },
  population: { age65: 0.216, black: 0.124 },
};

export async function loadHomeMeta(): Promise<HomeMeta> {
  try {
    const stats = await getStats();
    return {
      ...homeMetaSnapshot,
      trials: stats.studies || null,
      refreshed: stats.ingest?.loaded_at?.slice(0, 10) ?? null,
    };
  } catch {
    return homeMetaSnapshot;
  }
}
