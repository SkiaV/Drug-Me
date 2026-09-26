# Dashboard Visual Concepts Plan

## Objective

Create a focused concept-review experience for **Clinical Trial Representation** so the user can compare three distinct visual directions before one is applied to the complete product. This phase is intentionally a visual prototype, not the full dashboard/search/report implementation and not yet connected to Flask.

The three concepts will represent:

1. **Clinical research editorial** — calm, evidence-led, and authoritative.
2. **Traditional clinical dashboard** — compact, familiar, and operational.
3. **Consumer health** — approachable, explanatory, and visually bold.

After review, the selected direction will become the design language for the generalized dashboard, advanced search, and individualized report in a subsequent implementation phase.

## Repository Baseline

- The repository is a minimal React 19 + Vite 8 + Tailwind CSS v4 app.
- `src/App.tsx` currently renders an empty centered container.
- `src/index.css` only imports Tailwind.
- There is no router, component library, icon library, data layer, or existing design system to preserve.
- The existing `src/main.tsx` entrypoint and Vite/Tailwind wiring will remain unchanged.

## Scope

### Included

- One responsive concept-review page with a clearly visible three-option concept switcher.
- Three dashboard-only visual treatments using the same information and mock data so the comparison is about design rather than content.
- A realistic generalized dashboard composition that demonstrates hierarchy, typography, navigation, controls, score visualization, table density, provenance, and caveat treatment.
- Responsive behavior sufficient to review each direction on desktop and narrow/mobile widths.
- Accessible structure, controls, color contrast, focus states, and non-color score labels.

### Deliberately Deferred

- The complete production implementation of Dashboard, Advanced Search, and Individualized Report.
- Flask connectivity, fetch logic, loading/error/empty states, and the finalized `/api/v1` contract.
- Real ClinicalTrials.gov v2 or openFDA data.
- Final scoring methodology and score calculations.
- Functional dashboard filtering, sorting, pagination, advanced search, or report generation.
- Production routing and persistent URL state.

Only the concept switcher needs to be interactive in this phase. Dashboard controls may show representative states but will not imply that mock filtering is real.

## Shared Content for an Apples-to-Apples Comparison

All three directions will use the same representative content and ordering:

- Product name: **Clinical Trial Representation**.
- Primary navigation labels: Dashboard, Advanced Search, Individualized Report.
- Dashboard heading and concise explanation of what representation means.
- A visible “Research prototype” status and “Not medical advice” caveat.
- Summary metrics such as drugs reviewed, trials analyzed, and last data refresh.
- A drug search field and representative sort/filter controls.
- A generalized results table/list with these columns, in this order:
  1. **Name** — generic drug name only; brand names are not displayed.
  2. **Use** — most common indication first, with an explicit “+N more” treatment where applicable.
  3. **Least researched** — derived age, sex, and/or race coverage gaps; no user demographic input is required on this generalized dashboard.
  4. **Score** — provisional 0–100 coverage percentage, circular or equivalent coverage graphic, qualitative tier, and compact age/sex/race component indicators.
- Representative generic drugs and plausible placeholder values, clearly marked as sample data rather than factual findings.
- A source/provenance area referencing ClinicalTrials.gov API v2 and openFDA drug labeling, along with trial count, refresh date, methodology access, and the limitation that the score is provisional.

The mock dataset will be centralized and shared by every concept to prevent content drift between variants.

## Visual Directions

### 1. Clinical Research Editorial

- Warm off-white canvas with ink/navy text and restrained teal accents.
- Editorial typography pairing and generous whitespace.
- Strong explanatory copy, fine rules, restrained cards, and publication-like evidence treatment.
- Table remains data-dense but emphasizes reading flow and provenance.
- Score visual feels analytical rather than gamified; muted semantic bands are paired with labels.
- Overall impression: independent research institute or peer-reviewed evidence product.

### 2. Traditional Clinical Dashboard

- Cool neutral page background, white surfaces, navy/medical-blue accents, and compact spacing.
- Familiar top application bar, bordered cards, segmented controls, and dense table treatment.
- Summary metrics and filtering controls are prominent and operational.
- Score uses a conventional ring/progress treatment and concise status chips.
- Overall impression: trusted hospital analytics or enterprise clinical operations software.

### 3. Consumer Health

- Brighter but still credible palette, larger type, rounded surfaces, and more explanatory labels.
- Simplified scanning with a ranked card/list presentation at narrow widths.
- Friendly visual emphasis on “what this means,” while avoiding claims, alarmism, or gamified medical guidance.
- Score and component breakdown are more visual, but always accompanied by percentages and text labels.
- Overall impression: accessible public-health education product rather than a clinician-only tool.

No photography is needed for this data-product comparison. UI symbols will use simple CSS/SVG treatments rather than emoji.

## Component and File Approach

Keep the prototype small while separating shared content from concept styling:

- Update `src/App.tsx` to render the concept-review shell and hold the selected concept state.
- Add a small shared mock-data/types module for dashboard rows and summary metrics.
- Add shared semantic dashboard building blocks only where they genuinely prevent duplication, such as the concept switcher, score visualization, provenance content, and accessible table labels.
- Add one presentation component per visual direction so each can vary layout as well as color and typography; do not reduce the concepts to theme-token swaps.
- Extend `src/index.css` with scoped global design tokens, typography/background defaults, and any small visual primitives that Tailwind utilities cannot express cleanly. Avoid a universal reset.
- Preserve `src/main.tsx`, `index.html`, Vite configuration, and existing Tailwind setup.
- Do not add React Router or other runtime dependencies for the concept phase.

## Interaction and Responsive Behavior

- Provide a keyboard-accessible segmented concept switcher near the top of the page.
- Each option will include a short descriptor so reviewers understand the intended audience/tone.
- Switching concepts will preserve the same viewport and content, allowing direct comparison.
- Desktop should demonstrate the full table and dashboard hierarchy.
- At narrower widths, summary metrics stack, controls wrap, and each concept uses an intentional mobile treatment; the data table may become horizontally scrollable or convert to labeled rows/cards according to the visual direction.
- The concept selector remains reachable and usable on mobile.
- Representative nonfunctional controls will be visually distinguishable from the working concept selector or labeled as preview controls where ambiguity would otherwise arise.

## Accessibility and Content Safety

- Use semantic headings, navigation, tables/lists, labels, and buttons.
- Maintain visible keyboard focus and adequate contrast in every direction.
- Never encode score meaning by color alone; show percentage and tier text.
- Mark every score and drug finding as sample/provisional data.
- Include research-purpose and not-medical-advice language without allowing the disclaimer to dominate the page.
- Avoid collecting or displaying personal health information in this concept phase.

## Validation

Use the running Vite preview as the primary validation signal:

1. Open the preview and confirm the concept-review shell appears without replacing the application entrypoint.
2. Switch among all three concepts by pointer and keyboard; verify shared values remain identical.
3. Review each direction at desktop and narrow/mobile widths for overflow, readable hierarchy, and intentional responsive behavior.
4. Check that score graphics have textual equivalents and that focus states and contrast remain visible.
5. Confirm all displayed drug findings, counts, percentages, and dates are visibly identified as sample/provisional.
6. Because this is a localized visual prototype, do not run build/typecheck by default unless the preview exposes a concrete runtime or compilation failure.

## Decisions Captured for the Subsequent Full-Product Phase

These decisions should carry forward after a visual direction is selected:

- Public tool with no account or saved profiles.
- Full product pages: generalized dashboard, advanced search, and individualized report.
- Generic drug names only, with brands grouped under their generic ingredient in backend normalization.
- Dashboard least-researched values are derived gaps, not mandatory inputs.
- Advanced Search uses a curated clinical filter set rather than mirroring every upstream query parameter.
- Demographic input uses exact age mapped to backend bands, Female/Male/All or Not specified sex values, and US OMB-style race categories including multiracial.
- Individualized reports can be started from a standalone form or deep-linked from a drug row.
- Reports include overall and component scores, subgroup gaps, evidence/trial breakdown, FDA labeling context, source links, update dates, methodology, and medical-use caveats.
- Scores remain explicitly provisional until a methodology is supplied.
- The future frontend uses versioned same-origin `/api/v1/...` endpoints with `VITE_API_BASE_URL` as an override.
- Before Flask is available, the future data layer will use realistic local mock fallback data while preserving the API response shapes.

## Completion Criteria

The concept phase is complete when the user can inspect the same representative generalized dashboard in three clearly differentiated, polished, responsive visual directions and confidently choose one direction for the complete site. Selection and full-product implementation will be planned after that review rather than prematurely blending the three approaches.
