import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ApiError,
  getDashboard,
  getDrugReport,
  getMeta,
  pct,
  reportPath,
  searchDrugs,
  suggest,
  type DemographicProfile,
  type DrugReport,
  type DrugSummary,
  type Meta,
  type SearchFilters,
} from "./api";
import Banner from "./components/Banner";
import Explainer from "./components/Explainer";
import FaersPanel from "./components/FaersPanel";
import GroupBars from "./components/GroupBars";
import { useCountUp, useReveal } from "./hooks";
import { homeMetaSnapshot, loadHomeMeta, type HomeMeta } from "./homeData";

type Route = "home" | "dashboard" | "search" | "report";

const defaultProfile: DemographicProfile = {
  age: 67,
  sex: "Female",
  race: "Black or African American",
  ethnicity: "All or not specified",
};

const defaultFilters: SearchFilters = {
  ...defaultProfile,
  drug: "",
  indication: "",
  diseaseArea: "",
  minParticipants: "500",
  location: "",
  sponsor: "",
  fromDate: "",
  toDate: "",
};

/* Reports opened from a table without a chosen demographic use a generalized profile. */
const anyoneProfile: DemographicProfile = {
  age: 45,
  sex: "All or not specified",
  race: "All or not specified",
  ethnicity: "All or not specified",
};

/* The demo case: Ambien (zolpidem), whose dose for women was halved by the FDA in 2013. */
const demoReportPath = reportPath("ambien", defaultProfile);

const FLAG_TYPE: Record<string, string> = {
  sex: "Sex differences",
  older_adults: "Older adults",
  children: "Children",
  ancestry_genetics: "Ancestry & genetics",
};

const SECTION: Record<string, string> = {
  dosage_and_administration: "Dosage and administration",
  use_in_specific_populations: "Use in specific populations",
  clinical_pharmacology: "Clinical pharmacology",
  warnings_and_cautions: "Warnings and precautions",
  warnings: "Warnings",
  boxed_warning: "Boxed warning",
  geriatric_use: "Geriatric use",
  pediatric_use: "Pediatric use",
};

function Icon({
  name,
  size = 18,
}: {
  name:
    | "arrow"
    | "book"
    | "check"
    | "chevron"
    | "download"
    | "info"
    | "search"
    | "sliders";
  size?: number;
}) {
  const paths: Record<typeof name, ReactNode> = {
    arrow: (
      <>
        <path d="M5 12h14" />
        <path d="m14 7 5 5-5 5" />
      </>
    ),
    book: (
      <>
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22.5z" />
        <path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5a2.5 2.5 0 0 1 2.5 2.5z" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    download: (
      <>
        <path d="M12 3v12" />
        <path d="m7 10 5 5 5-5" />
        <path d="M5 21h14" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5" />
        <path d="M12 8h.01" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    sliders: (
      <>
        <path d="M4 7h10" />
        <path d="M18 7h2" />
        <circle cx="16" cy="7" r="2" />
        <path d="M4 17h2" />
        <path d="M10 17h10" />
        <circle cx="8" cy="17" r="2" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {paths[name]}
    </svg>
  );
}

function routeFromPath(): Route {
  const path = window.location.pathname;
  if (path.startsWith("/dashboard")) return "dashboard";
  if (path.startsWith("/advanced-search") || path.startsWith("/search")) return "search";
  if (path.startsWith("/report")) return "report";
  return "home";
}

function useRoute() {
  const [route, setRoute] = useState<Route>(routeFromPath);
  // Bumped on every navigation so a page can reload its state from the URL (report -> another report).
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const update = () => {
      setRoute(routeFromPath());
      setTick((current) => current + 1);
    };
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  const navigate = (path: string) => {
    window.history.pushState({}, "", path);
    setRoute(routeFromPath());
    setTick((current) => current + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return { route, navigate, tick };
}

function ScoreRing({ score, large = false }: { score: number | null; large?: boolean }) {
  // The ring draws itself once it scrolls into view; the big report number also counts up.
  const { ref, inView } = useReveal<HTMLDivElement>(0.3);
  const counted = useCountUp(large && inView ? score : null, 1000);
  const drawn = inView ? (score ?? 0) : 0;
  const shown = large ? (counted ?? 0) : score;

  return (
    <div
      aria-label={
        score == null ? "No score available" : `${score} percent provisional representation score`
      }
      className={`score-ring ${large ? "score-ring--large" : ""}`}
      ref={ref}
      role="img"
      style={{ "--score": `${drawn * 3.6}deg` } as CSSProperties}
    >
      <span>
        <strong>{score == null ? "—" : shown}</strong>
        {score != null && <small>%</small>}
      </span>
    </div>
  );
}

function CoverageBars({
  drug,
  detailed = false,
}: {
  drug: DrugSummary;
  detailed?: boolean;
}) {
  const { ref, inView } = useReveal<HTMLDivElement>(0.3);

  return (
    <div className={`coverage-bars ${detailed ? "coverage-bars--detailed" : ""}`} ref={ref}>
      {(["age", "sex", "race"] as const).map((label) => {
        const value = drug.components[label];
        return (
          <div className="coverage-bars__row" key={label}>
            <span>{label}</span>
            <div className="coverage-bars__track">
              <i style={{ "--coverage": `${inView ? (value ?? 0) : 0}%` } as CSSProperties} />
            </div>
            <b>{value == null ? <span className="na">n/a</span> : `${value}%`}</b>
          </div>
        );
      })}
    </div>
  );
}

function Button({
  children,
  className = "",
  disabled,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button className={`button ${className}`} disabled={disabled} onClick={onClick} type={type}>
      {children}
    </button>
  );
}

function AppShell({
  children,
  navigate,
  route,
}: {
  children: ReactNode;
  navigate: (path: string) => void;
  route: Route;
}) {
  return (
    <div className="app-shell">
      <header className="site-header">
        <button className="brand" onClick={() => navigate("/")} type="button">
          <img alt="" className="brand__icon" height="44" src="/drugme-icon-256.png" width="44" />
          <span className="brand__text">Drug Me</span>
        </button>
        <nav aria-label="Primary navigation">
          <button
            aria-current={route === "home" ? "page" : undefined}
            onClick={() => navigate("/")}
            type="button"
          >
            Home
          </button>
          <button
            aria-current={route === "dashboard" ? "page" : undefined}
            onClick={() => navigate("/dashboard")}
            type="button"
          >
            Dashboard
          </button>
          <button
            aria-current={route === "search" ? "page" : undefined}
            onClick={() => navigate("/advanced-search")}
            type="button"
          >
            Advanced search
          </button>
          <button
            aria-current={route === "report" ? "page" : undefined}
            onClick={() => navigate(demoReportPath)}
            type="button"
          >
            Individual report
          </button>
        </nav>
        <span className="prototype-label">Research prototype</span>
      </header>
      {children}
      <footer className="site-footer">
        <div>
          <span>Data sources</span>
          <a href="https://clinicaltrials.gov/data-api/about-api" rel="noreferrer" target="_blank">
            ClinicalTrials.gov API v2
          </a>
          <a href="https://open.fda.gov/apis/drug/label/" rel="noreferrer" target="_blank">
            openFDA labels &amp; FAERS
          </a>
          <a href="https://rxnav.nlm.nih.gov/" rel="noreferrer" target="_blank">
            RxNorm
          </a>
          <a href="https://data.cdc.gov/resource/hksd-2xuw" rel="noreferrer" target="_blank">
            CDC prevalence
          </a>
        </div>
        <p>
          This research prototype describes representation in available evidence. It does not assess
          whether a medicine is safe or appropriate for an individual and is not medical advice. Nothing
          you enter is stored.
        </p>
      </footer>
    </div>
  );
}

function PageIntro({
  eyebrow,
  title,
  description,
  aside,
}: {
  eyebrow: string;
  title: string;
  description: string;
  aside?: ReactNode;
}) {
  return (
    <section className="page-intro">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {aside && <aside>{aside}</aside>}
    </section>
  );
}

function MethodologyNote() {
  return (
    <div className="methodology-note">
      <Icon name="info" />
      <p>
        <strong>How to read the score</strong>
        Each group's share of trial participants is divided by its share of the reference population
        (the participation-to-prevalence ratio). The score is the coverage-weighted average of those
        ratios, capped at 1, across women, adults 65+, Black, Hispanic and Asian participants. Unreported
        rows lower confidence, not the score.
      </p>
    </div>
  );
}

function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="error-state">
      <Icon name="info" />
      <span>{error}</span>
      {onRetry && (
        <button onClick={onRetry} type="button">
          Try again
        </button>
      )}
    </div>
  );
}

function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const { ref, inView } = useReveal<HTMLDivElement>(0.15);
  return (
    <div className={`reveal ${inView ? "is-in" : ""} ${className}`.trim()} ref={ref}>
      {children}
    </div>
  );
}

/* Medicine input with suggestions from RxNorm (brand or generic; a brand resolves to its ingredient). */
function DrugSearch({
  value,
  onChange,
  onPick,
  label = "Medicine (brand or generic)",
  placeholder = "e.g. Ambien, sertraline, metformin",
}: {
  value: string;
  onChange: (value: string) => void;
  onPick?: (value: string) => void;
  label?: string;
  placeholder?: string;
}) {
  const [items, setItems] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const typed = useRef(false);

  useEffect(() => {
    if (!typed.current || value.trim().length < 2) {
      setItems([]);
      return;
    }
    const timer = window.setTimeout(() => {
      suggest(value)
        .then((suggestions) => {
          setItems(suggestions);
          setOpen(true);
          setActive(-1);
        })
        .catch(() => setItems([]));
    }, 150);
    return () => window.clearTimeout(timer);
  }, [value]);

  const pick = (suggestion: string) => {
    typed.current = false;
    onChange(suggestion);
    setOpen(false);
    onPick?.(suggestion);
  };

  return (
    <label className="field drug-search">
      <span>{label}</span>
      <input
        autoComplete="off"
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onChange={(event) => {
          typed.current = true;
          onChange(event.target.value);
        }}
        onFocus={() => {
          if (items.length) setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            setActive((current) => Math.min(current + 1, items.length - 1));
            event.preventDefault();
          } else if (event.key === "ArrowUp") {
            setActive((current) => Math.max(current - 1, 0));
            event.preventDefault();
          } else if (event.key === "Enter") {
            if (open && active >= 0) {
              pick(items[active]);
              event.preventDefault();
            } else {
              setOpen(false);
            }
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
        placeholder={placeholder}
        value={value}
      />
      {open && items.length > 0 && (
        <ul role="listbox">
          {items.map((suggestion, index) => (
            <li
              aria-selected={index === active}
              key={suggestion}
              onMouseDown={() => pick(suggestion)}
              role="option"
            >
              {suggestion}
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}

function DrugTable({
  drugs,
  navigate,
  profile,
  scoreLabel = "Representation score",
}: {
  drugs: DrugSummary[];
  navigate: (path: string) => void;
  profile?: DemographicProfile;
  scoreLabel?: string;
}) {
  const openReport = (drug: DrugSummary) => navigate(reportPath(drug.id, profile ?? anyoneProfile));

  return (
    <div className="data-table-wrap">
      <table className="drug-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Most common use</th>
            <th>Least researched</th>
            <th>{scoreLabel}</th>
          </tr>
        </thead>
        <tbody>
          {drugs.map((drug, index) => (
            <tr key={drug.id}>
              <td>
                <span className="row-index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{drug.name}</strong>
                  <small>
                    {drug.trialCount} trials · {drug.participantCount.toLocaleString()} participants
                  </small>
                </div>
              </td>
              <td>
                <strong>{drug.primaryUse}</strong>
                <small>
                  {drug.otherUses.length ? `+${drug.otherUses.length} more uses` : (drug.diseaseArea ?? "")}
                </small>
              </td>
              <td>
                <span className="dimension-label">{drug.leastResearched.dimension}</span>
                <strong>{drug.leastResearched.group}</strong>
              </td>
              <td>
                <button
                  aria-label={`Open ${drug.name} report`}
                  className="score-cell"
                  onClick={() => openReport(drug)}
                  type="button"
                >
                  <ScoreRing score={drug.score} />
                  <div>
                    <strong>{drug.tier} coverage</strong>
                    <CoverageBars drug={drug} />
                  </div>
                  <Icon name="chevron" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Home({ navigate }: { navigate: (path: string) => void }) {
  const [meta, setMeta] = useState<HomeMeta>(homeMetaSnapshot);

  useEffect(() => {
    let cancelled = false;
    loadHomeMeta().then((data) => {
      if (!cancelled) setMeta(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page">
      <Banner meta={meta} />
      <Explainer
        meta={meta}
        onBrowse={() => navigate("/dashboard")}
        onCheck={() => navigate(demoReportPath)}
      />
    </main>
  );
}

function Dashboard({ navigate }: { navigate: (path: string) => void }) {
  const [drugs, setDrugs] = useState<DrugSummary[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("score-asc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [anyDrug, setAnyDrug] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    const [sortKey, order] =
      sort === "name" ? ["name", "asc"] : ["score", sort === "score-asc" ? "asc" : "desc"];
    Promise.all([getDashboard({ sort: sortKey, order, limit: 150 }), getMeta()])
      .then(([rows, summary]) => {
        setDrugs(rows);
        setMeta(summary);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Could not load the evidence."),
      )
      .finally(() => setLoading(false));
  };

  useEffect(load, [sort]);

  const visibleDrugs = useMemo(() => {
    const needle = query.toLowerCase().trim();
    return drugs.filter((drug) =>
      `${drug.name} ${drug.primaryUse} ${drug.otherUses.join(" ")} ${drug.diseaseArea ?? ""}`
        .toLowerCase()
        .includes(needle),
    );
  }, [drugs, query]);

  const openAnyDrug = (event: FormEvent) => {
    event.preventDefault();
    if (anyDrug.trim()) navigate(reportPath(anyDrug.trim(), anyoneProfile));
  };

  return (
    <main className="page">
      <PageIntro
        aside={<MethodologyNote />}
        description="Explore how closely clinical-trial participants reflect the people who may use common medicines. Every row is built from the Phase 3 trials with posted results in ClinicalTrials.gov."
        eyebrow="The representation index"
        title="Who is reflected in the evidence?"
      />

      <Reveal>
        <section className="metric-strip" aria-label="Evidence summary">
          <article>
            <small>Generic drugs reviewed</small>
            <strong>{meta ? meta.drugsReviewed.toLocaleString() : "…"}</strong>
          </article>
          <article>
            <small>Trials in the evidence base</small>
            <strong>{meta ? meta.trials.toLocaleString() : "…"}</strong>
          </article>
          <article>
            <small>Average coverage (≥2 trials, ≥500 people)</small>
            <strong>{meta?.overallCoverage != null ? `${meta.overallCoverage}%` : "—"}</strong>
          </article>
          <article>
            <small>Evidence refreshed</small>
            <strong>{meta?.refreshed ?? "not loaded"}</strong>
            {meta?.sampleData ? <span>Sample dataset</span> : <span>Live harvest</span>}
          </article>
        </section>
      </Reveal>

      <section className="evidence-section" aria-labelledby="dashboard-results">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Evidence library · Generalized coverage</p>
            <h2 id="dashboard-results">Representation by medicine</h2>
          </div>
          <Button className="button--outline" onClick={() => navigate("/advanced-search")}>
            <Icon name="sliders" /> Search a demographic
          </Button>
        </div>
        <div className="table-controls">
          <label className="search-field">
            <Icon name="search" />
            <span className="sr-only">Filter medicines</span>
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by drug, use or disease area"
              type="search"
              value={query}
            />
          </label>
          <label className="select-field">
            <span className="sr-only">Sort medicines</span>
            <select onChange={(event) => setSort(event.target.value)} value={sort}>
              <option value="score-desc">Most to least covered</option>
              <option value="score-asc">Least to most covered</option>
              <option value="name">Name, A–Z</option>
            </select>
          </label>
        </div>
        {error ? (
          <ErrorState error={error} onRetry={load} />
        ) : loading ? (
          <div className="loading-state">Reviewing the evidence…</div>
        ) : visibleDrugs.length ? (
          <DrugTable drugs={visibleDrugs} navigate={navigate} />
        ) : (
          <div className="empty-state">
            <strong>No medicines match this filter.</strong>
            <span>
              Try a generic drug name or a broader use, or open a report for any medicine below.
            </span>
          </div>
        )}
        <div className="table-caption">
          <p>
            <Icon name="info" />
            Scores describe the completeness of demographic evidence—not drug safety, efficacy, or
            treatment suitability. Rows need at least 2 trials and 500 participants.
          </p>
          <span>
            {visibleDrugs.length} of {drugs.length} records shown
          </span>
        </div>
        <form className="dashboard-any" onSubmit={openAnyDrug}>
          <DrugSearch
            label="Not in the list? Open a report for any medicine"
            onChange={setAnyDrug}
            value={anyDrug}
          />
          <Button className="button--primary" type="submit">
            Open report <Icon name="arrow" />
          </Button>
        </form>
      </section>
    </main>
  );
}

function ProfileFields({
  values,
  onChange,
}: {
  values: DemographicProfile;
  onChange: (profile: DemographicProfile) => void;
}) {
  return (
    <div className="profile-fields">
      <label className="field">
        <span>Age</span>
        <input
          max="120"
          min="0"
          onChange={(event) =>
            onChange({ ...values, age: Number(event.target.value) })
          }
          required
          type="number"
          value={values.age}
        />
      </label>
      <label className="field">
        <span>Sex</span>
        <select
          onChange={(event) =>
            onChange({
              ...values,
              sex: event.target.value as DemographicProfile["sex"],
            })
          }
          value={values.sex}
        >
          <option>Female</option>
          <option>Male</option>
          <option>All or not specified</option>
        </select>
      </label>
      <label className="field">
        <span>Race</span>
        <select
          onChange={(event) =>
            onChange({
              ...values,
              race: event.target.value as DemographicProfile["race"],
            })
          }
          value={values.race}
        >
          <option>American Indian or Alaska Native</option>
          <option>Asian</option>
          <option>Black or African American</option>
          <option>Multiracial</option>
          <option>Native Hawaiian or Pacific Islander</option>
          <option>White</option>
          <option>All or not specified</option>
        </select>
      </label>
      <label className="field">
        <span>Ethnicity</span>
        <select
          onChange={(event) =>
            onChange({
              ...values,
              ethnicity: event.target.value as DemographicProfile["ethnicity"],
            })
          }
          value={values.ethnicity}
        >
          <option>Hispanic or Latino</option>
          <option>Not Hispanic or Latino</option>
          <option>All or not specified</option>
        </select>
      </label>
    </div>
  );
}

function AdvancedSearch({ navigate }: { navigate: (path: string) => void }) {
  const [filters, setFilters] = useState<SearchFilters>(defaultFilters);
  const [results, setResults] = useState<DrugSummary[] | null>(null);
  const [areas, setAreas] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMeta()
      .then((meta) => setAreas(meta.diseaseAreas))
      .catch(() => {});
  }, []);

  const update = (key: keyof SearchFilters, value: string | number) =>
    setFilters((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResults(await searchDrugs(filters));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not search the evidence.");
    } finally {
      setLoading(false);
    }
    window.setTimeout(
      () => document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth" }),
      0,
    );
  };

  return (
    <main className="page">
      <PageIntro
        description="Focus the representation score on a demographic profile, then narrow the evidence by medicine, use, disease area, sponsor, place, or study years."
        eyebrow="Advanced evidence search"
        title="Ask a more specific question."
      />

      <form className="search-form" onSubmit={submit}>
        <section className="form-section">
          <div className="form-section__intro">
            <span>01</span>
            <div>
              <h2>Demographic profile</h2>
              <p>Required. Scores are recalculated for these groups only.</p>
            </div>
          </div>
          <ProfileFields
            onChange={(profile) => setFilters((current) => ({ ...current, ...profile }))}
            values={filters}
          />
        </section>

        <section className="form-section">
          <div className="form-section__intro">
            <span>02</span>
            <div>
              <h2>Clinical filters</h2>
              <p>Optional. The evidence base is every Phase 3 trial with posted results.</p>
            </div>
          </div>
          <div className="clinical-fields">
            <label className="field">
              <span>Generic drug name</span>
              <input
                onChange={(event) => update("drug", event.target.value)}
                placeholder="e.g. sertraline"
                value={filters.drug}
              />
            </label>
            <label className="field">
              <span>Indication or use</span>
              <input
                onChange={(event) => update("indication", event.target.value)}
                placeholder="e.g. depression"
                value={filters.indication}
              />
            </label>
            <label className="field">
              <span>Disease area</span>
              <select
                onChange={(event) => update("diseaseArea", event.target.value)}
                value={filters.diseaseArea}
              >
                <option value="">All disease areas</option>
                {areas.map((area) => (
                  <option key={area} value={area}>
                    {area}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Minimum participants pooled</span>
              <select
                onChange={(event) => update("minParticipants", event.target.value)}
                value={filters.minParticipants}
              >
                <option value="100">100</option>
                <option value="500">500</option>
                <option value="2000">2,000</option>
                <option value="10000">10,000</option>
              </select>
            </label>
            <label className="field">
              <span>Location (country)</span>
              <input
                onChange={(event) => update("location", event.target.value)}
                placeholder="e.g. United States, Japan"
                value={filters.location}
              />
            </label>
            <label className="field">
              <span>Sponsor</span>
              <input
                onChange={(event) => update("sponsor", event.target.value)}
                placeholder="Organization name"
                value={filters.sponsor}
              />
            </label>
            <label className="field">
              <span>Study start from</span>
              <input
                onChange={(event) => update("fromDate", event.target.value)}
                type="date"
                value={filters.fromDate}
              />
            </label>
            <label className="field">
              <span>Study start to</span>
              <input
                onChange={(event) => update("toDate", event.target.value)}
                type="date"
                value={filters.toDate}
              />
            </label>
          </div>
        </section>

        <div className="form-actions">
          <p>
            <Icon name="info" />
            No personal information is saved. Search values are used only for this request.
          </p>
          <Button className="button--primary" disabled={loading} type="submit">
            {loading ? "Calculating…" : "Calculate representation"} <Icon name="arrow" />
          </Button>
        </div>
      </form>

      {error && <ErrorState error={error} />}
      {results && (
        <section className="evidence-section search-results" id="search-results">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Demographic-specific results · least covered first</p>
              <h2>
                Evidence for age {filters.age}, {filters.sex.toLowerCase()},{" "}
                {filters.race.toLowerCase()}
                {filters.ethnicity !== "All or not specified"
                  ? `, ${filters.ethnicity.toLowerCase()}`
                  : ""}
              </h2>
            </div>
            <span className="result-count">{results.length} medicines</span>
          </div>
          {results.length ? (
            <DrugTable
              drugs={results}
              navigate={navigate}
              profile={filters}
              scoreLabel="Profile score"
            />
          ) : (
            <div className="empty-state">
              <strong>No matching evidence was found.</strong>
              <span>Remove one or more optional clinical filters and try again.</span>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function readReportState() {
  const drugId = decodeURIComponent(window.location.pathname.split("/")[2] || "ambien");
  const params = new URLSearchParams(window.location.search);
  return {
    drugId,
    profile: {
      age: Number(params.get("age")) || defaultProfile.age,
      sex: (params.get("sex") as DemographicProfile["sex"]) || defaultProfile.sex,
      race: (params.get("race") as DemographicProfile["race"]) || defaultProfile.race,
      ethnicity:
        (params.get("ethnicity") as DemographicProfile["ethnicity"]) || defaultProfile.ethnicity,
    },
  };
}

function IndividualReport({
  navigate,
  tick,
}: {
  navigate: (path: string) => void;
  tick: number;
}) {
  const initial = readReportState();
  const [drugName, setDrugName] = useState(initial.drugId);
  const [profile, setProfile] = useState<DemographicProfile>(initial.profile);
  const [report, setReport] = useState<DrugReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReport = async (nextDrug = drugName, nextProfile = profile) => {
    if (!nextDrug.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getDrugReport(nextDrug.trim(), nextProfile);
      setReport(data);
      window.history.replaceState({}, "", reportPath(data.drug.id, nextProfile));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Could not build the report.");
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  // Re-read the URL on every navigation, so the nav button and the browser's back/forward reload the report.
  useEffect(() => {
    const state = readReportState();
    setDrugName(state.drugId);
    setProfile(state.profile);
    loadReport(state.drugId, state.profile);
  }, [tick]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    loadReport();
  };

  const exportSummary = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${report.drug.id}-representation-report.json`;
    link.click();
  };

  const details = report?.details;
  const score = report?.personalizedScore ?? null;
  const headline = !report
    ? ""
    : !report.scoreable
      ? "Too little trial data to score this profile."
      : score == null
        ? "Your groups were not reported in these trials."
        : score >= 75
          ? "The evidence is comparatively representative."
          : score >= 55
            ? "The evidence has meaningful coverage gaps."
            : "The evidence has substantial coverage gaps.";

  return (
    <main className="page report-page">
      <PageIntro
        description="Review how the available clinical evidence aligns with one selected demographic profile."
        eyebrow="Individualized evidence report"
        title={report ? `${report.drug.name} representation report` : "Build a representation report."}
      />

      <form className="report-builder" onSubmit={submit}>
        <DrugSearch onChange={setDrugName} onPick={(name) => loadReport(name)} value={drugName} />
        <ProfileFields onChange={setProfile} values={profile} />
        <Button className="button--primary" disabled={loading} type="submit">
          {loading ? "Assembling…" : "Update report"} <Icon name="arrow" />
        </Button>
      </form>
      <p className="inline-note">
        The first report for a medicine takes about 15 seconds while five public APIs are queried; later
        requests are cached.
      </p>

      {error && <ErrorState error={error} onRetry={() => loadReport()} />}
      {loading ? (
        <div className="loading-state">Assembling the evidence report…</div>
      ) : report ? (
        <div className="report">
          <section className="report-summary">
            <div className="report-summary__score">
              <ScoreRing large score={score} />
              <span>Provisional profile score</span>
              {report.diseaseScore != null &&
                report.populationScore != null &&
                report.diseaseScore !== report.populationScore && (
                  <div className="score-secondary">
                    vs. people with this condition · vs. US population: <b>{report.populationScore}%</b>
                  </div>
                )}
            </div>
            <div className="report-summary__copy">
              <p className="eyebrow">Evidence interpretation</p>
              <h2>{headline}</h2>
              <p>{report.summary}</p>
              <div className="profile-chips">
                <span>Age {report.profile.age}</span>
                <span>{report.profile.sex}</span>
                <span>{report.profile.race}</span>
                {report.profile.ethnicity !== "All or not specified" && (
                  <span>{report.profile.ethnicity}</span>
                )}
                {report.drug.brands?.length ? (
                  <span>Sold as {report.drug.brands.slice(0, 4).join(", ")}</span>
                ) : null}
                {report.drug.approvedOn && <span>Approved {report.drug.approvedOn}</span>}
              </div>
              {report.drug.isCombination && (
                <p className="inline-note">
                  Combination product ({report.drug.ingredients?.join(" + ")}). Showing trials for{" "}
                  {report.drug.name.toLowerCase()}; search the other ingredient separately.
                </p>
              )}
            </div>
            <Button className="button--outline" onClick={exportSummary}>
              <Icon name="download" /> Export summary
            </Button>
          </section>

          <Reveal>
            <section className="report-grid">
              <article className="report-card report-card--coverage">
                <p className="eyebrow">Coverage components</p>
                <h3>Where the evidence is strongest</h3>
                <CoverageBars detailed drug={report.drug} />
                <p className="card-note">
                  Component scores use the participation-to-prevalence ratio of each group, weighted by how
                  many participants came from trials that reported the row. "n/a" means no trial reported
                  that dimension.
                  {details && (
                    <>
                      {" "}
                      Based on {details.evidence.trials} trials and{" "}
                      {details.evidence.participants.toLocaleString()} participants
                      {details.evidence.comparator_only
                        ? `; ${details.evidence.comparator_only} comparator-only trial(s) excluded`
                        : ""}
                      .
                    </>
                  )}
                </p>
              </article>
              <article className="report-card">
                <p className="eyebrow">What the evidence shows</p>
                <h3>Strengths and limitations</h3>
                <div className="findings-list findings-list--positive">
                  {report.strengths.map((item) => (
                    <p key={item}>
                      <Icon name="check" /> {item}
                    </p>
                  ))}
                </div>
                <div className="findings-list findings-list--caution">
                  {report.gaps.map((item) => (
                    <p key={item}>
                      <Icon name="info" /> {item}
                    </p>
                  ))}
                </div>
                {report.questions?.length ? (
                  <>
                    <p className="eyebrow" style={{ marginTop: 24 }}>
                      Questions for your doctor or pharmacist
                    </p>
                    <ol className="questions-list">
                      {report.questions.map((question) => (
                        <li key={question}>{question}</li>
                      ))}
                    </ol>
                  </>
                ) : null}
              </article>
            </section>
          </Reveal>

          {details && details.groups.length > 0 && (
            <section className="report-section" aria-labelledby="who-was-in">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Enrollment by group</p>
                  <h2 id="who-was-in">Who was in the trials</h2>
                </div>
                <span className="result-count">
                  {details.evidence.participants.toLocaleString()} participants
                </span>
              </div>
              <GroupBars
                details={details}
                profileGroups={report.profile.groups ?? []}
                trials={details.evidence.trials}
              />
            </section>
          )}

          <section className="report-section" aria-labelledby="trial-evidence">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Supporting evidence</p>
                <h2 id="trial-evidence">Trials behind this report</h2>
              </div>
              <span className="result-count">{report.evidence.length} trials with posted results</span>
            </div>
            {report.evidence.length === 0 ? (
              <div className="empty-state">
                <strong>No Phase 3 trials with posted demographic results.</strong>
                <span>
                  {details?.evidence.note ??
                    "ClinicalTrials.gov results reporting began in 2008; older approvals are not visible here."}
                </span>
              </div>
            ) : (
              <div className="trial-list">
                {report.evidence.map((item) => (
                  <a href={item.sourceUrl} key={item.id} rel="noreferrer" target="_blank">
                    <div>
                      <span className={item.match === "Comparator only" ? "cmp" : ""}>
                        {item.id} · {item.match}
                      </span>
                      <strong>{item.title}</strong>
                    </div>
                    <dl>
                      <div>
                        <dt>Years · sponsor</dt>
                        <dd>
                          {item.years?.[0] ?? "?"}–{item.years?.[1] ?? "?"} · {item.sponsorClass ?? "?"}
                        </dd>
                      </div>
                      <div>
                        <dt>Enrollment</dt>
                        <dd>
                          {item.enrollment.toLocaleString()}
                          {item.sitesTotal ? ` · ${item.sitesUs}/${item.sitesTotal} US sites` : ""}
                        </dd>
                      </div>
                      <div>
                        <dt>Ages allowed</dt>
                        <dd>
                          {item.agesAllowed}
                          {item.sexAllowed && item.sexAllowed !== "ALL"
                            ? ` · ${item.sexAllowed.toLowerCase()} only`
                            : ""}
                        </dd>
                      </div>
                      <div>
                        <dt>Women · 65+</dt>
                        <dd>
                          {pct(item.femaleShare)} ·{" "}
                          {item.age65Share != null ? (
                            pct(item.age65Share)
                          ) : item.meanAge != null ? (
                            <span className="muted">mean age {item.meanAge}</span>
                          ) : (
                            "—"
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Race table</dt>
                        <dd className={item.raceReported ? "" : "muted"}>
                          {item.raceReported ? item.raceTitle : "not reported"}
                        </dd>
                      </div>
                    </dl>
                    <Icon name="arrow" />
                  </a>
                ))}
              </div>
            )}
          </section>

          <Reveal>
            <section className="fda-context fda-context--stack">
              <div>
                <span className="source-mark">FDA</span>
                <div>
                  <p className="eyebrow">
                    Labeling context
                    {report.fdaContext.labelUpdated
                      ? ` · label effective ${report.fdaContext.labelUpdated}`
                      : ""}
                  </p>
                  <h2>{report.fdaContext.indication}</h2>
                </div>
              </div>
              {report.fdaContext.insufficient65 && (
                <p>
                  <strong>
                    The label states that clinical studies did not include sufficient numbers of subjects
                    aged 65 and over.
                  </strong>
                </p>
              )}
              {report.fdaContext.flags?.length ? (
                <div className="label-quotes">
                  {report.fdaContext.flags.map((flag, index) => (
                    <blockquote key={index}>
                      <span>
                        {FLAG_TYPE[flag.type] ?? flag.type} · {SECTION[flag.section] ?? flag.section}
                      </span>
                      “{flag.quote}”
                    </blockquote>
                  ))}
                </div>
              ) : (
                <p>{report.fdaContext.note}</p>
              )}
              <a href={report.fdaContext.sourceUrl} rel="noreferrer" target="_blank">
                View the full label <Icon name="arrow" />
              </a>
            </section>
          </Reveal>

          {details?.faers && details.faers.reports > 0 && (
            <section className="report-section" aria-labelledby="faers">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">After approval</p>
                  <h2 id="faers">Side-effect reports by sex</h2>
                </div>
                <span className="result-count">openFDA FAERS</span>
              </div>
              <FaersPanel faers={details.faers} />
            </section>
          )}

          {details && (
            <section className="report-section">
              <p className="eyebrow">Method and limits</p>
              <div className="findings-list findings-list--caution">
                <p>
                  <Icon name="info" /> {details.method.metric}
                </p>
                <p>
                  <Icon name="info" /> {details.method.score}
                </p>
                {details.method.limits.map((limit) => (
                  <p key={limit}>
                    <Icon name="info" /> {limit}
                  </p>
                ))}
                <p>
                  <Icon name="info" /> Population denominator: {details.denominators.population}. Trials
                  from{" "}
                  {details.evidence.source === "harvest"
                    ? "the local registry harvest"
                    : "a live ClinicalTrials.gov query"}
                  .
                </p>
              </div>
            </section>
          )}

          <section className="report-disclaimer">
            <Icon name="book" size={24} />
            <div>
              <strong>Use this report as a starting point, not a clinical conclusion.</strong>
              <p>
                Trial representation is one part of understanding medical evidence. Eligibility criteria,
                study design, dosage, outcomes, and individual health factors also matter. Take the
                questions above to a clinician.
              </p>
            </div>
            <Button className="button--text" onClick={() => navigate("/advanced-search")}>
              Explore another question <Icon name="arrow" />
            </Button>
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default function App() {
  const { route, navigate, tick } = useRoute();

  return (
    <AppShell navigate={navigate} route={route}>
      {route === "home" && <Home navigate={navigate} />}
      {route === "dashboard" && <Dashboard navigate={navigate} />}
      {route === "search" && <AdvancedSearch navigate={navigate} />}
      {route === "report" && <IndividualReport navigate={navigate} tick={tick} />}
    </AppShell>
  );
}
