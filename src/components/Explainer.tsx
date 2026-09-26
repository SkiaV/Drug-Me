import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent,
  type ReactNode,
} from "react";
import type { HomeMeta } from "../homeData";

/* Scroll-driven explainer modeled on The Pudding piece "Pockets", laid out side by side: the two dot grids
   (IN THE TRIALS | TAKING THE MEDICINE) stay pinned and centred on the right while the text cards scroll past
   them in their own column on the left. The card nearest the middle of the window is the active one and drives
   the figure, so the cards move with the scroll but never cover the dots. The numbers come from homeData.ts.
   With prefers-reduced-motion the steps are a plain list. */

type Dot = "ink" | "dim" | "ghost" | "hl" | "missing";
type Figure = { left: Dot[]; right: Dot[]; leftCap: string; rightCap: string };
type Step = { text: ReactNode; figure: Figure; final?: boolean };

const N = 100;
const grid = (first: Dot, count: number, rest: Dot): Dot[] =>
  Array.from({ length: N }, (_, i) => (i < count ? first : rest));
const solid = (d: Dot) => grid(d, N, d);
const pc = (x: number | null | undefined) => (x == null ? null : Math.round(100 * x));
const reducedMotion = () =>
  typeof window !== "undefined" &&
  !!window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function DotGrid({ dots }: { dots: Dot[] }) {
  return (
    <div className="dots">
      {dots.map((d, i) => (
        <i className={`dot--${d}`} key={i} style={{ "--i": i } as CSSProperties} />
      ))}
    </div>
  );
}

function FigureView({ fig }: { fig: Figure }) {
  return (
    <div aria-hidden="true" className="scrolly__figure">
      <div className="scrolly__col">
        <span className="scrolly__label">In the trials</span>
        <DotGrid dots={fig.left} />
        <span className="scrolly__cap">{fig.leftCap}</span>
      </div>
      <div className="scrolly__col">
        <span className="scrolly__label">Taking the medicine</span>
        <DotGrid dots={fig.right} />
        <span className="scrolly__cap">{fig.rightCap}</span>
      </div>
    </div>
  );
}

export default function Explainer({
  meta,
  onBrowse,
  onCheck,
}: {
  meta: HomeMeta | null;
  onBrowse: () => void;
  onCheck: () => void;
}) {
  const steps = useMemo<Step[]>(() => {
    const r = meta?.registry;
    const p = meta?.population;
    const out: Step[] = [
      {
        text: <p>Before a medicine reaches the pharmacy, it is tested on a few thousand volunteers.</p>,
        figure: {
          left: solid("ink"),
          right: solid("ghost"),
          leftCap: r ? `${r.participants.toLocaleString()} volunteers so far` : "the volunteers",
          rightCap: "the people who will take it",
        },
      },
    ];
    if (r && p) {
      // Registry-wide, women are about as common in trials as in the country (52% vs 51%), so the two groups
      // shown here are the ones with a real gap in the aggregate: older adults and Black participants.
      const old = pc(r.shares.age65);
      const oldPop = pc(p.age65);
      const blk = pc(r.shares.black);
      const blkPop = pc(p.black);
      const miss = pc(r.notReported.race);
      if (old != null && oldPop != null)
        out.push({
          text: (
            <p>
              Who they are matters. Across all {r.trials.toLocaleString()} trials,{" "}
              <mark className="hl">adults 65 and over</mark> were {old}% of participants. They are {oldPop}% of
              adults.
            </p>
          ),
          figure: {
            left: grid("hl", old, "dim"),
            right: grid("hl", oldPop, "dim"),
            leftCap: `${old}% aged 65+`,
            rightCap: `${oldPop}% aged 65+`,
          },
        });
      if (blk != null && blkPop != null)
        out.push({
          text: (
            <p>
              <mark className="hl">Black participants</mark> were {blk}% of the trials and {blkPop}% of the
              country. That average hides big differences between medicines.
            </p>
          ),
          figure: {
            left: grid("hl", blk, "dim"),
            right: grid("hl", blkPop, "dim"),
            leftCap: `${blk}% Black`,
            rightCap: `${blkPop}% Black`,
          },
        });
      if (miss != null)
        out.push({
          text: (
            <p>
              And {miss}% of trials never reported <mark className="hl hl--pop">race</mark> at all. We show the
              blank instead of guessing.
            </p>
          ),
          figure: {
            left: grid("missing", miss, "ink"),
            right: solid("ghost"),
            leftCap: `race not reported in ${miss}% of trials`,
            rightCap: "",
          },
        });
    }
    out.push({
      text: <p>Type a medicine, say who you are, and see who was in the room.</p>,
      figure: { left: solid("ink"), right: solid("ink"), leftCap: "who was tested", rightCap: "who takes it" },
      final: true,
    });
    return out;
  }, [meta]);

  const still = useMemo(() => reducedMotion(), []);
  const [active, setActive] = useState(0);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);

  // The active step is the card whose centre is nearest the reading line: the middle of the window, or a little
  // lower on narrow screens where the figure is pinned across the top.
  useEffect(() => {
    if (still) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const narrow = window.matchMedia("(max-width: 960px)").matches;
      const line = window.innerHeight * (narrow ? 0.64 : 0.5);
      let best = 0;
      let bestDist = Infinity;
      cardRefs.current.forEach((el, i) => {
        if (!el) return;
        const r = el.getBoundingClientRect();
        const d = Math.abs((r.top + r.bottom) / 2 - line);
        if (d < bestDist) {
          bestDist = d;
          best = i;
        }
      });
      setActive(best);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [steps.length, still]);

  const skip = (e: MouseEvent) => {
    e.preventDefault();
    onBrowse();
  };
  const cta = (
    <div className="step__cta">
      <button className="button button--primary" onClick={onCheck} type="button">
        Check a medicine
      </button>
      <button className="button button--outline" onClick={onBrowse} type="button">
        Browse all medicines
      </button>
    </div>
  );

  if (still) {
    return (
      <section className="scrolly scrolly--static" aria-label="How this works">
        <ol className="scrolly__list">
          {steps.map((s, i) => (
            <li key={i}>
              <div className="step__box is-static">
                {s.text}
                {s.final && cta}
              </div>
              <FigureView fig={s.figure} />
            </li>
          ))}
        </ol>
      </section>
    );
  }

  const fig = steps[Math.min(active, steps.length - 1)].figure;
  return (
    <section className="scrolly" aria-label="How this works">
      <div className="scrolly__layout">
        <div className="scrolly__steps">
          {steps.map((s, i) => (
            <div className={`step ${i === active ? "is-active" : ""}`} key={i}>
              <div
                className="step__box"
                ref={(el) => {
                  cardRefs.current[i] = el;
                }}
              >
                {s.text}
                {s.final && cta}
              </div>
            </div>
          ))}
        </div>
        <div className="scrolly__sticky">
          <FigureView fig={fig} />
          <p className="scrolly__skip">
            <a href="/dashboard" onClick={skip}>
              Skip to the medicines
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}
