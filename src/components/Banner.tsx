import { useLayoutEffect, useRef, useState } from "react";
import type { HomeMeta } from "../homeData";

/* Modeled on the header of The Pudding piece "Pockets" (pudding.cool/2018/08/pockets): a panel with a dashed
   inset border, a quiet eyebrow and question, a giant title drawn as dashed outlines, and one letter swapped for
   a small drawing (their pocket with a note; our half-filled capsule). */

const VIEW_W = 1000;
const FONT = 170;
const GAP = 16;
const CAP_W = FONT * 0.8;
const CAP_H = FONT * 0.44;

export default function Banner({ meta }: { meta: HomeMeta | null }) {
  const peRef = useRef<SVGTextElement>(null);
  const pleRef = useRef<SVGTextElement>(null);
  const [widths, setWidths] = useState({ pe: 235, ple: 335 }); // estimates until the text is measured

  useLayoutEffect(() => {
    try {
      const pe = peRef.current?.getComputedTextLength();
      const ple = pleRef.current?.getComputedTextLength();
      if (pe && ple) setWidths({ pe, ple });
    } catch {
      /* keep the estimates */
    }
  }, []);

  const total = widths.pe + GAP + CAP_W + GAP + widths.ple;
  const x0 = (VIEW_W - total) / 2;
  const row1 = FONT; // baseline of "PE PLE"
  const row2 = FONT * 2.08; // baseline of "LIKE ME?"
  const capX = x0 + widths.pe + GAP + CAP_W / 2;
  const capY = row1 - FONT * 0.36; // middle of the capital letters
  const pleX = x0 + widths.pe + GAP + CAP_W + GAP;

  return (
    <section className="banner" aria-labelledby="banner-title">
      <div className="banner__panel">
        <p className="banner__lead">
          <span className="banner__lead-a">Every new medicine is tested on volunteers</span>
          <span className="banner__lead-b">Was this one tested on</span>
        </p>
        <h1 className="sr-only" id="banner-title">
          Was this medicine tested on people like me?
        </h1>
        <svg
          aria-hidden="true"
          className="banner__title"
          focusable="false"
          viewBox={`0 0 ${VIEW_W} ${FONT * 2.35}`}
        >
          <defs>
            <clipPath id="banner-capsule-clip">
              <rect height={CAP_H} rx={CAP_H / 2} width={CAP_W} x={-CAP_W / 2} y={-CAP_H / 2} />
            </clipPath>
          </defs>
          <g className="banner__letters">
            <text ref={peRef} x={x0} y={row1}>
              PE
            </text>
            <text ref={pleRef} x={pleX} y={row1}>
              PLE
            </text>
            <text textAnchor="middle" x={VIEW_W / 2} y={row2}>
              LIKE ME?
            </text>
          </g>
          <g className="banner__capsule" transform={`translate(${capX} ${capY}) rotate(-24)`}>
            <rect
              className="banner__capsule-fill"
              clipPath="url(#banner-capsule-clip)"
              height={CAP_H}
              width={CAP_W / 2}
              x={-CAP_W / 2}
              y={-CAP_H / 2}
            />
            <rect height={CAP_H} rx={CAP_H / 2} width={CAP_W} x={-CAP_W / 2} y={-CAP_H / 2} />
            <line x1={0} x2={0} y1={-CAP_H / 2} y2={CAP_H / 2} />
          </g>
        </svg>
      </div>
      <p className="banner__byline">
        {meta?.trials ? (
          <>
            Built from <b>{meta.trials.toLocaleString()}</b> completed Phase III studies
          </>
        ) : (
          <>Built from completed Phase III studies</>
        )}
        {" · "}ClinicalTrials.gov{meta?.refreshed ? <> · refreshed {meta.refreshed}</> : null}
      </p>
    </section>
  );
}
