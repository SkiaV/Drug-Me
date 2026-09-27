import { BAND_LABEL, pct, type Group, type ReportDetails } from "../api";
import { useReveal } from "../hooks";

const ORDER = [
  "female",
  "male",
  "age65",
  "under18",
  "white",
  "black",
  "hispanic",
  "asian",
  "aian",
  "nhpi",
  "multiracial",
];

/* "Who was in the trials": one editorial bar per group. The bar is the group's share of pooled trial
   participants; the black tick is its share of the US population and the red tick its share of the people
   who have the condition (when CDC has a prevalence series). Not-reported rows are hatched, never blank. */
export default function GroupBars({
  details,
  profileGroups,
  trials,
}: {
  details: ReportDetails;
  profileGroups: string[];
  trials: number;
}) {
  const { ref, inView } = useReveal<HTMLDivElement>(0.2);
  const mine = new Set(profileGroups);
  const hasDisease = !!details.denominators.disease;
  const groups = [...details.groups]
    .filter((group) => mine.has(group.key) || !["male", "under18"].includes(group.key))
    .sort(
      (a, b) =>
        (mine.has(b.key) ? 1 : 0) - (mine.has(a.key) ? 1 : 0) ||
        ORDER.indexOf(a.key) - ORDER.indexOf(b.key),
    );
  const max =
    Math.max(
      0.6,
      ...groups.map((group) =>
        Math.max(group.trial_share ?? 0, group.expected_pop, group.expected_disease ?? 0),
      ),
    ) * 1.08;
  const x = (value: number) => `${Math.min(100, (100 * value) / max)}%`;

  return (
    <div>
      <div className="rep-bars" ref={ref}>
        {groups.map((group: Group) => {
          const band = hasDisease && group.band_disease ? group.band_disease : group.band_pop;
          const ratio = hasDisease && group.ppr_disease != null ? group.ppr_disease : group.ppr_pop;
          const missing = group.trial_share == null;
          const notApplicable = band === "na_by_design";
          return (
            <div className={`rep-row ${mine.has(group.key) ? "rep-row--mine" : ""}`} key={group.key}>
              <div className="rep-label">
                <strong>
                  {group.label}
                  {mine.has(group.key) ? " · your profile" : ""}
                </strong>
                <small>
                  {missing
                    ? `Not reported in ${group.trials_missing} of ${trials} trials`
                    : `${group.trials_reporting} of ${trials} trials report it`}
                  {group.trials_design_excluded > 0 &&
                    ` · ${group.trials_design_excluded} excluded by protocol`}
                </small>
              </div>
              <div
                className="rep-track"
                title={missing ? "Not reported" : `${pct(group.trial_share, 1)} of participants`}
              >
                {notApplicable ? null : missing ? (
                  <div className="rep-fill rep-fill--missing" />
                ) : (
                  <div className="rep-fill" style={{ width: inView ? x(group.trial_share!) : "0%" }} />
                )}
                {!notApplicable && (
                  <div
                    className="rep-tick"
                    style={{ left: x(group.expected_pop) }}
                    title={`US population: ${pct(group.expected_pop)}`}
                  />
                )}
                {!notApplicable && group.expected_disease != null && (
                  <div
                    className="rep-tick rep-tick--disease"
                    style={{ left: x(group.expected_disease) }}
                    title={`People with this condition: ${pct(group.expected_disease)}`}
                  />
                )}
              </div>
              <div className="rep-value">
                {missing || notApplicable ? null : (
                  <>
                    <b>{pct(group.trial_share)}</b>
                    {ratio != null && <span className="ratio"> · {ratio}× expected</span>}
                  </>
                )}
                <span className={`rep-band rep-band--${band}`}>{BAND_LABEL[band] || band}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="rep-legend">
        <span>
          <i style={{ background: "var(--teal)" }} /> share of trial participants
        </span>
        <span>
          <i className="tick" style={{ background: "var(--ink)" }} /> expected from the US population
        </span>
        {hasDisease && (
          <span>
            <i className="tick" style={{ background: "var(--caution)" }} /> expected from people with this
            condition
          </span>
        )}
        <span>
          <i className="rep-fill--missing" style={{ width: 22 }} /> not reported
        </span>
      </div>
      <p className="rep-note">
        Ratio = participation-to-prevalence (trial share ÷ expected share); 0.8–1.2 is considered comparable
        (Scott et al., JACC 2018).
        {hasDisease && (
          <>
            {" "}
            Condition denominator: {details.denominators.disease!.question} (
            {details.denominators.disease!.year}), CDC Chronic Disease Indicators
            {details.denominators.disease!.proxy ? " — a proxy indicator" : ""}.
          </>
        )}{" "}
        Trials that excluded a group by protocol count as zero for that group; unreported rows count for
        nothing.
      </p>
    </div>
  );
}
