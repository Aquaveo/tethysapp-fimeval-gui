# FIMEVAL-FE1 — App Shell + Three-Step Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the scaffold placeholder `App.tsx` with a three-step wizard shell (horizontal stepper on top) that walks Upload → Running → Results.

**Architecture:** A single `step` state in `App.tsx` is the only source of truth. It drives both which step component renders and how `Stepper` colors each of the three circles (complete = green ✓, active = blue, pending = gray). Placeholder step components carry temporary dev nav buttons to advance/rewind the wizard until real transitions arrive in FE3/FE4. A shared `types.ts` holds the `Step` type and the step order/labels so `App` and `Stepper` stay DRY.

**Tech Stack:** React 19, TypeScript (strict, `verbatimModuleSyntax`), Vite, plain CSS (no UI library).

---

## Project-Specific Constraints (read before starting)

- **`verbatimModuleSyntax: true`** — importing a type requires the `type` modifier. Use inline form: `import { STEP_ORDER, type Step } from './types';`. A plain `import { Step }` will fail the build.
- **`react-refresh/only-export-components`** (ESLint) — a file that exports a component must export *only* components. That's why `Step`/`STEP_ORDER`/`STEP_LABELS` live in `types.ts`, not in `App.tsx`.
- **React 19 + `react-jsx`** — do not `import React`. Import only the hooks/utilities you use (e.g. `useState`, `Fragment`).
- **`strict`, `noUnusedLocals`, `noUnusedParameters`** — no unused variables or parameters anywhere.
- **No component test framework** — vitest is installed but there is no `@testing-library/react`/jsdom setup. Do **not** add one for this task (YAGNI — the shell has no logic worth a unit test beyond the type checker). Verification is `npx tsc -b` + `npm run lint` + a manual browser walkthrough.

## File Structure

All paths under `reactapp/src/`.

- **Create `types.ts`** — `Step` union type, `STEP_ORDER` array, `STEP_LABELS` record. Shared by `App` and `Stepper`.
- **Create `Stepper.tsx`** — pure presentational stepper. Props: `{ current: Step }`. Renders 3 circles + connector lines + labels.
- **Create `UploadStep.tsx`** — placeholder. Props: `{ onNext: () => void }`.
- **Create `RunningStep.tsx`** — placeholder. Props: `{ onNext: () => void; onBack: () => void }`.
- **Create `ResultsStep.tsx`** — placeholder. Props: `{ onBack: () => void }`.
- **Modify `App.tsx`** — owns `step` state, computes next/back, renders heading + `Stepper` + active step.
- **Modify `App.css`** — styles for header, stepper (three states + lines), placeholder boxes, dev nav buttons.

## Git / Commit Convention (project-specific)

Per this project's working style, **commits require explicit user go-ahead and the user tests manually first.** Therefore this plan does **not** commit per sub-task. Implement all tasks, run the type-check and lint gates, then hand off for a manual browser walkthrough. A single commit happens at the end **only after the user approves** (Task 6).

---

### Task 1: Shared types

**Files:**
- Create: `reactapp/src/types.ts`

- [ ] **Step 1: Create the shared types module**

```ts
// reactapp/src/types.ts

// Which step of the wizard is currently active.
export type Step = 'upload' | 'running' | 'results';

// Wizard order. Index in this array determines complete/active/pending state.
export const STEP_ORDER: Step[] = ['upload', 'running', 'results'];

// Display labels shown beneath each stepper circle.
export const STEP_LABELS: Record<Step, string> = {
  upload: 'Upload',
  running: 'Running',
  results: 'Results',
};
```

- [ ] **Step 2: Type-check**

Run: `cd reactapp && npx tsc -b`
Expected: PASS (no output, exit 0). `types.ts` is valid even though nothing imports it yet.

---

### Task 2: Stepper component

**Files:**
- Create: `reactapp/src/Stepper.tsx`

- [ ] **Step 1: Create the Stepper component**

```tsx
// reactapp/src/Stepper.tsx
import { Fragment } from 'react';
import { STEP_ORDER, STEP_LABELS, type Step } from './types';

interface StepperProps {
  current: Step;
}

function Stepper({ current }: StepperProps) {
  const currentIndex = STEP_ORDER.indexOf(current);

  return (
    <div className="stepper">
      {STEP_ORDER.map((stepId, i) => {
        const state =
          i < currentIndex ? 'complete' : i === currentIndex ? 'active' : 'pending';
        return (
          <Fragment key={stepId}>
            {i > 0 && (
              <div className={`stepper-line ${i <= currentIndex ? 'filled' : ''}`} />
            )}
            <div className="stepper-step">
              <div className={`stepper-circle ${state}`}>
                {state === 'complete' ? '✓' : i + 1}
              </div>
              <span className={`stepper-label ${state}`}>{STEP_LABELS[stepId]}</span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

export default Stepper;
```

Notes:
- `✓` is the ✓ checkmark; written as an escape to keep the source ASCII-safe.
- The connector line renders *before* each step except the first, and is `filled` (green) when that line sits at or before the current step.

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: PASS. (Stepper is unimported so far — that is fine; `noUnusedLocals` is per-file, not cross-module.)

---

### Task 3: Placeholder step components

**Files:**
- Create: `reactapp/src/UploadStep.tsx`
- Create: `reactapp/src/RunningStep.tsx`
- Create: `reactapp/src/ResultsStep.tsx`

- [ ] **Step 1: Create UploadStep**

```tsx
// reactapp/src/UploadStep.tsx
interface UploadStepProps {
  onNext: () => void;
}

function UploadStep({ onNext }: UploadStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Upload Files</h2>
      <p>File pickers and method selector will go here (FIMEVAL-FE2).</p>
      {/* TODO(FE3): replace temporary dev nav with real upload+submit transition */}
      <div className="dev-nav">
        <button className="btn btn-next" onClick={onNext}>Next &rarr;</button>
      </div>
    </div>
  );
}

export default UploadStep;
```

- [ ] **Step 2: Create RunningStep**

```tsx
// reactapp/src/RunningStep.tsx
interface RunningStepProps {
  onNext: () => void;
  onBack: () => void;
}

function RunningStep({ onNext, onBack }: RunningStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Running</h2>
      <p>Job progress and status polling will go here (FIMEVAL-FE4).</p>
      {/* TODO(FE4): replace temporary dev nav with real status-poll transition */}
      <div className="dev-nav">
        <button className="btn btn-back" onClick={onBack}>&larr; Back</button>
        <button className="btn btn-next" onClick={onNext}>Next &rarr;</button>
      </div>
    </div>
  );
}

export default RunningStep;
```

- [ ] **Step 3: Create ResultsStep**

```tsx
// reactapp/src/ResultsStep.tsx
interface ResultsStepProps {
  onBack: () => void;
}

function ResultsStep({ onBack }: ResultsStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Results</h2>
      <p>Metrics table and download links will go here (FIMEVAL-FE5).</p>
      {/* TODO(FE5): replace temporary dev nav with real "Start New Evaluation" reset */}
      <div className="dev-nav">
        <button className="btn btn-back" onClick={onBack}>&larr; Back</button>
      </div>
    </div>
  );
}

export default ResultsStep;
```

- [ ] **Step 4: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: PASS.

---

### Task 4: Wire up App.tsx

**Files:**
- Modify: `reactapp/src/App.tsx` (full replace)

- [ ] **Step 1: Replace App.tsx with the wired shell**

```tsx
// reactapp/src/App.tsx
import { useState } from 'react';
import { STEP_ORDER, type Step } from './types';
import Stepper from './Stepper';
import UploadStep from './UploadStep';
import RunningStep from './RunningStep';
import ResultsStep from './ResultsStep';
import './App.css';

function App() {
  const [step, setStep] = useState<Step>('upload');

  const index = STEP_ORDER.indexOf(step);
  const goNext = () => {
    if (index < STEP_ORDER.length - 1) setStep(STEP_ORDER[index + 1]);
  };
  const goBack = () => {
    if (index > 0) setStep(STEP_ORDER[index - 1]);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>FIMeval</h1>
        <p className="app-subtitle">Flood Inundation Map Evaluation</p>
      </header>

      <Stepper current={step} />

      <main className="step-container">
        {step === 'upload' && <UploadStep onNext={goNext} />}
        {step === 'running' && <RunningStep onNext={goNext} onBack={goBack} />}
        {step === 'results' && <ResultsStep onBack={goBack} />}
      </main>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: PASS. All five new modules are now imported; no unused-import or unused-var errors.

---

### Task 5: Styles

**Files:**
- Modify: `reactapp/src/App.css` (full replace)

- [ ] **Step 1: Replace App.css**

```css
/* reactapp/src/App.css */

.app {
  padding: 2rem;
  max-width: 800px;
  margin: 0 auto;
}

/* ---- Header ---- */
.app-header {
  text-align: center;
  margin-bottom: 1.75rem;
}
.app-header h1 {
  margin: 0;
  font-size: 1.9rem;
  color: #212529;
}
.app-subtitle {
  margin: 0.25rem 0 0;
  color: #868e96;
  font-size: 0.95rem;
}

/* ---- Stepper ---- */
.stepper {
  display: flex;
  align-items: flex-start;
  margin-bottom: 2rem;
}
.stepper-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  flex: 0 0 auto;
}
.stepper-circle {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.9rem;
}
.stepper-circle.complete {
  background: #28a745;
  color: #fff;
}
.stepper-circle.active {
  background: #007bff;
  color: #fff;
}
.stepper-circle.pending {
  background: #dee2e6;
  color: #868e96;
}
.stepper-label {
  font-size: 0.78rem;
}
.stepper-label.complete {
  color: #28a745;
  font-weight: 600;
}
.stepper-label.active {
  color: #007bff;
  font-weight: 600;
}
.stepper-label.pending {
  color: #868e96;
}
.stepper-line {
  flex: 1 1 auto;
  height: 2px;
  background: #dee2e6;
  margin: 16px 8px 0;   /* 16px top-margin centers the line on the 34px circle */
}
.stepper-line.filled {
  background: #28a745;
}

/* ---- Step content ---- */
.step-container {
  margin-top: 1rem;
}
.step-placeholder {
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 2rem;
  background: #fff;
  text-align: center;
}
.step-placeholder h2 {
  margin-top: 0;
  color: #212529;
}
.step-placeholder p {
  color: #868e96;
}

/* ---- Temporary dev nav (removed in FE3/FE4/FE5) ---- */
.dev-nav {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 1.5rem;
}
.btn {
  padding: 0.5rem 1.1rem;
  border-radius: 5px;
  border: 1px solid transparent;
  font-size: 0.9rem;
  cursor: pointer;
}
.btn-next {
  background: #007bff;
  color: #fff;
}
.btn-back {
  background: #fff;
  color: #495057;
  border-color: #ced4da;
}
```

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: PASS (CSS is not type-checked/linted by these, but confirms nothing regressed).

---

### Task 6: Verify and commit (await user go-ahead)

**Files:** none (verification + git)

- [ ] **Step 1: Final type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS, exit 0.

- [ ] **Step 2: Manual browser walkthrough**

Run: `cd reactapp && npm run dev`
Open http://localhost:5173 and confirm:
- Heading "FIMeval" + subtitle "Flood Inundation Map Evaluation" centered at top.
- Stepper shows circle 1 (Upload) blue/active, 2 and 3 gray/pending, connector lines gray.
- "Upload Files" placeholder box with a single "Next →" button.
- Click "Next →": step 2 (Running) goes active/blue, step 1 becomes green with ✓, the line between 1 and 2 turns green. "Running" box shows "← Back" and "Next →".
- Click "Next →" again: step 3 (Results) active, steps 1 and 2 green with ✓, both lines green. "Results" box shows only "← Back".
- "← Back" walks back through the steps and the stepper states reverse correctly.

Report the result to the user and **wait for their go-ahead before committing.**

- [ ] **Step 3: Commit (only after user approval)**

```bash
git add .
git commit -m "feat: FIMEVAL-FE1 three-step wizard app shell

Replace scaffold placeholder with App shell: step state, horizontal
Stepper (complete/active/pending), and placeholder Upload/Running/Results
steps with temporary dev nav buttons.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Push (only after user approval)**

```bash
git push
```

---

## Self-Review

**Spec coverage** (against `2026-06-08-fimeval-fe1-app-shell-design.md`):
- Layout A horizontal stepper on top → Task 2 + Task 5 ✓
- Heading "FIMeval" + subtitle → Task 4 + Task 5 ✓
- `App.tsx` owns `step` state `'upload'|'running'|'results'` → Task 4 ✓
- `Stepper.tsx` 3 states (complete green ✓ / active blue `#007bff` / pending gray) → Task 2 + Task 5 ✓
- Step labels Upload/Running/Results → Task 1 (`STEP_LABELS`) ✓
- Steps not clickable (pure indicator) → Stepper renders no click handlers ✓
- Placeholder Upload/Running/Results components → Task 3 ✓
- Temporary dev nav buttons, removed later → Task 3 (with TODO markers) ✓
- `App.css` plain CSS, no UI library → Task 5 ✓
- State flow: `step` drives both render + stepper coloring; dev buttons call setter → Task 4 ✓
- Verify `npx tsc -b` + lint + manual → Tasks 2–6 ✓

**Placeholder scan:** No "TBD/TODO/handle edge cases" plan-placeholders. The `TODO(FE3/FE4/FE5)` strings are intentional code comments marking throwaway dev nav, not plan gaps.

**Type consistency:** `Step`, `STEP_ORDER`, `STEP_LABELS` defined in Task 1 and consumed with matching names/signatures in Tasks 2 & 4. Prop interfaces (`onNext`/`onBack`) defined in Task 3 match the handlers passed in Task 4 (`goNext`/`goBack`). Inline `type` imports used throughout per `verbatimModuleSyntax`.
