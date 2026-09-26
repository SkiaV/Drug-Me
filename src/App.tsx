import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  getDashboard,
  getDrugReport,
  searchDrugs,
  type BackendStats,
  type DemographicProfile,
  type DrugReport,
  type DrugSummary,
  type SearchFilters,
} from "./api";

type Route = "dashboard" | "search" | "report";

const defaultProfile: DemographicProfile = {
  age: 67,
  sex: "Female",
  race: "Black or African American",
};

const defaultFilters: SearchFilters = {
  ...defaultProfile,
  drug: "",
  indication: "",
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
  if (window.location.pathname.startsWith("/advanced-search")) return "search";
  if (window.location.pathname.startsWith("/report")) return "report";
  return "dashboard";
}

function useRoute() {
  const [route, setRoute] = useState<Route>(routeFromPath);

  useEffect(() => {
    const update = () => setRoute(routeFromPath());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  const navigate = (path: string) => {
    window.history.pushState({}, "", path);
    setRoute(routeFromPath());
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return { route, navigate };
}

function ScoreRing({ score, large = false }: { score: number; large?: boolean }) {
  return (
    <div
      aria-label={`${score} percent provisional representation score`}
      className={`score-ring ${large ? "score-ring--large" : ""}`}
      role="img"
      style={{ "--score": `${score * 3.6}deg` } as CSSProperties}
    >
      <span>
        <strong>{score}</strong>
        <small>%</small>
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
  return (
    <div className={`coverage-bars ${detailed ? "coverage-bars--detailed" : ""}`}>
      {Object.entries(drug.components).map(([label, value]) => (
        <div className="coverage-bars__row" key={label}>
          <span>{label}</span>
          <div className="coverage-bars__track">
            <i style={{ "--coverage": `${value}%` } as CSSProperties} />
          </div>
          <b>{value}%</b>
        </div>
      ))}
    </div>
  );
}

function Button({
  children,
  className = "",
  onClick,
  type = "button",
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button className={`button ${className}`} onClick={onClick} type={type}>
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
          <span>CTR</span>
          <strong>
            Clinical Trial
            <br />
            Representation
          </strong>
        </button>
        <nav aria-label="Primary navigation">
          <button
            aria-current={route === "dashboard" ? "page" : undefined}
            onClick={() => navigate("/")}
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
            onClick={() =>
              navigate(
                "/report/fluoxetine?age=67&sex=Female&race=Black%20or%20African%20American",
              )
            }
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
            openFDA drug labeling (not connected)
          </a>
        </div>
        <p>
          This research prototype describes representation in available evidence.
          It does not assess whether a medicine is safe or appropriate for an
          individual and is not medical advice.
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
        Coverage uses protocol age eligibility, reported sex counts, and race
        reporting. Scores are provisional while the methodology is under review.
      </p>
    </div>
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
  const openReport = (drug: DrugSummary) => {
    const params = profile
      ? `?${new URLSearchParams({
          age: String(profile.age),
          sex: profile.sex,
          race: profile.race,
        })}`
      : "";
    navigate(`/report/${drug.id}${params}`);
  };

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
                  <small>{drug.trialCount} trials analyzed</small>
                </div>
              </td>
              <td>
                <strong>{drug.primaryUse}</strong>
                <small>+{drug.otherUses.length} more uses</small>
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

function Dashboard({ navigate }: { navigate: (path: string) => void }) {
  const [drugs, setDrugs] = useState<DrugSummary[]>([]);
  const [stats, setStats] = useState<BackendStats | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("score-desc");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getDashboard()
      .then(({ drugs, stats }) => {
        setDrugs(drugs);
        setStats(stats);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load the database."))
      .finally(() => setLoading(false));
  }, []);

  const visibleDrugs = useMemo(() => {
    const filtered = drugs.filter((drug) =>
      `${drug.name} ${drug.primaryUse}`.toLowerCase().includes(query.toLowerCase()),
    );
    return [...filtered].sort((a, b) => {
      if (sort === "score-asc") return a.score - b.score;
      if (sort === "name") return a.name.localeCompare(b.name);
      return b.score - a.score;
    });
  }, [drugs, query, sort]);

  return (
    <main className="page">
      <PageIntro
        aside={<MethodologyNote />}
        description="Explore how closely clinical-trial participants reflect the people who may use common medicines."
        eyebrow="The representation index"
        title="Who is reflected in the evidence?"
      />

      <section className="metric-strip" aria-label="Evidence summary">
        <article>
          <small>Generic drugs reviewed</small>
          <strong>{stats?.distinct_drugs.toLocaleString() ?? "—"}</strong>
        </article>
        <article>
          <small>Trials in the evidence base</small>
          <strong>{stats?.studies.toLocaleString() ?? "—"}</strong>
        </article>
        <article>
          <small>Trials reporting race</small>
          <strong>{stats?.studies ? `${Math.round((stats.with_race_composition / stats.studies) * 100)}%` : "—"}</strong>
        </article>
        <article>
          <small>Evidence refreshed</small>
          <strong>{stats?.ingest?.loaded_at ? new Date(stats.ingest.loaded_at).toLocaleDateString() : "Not reported"}</strong>
          <span>SQLite database</span>
        </article>
      </section>

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
            <span className="sr-only">Search generic medicines</span>
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a generic drug or use"
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
          <div className="empty-state"><strong>Could not load trial data.</strong><span>{error}</span></div>
        ) : loading ? (
          <div className="loading-state">Reviewing the evidence…</div>
        ) : visibleDrugs.length ? (
          <DrugTable drugs={visibleDrugs} navigate={navigate} />
        ) : (
          <div className="empty-state">
            <strong>No medicines match this search.</strong>
            <span>Try a generic drug name or a broader use.</span>
          </div>
        )}
        <div className="table-caption">
          <p>
            <Icon name="info" />
            Scores describe the completeness of demographic evidence—not drug
            safety, efficacy, or treatment suitability. Dashboard summaries use
            the first 200 studies returned by the API.
          </p>
          <span>{visibleDrugs.length} medicines shown</span>
        </div>
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
          required
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
          required
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
    </div>
  );
}

function AdvancedSearch({ navigate }: { navigate: (path: string) => void }) {
  const [filters, setFilters] = useState<SearchFilters>(defaultFilters);
  const [results, setResults] = useState<DrugSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const update = (key: keyof SearchFilters, value: string | number) =>
    setFilters((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResults(await searchDrugs(filters));
    } catch (reason) {
      setResults([]);
      setError(reason instanceof Error ? reason.message : "Could not search studies.");
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
        description="Focus the evidence search on a demographic profile, then narrow by medicine or condition."
        eyebrow="Advanced evidence search"
        title="Ask a more specific question."
      />

      <form className="search-form" onSubmit={submit}>
        <section className="form-section">
          <div className="form-section__intro">
            <span>01</span>
            <div>
              <h2>Demographic profile</h2>
              <p>Choose a demographic profile to filter the available studies.</p>
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
              <p>Optionally narrow by medicine or condition.</p>
            </div>
          </div>
          <div className="clinical-fields">
            <label className="field">
              <span>Generic drug name</span>
              <input
                onChange={(event) => update("drug", event.target.value)}
                placeholder="e.g. fluoxetine"
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
          </div>
        </section>

        <div className="form-actions">
          <p>
            <Icon name="info" />
            No personal information is saved. Search values are used only for
            this session.
          </p>
          <Button className="button--primary" type="submit">
            {loading ? "Calculating…" : "Calculate representation"} <Icon name="arrow" />
          </Button>
        </div>
      </form>

      {results && (
        <section className="evidence-section search-results" id="search-results">
          {error && <div className="empty-state"><strong>Search failed.</strong><span>{error}</span></div>}
          <div className="section-heading">
            <div>
              <p className="eyebrow">Demographic-specific results</p>
              <h2>
                Evidence for age {filters.age}, {filters.sex.toLowerCase()},{" "}
                {filters.race.toLowerCase()}
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
  const drugId = window.location.pathname.split("/")[2] || "fluoxetine";
  const params = new URLSearchParams(window.location.search);
  return {
    drugId,
    profile: {
      age: Number(params.get("age")) || defaultProfile.age,
      sex: (params.get("sex") as DemographicProfile["sex"]) || defaultProfile.sex,
      race: (params.get("race") as DemographicProfile["race"]) || defaultProfile.race,
    },
  };
}

function IndividualReport({ navigate }: { navigate: (path: string) => void }) {
  const initial = readReportState();
  const [drugId, setDrugId] = useState(initial.drugId);
  const [profile, setProfile] = useState<DemographicProfile>(initial.profile);
  const [availableDrugs, setAvailableDrugs] = useState<DrugSummary[]>([]);
  const [report, setReport] = useState<DrugReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadReport = async (nextDrug = drugId, nextProfile = profile) => {
    setLoading(true);
    setError("");
    try {
      const data = await getDrugReport(nextDrug, nextProfile);
      setReport(data);
      const params = new URLSearchParams({
        age: String(nextProfile.age),
        sex: nextProfile.sex,
        race: nextProfile.race,
      });
      const nextUrl = `/report/${nextDrug}?${params}`;
      if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
        window.history.replaceState({}, "", nextUrl);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load this report.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    getDashboard()
      .then(({ drugs }) => setAvailableDrugs(drugs))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load medicines."));
    loadReport(initial.drugId, initial.profile);
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    loadReport();
  };

  return (
    <main className="page report-page">
      <PageIntro
        description="Review how the available clinical evidence aligns with one selected demographic profile."
        eyebrow="Individualized evidence report"
        title={report ? `${report.drug.name} representation report` : "Build a representation report."}
      />

      <form className="report-builder" onSubmit={submit}>
        <label className="field">
          <span>Generic drug</span>
          <select onChange={(event) => setDrugId(event.target.value)} value={drugId}>
            {!availableDrugs.some((drug) => drug.id === drugId) && report && (
              <option value={drugId}>{report.drug.name}</option>
            )}
            {availableDrugs
              .slice()
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((drug) => <option key={drug.id} value={drug.id}>{drug.name}</option>)}
          </select>
        </label>
        <ProfileFields onChange={setProfile} values={profile} />
        <Button className="button--primary" type="submit">
          Update report <Icon name="arrow" />
        </Button>
      </form>

      {error && <div className="empty-state"><strong>Report unavailable.</strong><span>{error}</span></div>}
      {loading ? (
        <div className="loading-state">Assembling the evidence report…</div>
      ) : report ? (
        <div className="report">
          <section className="report-summary">
            <div className="report-summary__score">
              <ScoreRing large score={report.personalizedScore} />
              <span>Provisional profile score</span>
            </div>
            <div className="report-summary__copy">
              <p className="eyebrow">Evidence interpretation</p>
              <h2>
                {report.personalizedScore >= 75
                  ? "The evidence is comparatively representative."
                  : report.personalizedScore >= 55
                    ? "The evidence has meaningful coverage gaps."
                    : "The evidence has substantial coverage gaps."}
              </h2>
              <p>{report.summary}</p>
              <div className="profile-chips">
                <span>Age {report.profile.age}</span>
                <span>{report.profile.sex}</span>
                <span>{report.profile.race}</span>
              </div>
            </div>
            <Button className="button--outline">
              <Icon name="download" /> Export summary
            </Button>
          </section>

          <section className="report-grid">
            <article className="report-card report-card--coverage">
              <p className="eyebrow">Coverage components</p>
              <h3>Where the evidence is strongest</h3>
              <CoverageBars detailed drug={report.drug} />
              <p className="card-note">
                Component scores reflect the generalized evidence base. The
                profile score applies demographic-specific adjustments.
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
            </article>
          </section>

          <section className="report-section" aria-labelledby="trial-evidence">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Supporting evidence</p>
                <h2 id="trial-evidence">Relevant clinical trials</h2>
              </div>
              <span className="result-count">{report.drug.trialCount} total trials</span>
            </div>
            <div className="trial-list">
              {report.evidence.map((item) => (
                <a href={item.sourceUrl} key={item.id} rel="noreferrer" target="_blank">
                  <div>
                    <span>{item.id}</span>
                    <strong>{item.title}</strong>
                  </div>
                  <dl>
                    <div>
                      <dt>Study type</dt>
                      <dd>{item.phase}</dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>{item.status}</dd>
                    </div>
                    <div>
                      <dt>Enrollment</dt>
                      <dd>{item.enrollment.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>Profile match</dt>
                      <dd>{item.match}</dd>
                    </div>
                  </dl>
                  <Icon name="arrow" />
                </a>
              ))}
            </div>
          </section>

          <section className="fda-context">
            <div>
              <span className="source-mark">FDA</span>
              <div>
                <p className="eyebrow">Labeling context</p>
                <h2>{report.fdaContext.indication}</h2>
              </div>
            </div>
            <p>{report.fdaContext.note}</p>
            <a href={report.fdaContext.sourceUrl} rel="noreferrer" target="_blank">
              View openFDA source <Icon name="arrow" />
            </a>
          </section>

          <section className="report-disclaimer">
            <Icon name="book" size={24} />
            <div>
              <strong>Use this report as a starting point, not a clinical conclusion.</strong>
              <p>
                Trial representation is one part of understanding medical
                evidence. Eligibility criteria, study design, dosage, outcomes,
                and individual health factors also matter.
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
  const { route, navigate } = useRoute();

  return (
    <AppShell navigate={navigate} route={route}>
      {route === "dashboard" && <Dashboard navigate={navigate} />}
      {route === "search" && <AdvancedSearch navigate={navigate} />}
      {route === "report" && <IndividualReport navigate={navigate} />}
    </AppShell>
  );
}
