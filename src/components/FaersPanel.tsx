import { pct, type Faers } from "../api";

/* Side-effect reports (openFDA FAERS) for the drug: how many were about women versus the all-drugs baseline,
   the reactions that skew female, and a small hand-drawn line chart of reports per year by sex. */

function niceCeiling(value: number) {
  if (value <= 0) return 1;
  const power = Math.pow(10, Math.floor(Math.log10(value)));
  const step = [1, 2, 5, 10].find((candidate) => candidate * power >= value) ?? 10;
  return step * power;
}

function compact(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}

function YearChart({ rows }: { rows: Faers["by_year"] }) {
  const width = 520;
  const height = 230;
  const left = 46;
  const right = 12;
  const top = 12;
  const bottom = 26;
  const maxValue = niceCeiling(Math.max(1, ...rows.map((row) => Math.max(row.female, row.male))));
  const xAt = (index: number) =>
    rows.length === 1 ? left : left + ((width - left - right) * index) / (rows.length - 1);
  const yAt = (value: number) => top + (height - top - bottom) * (1 - value / maxValue);
  const path = (key: "female" | "male") =>
    rows
      .map((row, index) => `${index === 0 ? "M" : "L"}${xAt(index).toFixed(1)} ${yAt(row[key]).toFixed(1)}`)
      .join(" ");
  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((fraction) => fraction * maxValue);
  const labelEvery = Math.max(1, Math.ceil(rows.length / 6));

  return (
    <svg
      aria-label="Side-effect reports per year, women and men"
      className="faers-chart"
      role="img"
      viewBox={`0 0 ${width} ${height}`}
    >
      {gridValues.map((value) => (
        <g key={value}>
          <line stroke="var(--line-soft)" x1={left} x2={width - right} y1={yAt(value)} y2={yAt(value)} />
          <text fill="var(--muted)" fontSize="10" textAnchor="end" x={left - 6} y={yAt(value) + 3}>
            {compact(value)}
          </text>
        </g>
      ))}
      {rows.map(
        (row, index) =>
          (index % labelEvery === 0 || index === rows.length - 1) && (
            <text
              fill="var(--muted)"
              fontSize="10"
              key={row.year}
              textAnchor="middle"
              x={xAt(index)}
              y={height - 8}
            >
              {row.year}
            </text>
          ),
      )}
      <path d={path("female")} fill="none" stroke="var(--teal)" strokeWidth="2" />
      <path d={path("male")} fill="none" stroke="var(--caution)" strokeWidth="2" />
      {rows.map((row, index) => (
        <g key={row.year}>
          <circle cx={xAt(index)} cy={yAt(row.female)} fill="var(--teal)" r="3">
            <title>{`${row.year}: ${row.female.toLocaleString()} reports about women`}</title>
          </circle>
          <circle cx={xAt(index)} cy={yAt(row.male)} fill="var(--caution)" r="3">
            <title>{`${row.year}: ${row.male.toLocaleString()} reports about men`}</title>
          </circle>
        </g>
      ))}
    </svg>
  );
}

export default function FaersPanel({ faers }: { faers: Faers }) {
  return (
    <div className="faers-grid">
      <div>
        <section
          aria-label="Adverse-event summary"
          className="metric-strip"
          style={{ gridTemplateColumns: "1fr 1fr", borderTop: 0 }}
        >
          <article>
            <small>Side-effect reports (FAERS)</small>
            <strong>{faers.reports.toLocaleString()}</strong>
          </article>
          <article>
            <small>About women</small>
            <strong>{pct(faers.female_share)}</strong>
          </article>
          <article>
            <small>Women, all drugs</small>
            <strong>{pct(faers.baseline_female_share)}</strong>
          </article>
          <article>
            <small>Ratio to baseline</small>
            <strong>{faers.ratio ?? "—"}×</strong>
          </article>
        </section>
        {faers.reactions_skew_female.length > 0 && (
          <table className="faers-table">
            <thead>
              <tr>
                <th>Reported more often by women</th>
                <th>Women</th>
                <th>Men</th>
                <th>Ratio</th>
              </tr>
            </thead>
            <tbody>
              {faers.reactions_skew_female.slice(0, 6).map((reaction) => (
                <tr key={reaction.reaction}>
                  <td>{reaction.reaction}</td>
                  <td>{reaction.female.toLocaleString()}</td>
                  <td>{reaction.male.toLocaleString()}</td>
                  <td>{reaction.ratio}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div>
        {faers.by_year.length > 1 && <YearChart rows={faers.by_year} />}
        <div className="chart-legend">
          <span>
            <i style={{ background: "var(--teal)" }} />
            Reports about women, per year
          </span>
          <span>
            <i style={{ background: "var(--caution)" }} />
            Reports about men, per year
          </span>
        </div>
        <p className="inline-note">
          {faers.note} The current year is partial. Reaction ratios divide by each sex's own total, which
          removes the "women file more reports" baseline.
        </p>
      </div>
    </div>
  );
}
