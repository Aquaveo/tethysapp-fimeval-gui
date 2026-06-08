# FIMEVAL-FE1 — App Shell + Three-Step Layout

**Date:** 2026-06-08
**Status:** Approved, ready for implementation plan

## Goal

Replace the scaffold placeholder in the FIMeval GUI React SPA with a three-step
wizard shell. This task delivers the **structure and navigation only** — no
upload, job, or download logic. Those land in FE2–FE5.

The app renders inside the Tethys Platform 4 portal content area, which already
provides its own top navigation showing the app name.

## Layout

**Option A — horizontal stepper on top** (selected during brainstorming):
numbered circles connected by a line across the top, with the active step's
content rendered below. Compact vertically, familiar wizard pattern.

A heading block sits above the stepper:
- Title: **FIMeval**
- Subtitle: **Flood Inundation Map Evaluation**

## Components

All under `reactapp/src/`.

### `App.tsx`
- Owns the single source of truth: `step` state, typed as
  `'upload' | 'running' | 'results'`.
- Renders, top to bottom: heading block → `<Stepper>` → the active step component.
- Selects which step component to render based on `step`.
- Passes a setter down to the placeholder steps so the temporary dev nav buttons
  can advance/rewind the wizard (see Navigation below).

### `Stepper.tsx`
- Props: the current `step`.
- Renders three horizontal numbered circles connected by lines.
- Each circle is in one of three visual states, derived from the current step's
  position relative to that circle:
  - **Complete** — green circle with a ✓ (steps before the current one)
  - **Active** — blue `#007bff` circle with the step number (the current step)
  - **Pending** — gray circle with the step number (steps after the current one)
- Each step has a label beneath it: "Upload", "Running", "Results".
- Steps are **not clickable** — the stepper is a pure progress indicator.

### `UploadStep.tsx`, `RunningStep.tsx`, `ResultsStep.tsx`
- Placeholder components for this task. Each renders a titled box describing what
  it will become.
- Each contains **temporary dev navigation buttons** ("← Back" / "Next →") to
  advance the `step` state. These exist only so FE1 is self-contained and
  demoable; they will be removed when real transitions are wired in (FE3/FE4).
- Real content replaces these placeholders in later tasks.

### `App.css`
- Styles the heading, stepper (circles, connector lines, three-state colors,
  labels), and the placeholder step boxes.
- Matches the Tethys portal accent color `#007bff`. Green for the complete state,
  gray (`#dee2e6` / `#868e96`) for pending.
- Plain CSS — no external UI library.

## State Flow

```
App.tsx  ──(step)──>  Stepper.tsx          (colors each circle)
   │
   └─────(step)──>  active step component  (which one renders)
                          │
                          └──(setStep via dev buttons)──> back to App.tsx
```

`step` is the only state. It determines both which step component renders and how
the stepper colors each circle. There is no independent "completed" tracking —
completeness is purely positional (any step index less than the current step's
index is complete).

## Navigation

Temporary dev nav buttons in each placeholder step call the `setStep` setter:
- Upload → Running → Results (Next)
- Results → Running → Upload (Back)

These are throwaway scaffolding for FE1 only. Real state transitions (upload
success → running, job complete → results) arrive in FE3 and FE4, at which point
the dev buttons are removed.

## Out of Scope

- Any API calls (upload, submit, status, outputs, download) — FE3+
- File pickers, method selector, validation — FE2
- Status polling — FE4
- Results table and download links — FE5
- Production build / Tethys serving verification — FE6
- Clickable step navigation (steps stay non-interactive by design)

## Testing

- `npx tsc -b` type-checks cleanly.
- `npm run lint` passes.
- Manual: the three dev nav buttons walk forward and backward through all three
  steps, and the stepper reflects complete/active/pending states correctly at
  each position.
