import { getMeta } from "./api";

/* Numbers behind the home page.
   - Live: /api/v1/meta gives the trial count, the refresh date, the registry-wide participant shares and the
     2020 Census reference shares (age65 = share of adults).
   - Snapshot: the same numbers as of 2026-09-26, shown until the API answers or when it cannot be reached. */

export type HomeMeta = {
  /** Trials behind this site; filled from the backend when it answers. */
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
    const meta = await getMeta();
    return {
      trials: meta.trials || null,
      refreshed: meta.refreshed,
      registry: meta.registry ?? homeMetaSnapshot.registry,
      population: meta.population ?? homeMetaSnapshot.population,
    };
  } catch {
    return homeMetaSnapshot;
  }
}
