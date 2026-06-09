# FIMEVAL-FE4 — Running Step + Status Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Running step poll the job status endpoint, show a spinner while the job runs, auto-advance to Results on completion, and show an error + "Start Over" on failure — with polling cleaned up on unmount.

**Architecture:** `api.ts` gains `getJobStatus`. `RunningStep` runs a recursive `setTimeout` poll loop inside one `useEffect` (cancelled-flag + `clearTimeout` cleanup), calling `onComplete`/`setErrored` on terminal statuses and tolerating transient request failures. `App` passes `useCallback`-stable `onComplete`/`onReset` so the effect doesn't restart on re-render.

**Tech Stack:** React 19, TypeScript (strict, `verbatimModuleSyntax`), Vite, plain CSS.

---

## Project-Specific Constraints (read before starting)

- **React 19 + `react-jsx`** — no `import React`. Import hooks explicitly.
- **`verbatimModuleSyntax: true`** — type-only imports need the `type` modifier. `api.ts` may export types (not a component file). Component files export ONLY their default component.
- **`react-hooks/exhaustive-deps` is enabled** — the poll effect lists `[jobId, onComplete]`; that's why `App` makes `onComplete`/`onReset` `useCallback`-stable. Do not silence the lint rule.
- **`strict`, `noUnusedLocals`, `noUnusedParameters`** — no unused vars/params. `goNext` becomes unused this task and MUST be removed.
- **No component test framework** — verify with `npx tsc -b` + `npm run lint` + `npm run build` + manual.
- **Coupling:** `App.tsx` and `RunningStep.tsx` change the prop contract in lockstep (`onNext`/`onBack` → `onComplete`/`onReset` + `jobId`). They must land together — `tsc` will not pass with only one changed. They're one task here.

## File Structure

- **Modify `reactapp/src/api.ts`** — add `JobStatus` interface + `getJobStatus`.
- **Modify `reactapp/src/RunningStep.tsx`** — full rewrite: polling loop, spinner/error render.
- **Create `reactapp/src/RunningStep.css`** — spinner, progress, error layout.
- **Modify `reactapp/src/App.tsx`** — `useCallback` transitions, new RunningStep render, remove `goNext`.

## Git / Commit Convention (project-specific)

**Commits require explicit user go-ahead; the user tests manually first.** No per-task commits. Implement all tasks, run the gates, then hand off for manual verification. One commit at the end after the user approves (Task 4).

---

### Task 1: api.ts — `getJobStatus`

**Files:**
- Modify: `reactapp/src/api.ts`

- [ ] **Step 1: Add the `JobStatus` interface and `getJobStatus` function**

Append to `reactapp/src/api.ts` (after the existing `submitJob` function):

```ts
export interface JobStatus {
  job_id: number;
  status: 'submitted' | 'running' | 'complete' | 'error';
  created: string | null;
  completed: string | null;
  method: string | null;
  upload_id: string | null;
}

export async function getJobStatus(jobId: number): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}
```

Notes:
- GET is a safe method — no `X-CSRFToken` needed. `credentials: 'same-origin'` sends the session cookie.
- `API_BASE` and `parseError` already exist at the top of `api.ts`; reuse them (do not redefine).

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS (`getJobStatus` is valid even though nothing imports it yet).

---

### Task 2: RunningStep — polling + render, App wiring (coupled)

`RunningStep.tsx` and `App.tsx` change the prop contract together; implement both before running the gate.

**Files:**
- Modify: `reactapp/src/RunningStep.tsx` (full replace)
- Modify: `reactapp/src/App.tsx` (full replace)

- [ ] **Step 1: Replace RunningStep.tsx**

```tsx
// reactapp/src/RunningStep.tsx
import { useEffect, useState } from 'react';
import { getJobStatus } from './api';
import './RunningStep.css';

interface RunningStepProps {
  jobId: number;
  onComplete: () => void;
  onReset: () => void;
}

function RunningStep({ jobId, onComplete, onReset }: RunningStepProps) {
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const status = await getJobStatus(jobId);
        if (cancelled) return;
        if (status.status === 'complete') {
          onComplete();
          return;
        }
        if (status.status === 'error') {
          setErrored(true);
          return;
        }
        // submitted / running — keep polling
        timeout = setTimeout(poll, 3000);
      } catch {
        // transient request failure — tolerate and keep polling
        if (cancelled) return;
        timeout = setTimeout(poll, 3000);
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (timeout !== undefined) clearTimeout(timeout);
    };
  }, [jobId, onComplete]);

  if (errored) {
    return (
      <div className="step-placeholder running-step">
        <h2>Running</h2>
        <p className="running-error">The evaluation failed.</p>
        <div className="running-actions">
          <button type="button" className="button-primary" onClick={onReset}>
            Start Over
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-placeholder running-step">
      <h2>Running</h2>
      <div className="running-spinner" aria-hidden="true" />
      <p className="running-message">Evaluation in progress&hellip;</p>
      <p className="running-jobid">(Job #{jobId})</p>
    </div>
  );
}

export default RunningStep;
```

Notes:
- `ReturnType<typeof setTimeout>` is the portable type for a timeout handle (number in the browser, but this avoids the Node `Timeout` type mismatch under `@types/node`).
- The effect deps are `[jobId, onComplete]`; `onComplete` is `useCallback`-stable from `App` (Step 2), so the loop starts once per job and is not restarted by re-renders.
- `onReset` is intentionally NOT in the deps — it is only called from the rendered button (an event handler), not inside the effect, so it does not need to be a dependency and does not trigger `exhaustive-deps`.

- [ ] **Step 2: Replace App.tsx**

```tsx
// reactapp/src/App.tsx
import { useCallback, useEffect, useState } from 'react';
import { STEP_ORDER, type Step } from './types';
import { ensureCsrf } from './api';
import Stepper from './Stepper';
import UploadStep from './UploadStep';
import RunningStep from './RunningStep';
import ResultsStep from './ResultsStep';
import './App.css';

function App() {
  const [step, setStep] = useState<Step>('upload');
  const [jobId, setJobId] = useState<number | null>(null);

  useEffect(() => {
    ensureCsrf();
  }, []);

  const index = STEP_ORDER.indexOf(step);
  const goBack = () => {
    if (index > 0) setStep(STEP_ORDER[index - 1]);
  };

  const onJobCreated = (id: number) => {
    setJobId(id);
    setStep('running');
  };

  const onComplete = useCallback(() => setStep('results'), []);
  const onReset = useCallback(() => {
    setStep('upload');
    setJobId(null);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1>FIMeval</h1>
        <p className="app-subtitle">Flood Inundation Map Evaluation</p>
      </header>

      <Stepper current={step} />

      <main className="step-container">
        {step === 'upload' && <UploadStep onJobCreated={onJobCreated} />}
        {step === 'running' && jobId !== null && (
          <RunningStep jobId={jobId} onComplete={onComplete} onReset={onReset} />
        )}
        {step === 'results' && <ResultsStep onBack={goBack} />}
      </main>
    </div>
  );
}

export default App;
```

Notes:
- `goNext` is removed (no longer used; would fail `noUnusedLocals`). `goBack`, `index`, and the `STEP_ORDER` import remain — `ResultsStep` still uses `goBack` until FE5.
- `setStep` / `setJobId` are stable across renders, so the `useCallback`s correctly use `[]` deps.
- The `jobId !== null` guard narrows `jobId` from `number | null` to `number` for the `RunningStep` prop.

- [ ] **Step 3: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS. (`RunningStep.css` does not exist yet — Task 3 adds it; CSS imports aren't type-checked, so this still passes. No unused-var errors: `goNext` is gone, `useCallback` is used.)

---

### Task 3: RunningStep.css

**Files:**
- Create: `reactapp/src/RunningStep.css`

- [ ] **Step 1: Create RunningStep.css**

```css
/* reactapp/src/RunningStep.css */

.running-step {
  text-align: center;
}

.running-spinner {
  width: 2.5rem;
  height: 2.5rem;
  margin: 1.5rem auto 0;
  border: 3px solid var(--color-surface-alt);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: running-spin 0.8s linear infinite;
}
@keyframes running-spin {
  to {
    transform: rotate(360deg);
  }
}

.running-message {
  margin: 1rem 0 0;
  font-size: 1rem;
  color: var(--color-text);
}
.running-jobid {
  margin: 0.25rem 0 0;
  font-size: 0.82rem;
  color: var(--color-text-muted);
}

.running-error {
  color: var(--color-error);
  font-weight: 500;
  margin: 1rem 0 1.5rem;
}
.running-actions {
  display: flex;
  justify-content: center;
}
```

Notes:
- `.running-message` uses `var(--color-text)` directly (not a bare `p`) so it is unaffected by the broader `.step-placeholder p` rule in `App.css`.

- [ ] **Step 2: Type-check, lint, build**

Run: `cd reactapp && npx tsc -b && npm run lint && npm run build`
Expected: all PASS (build confirms the new CSS import bundles cleanly).

---

### Task 4: Verify and commit (await user go-ahead)

**Files:** none (verification + git)

- [ ] **Step 1: Final gates**

Run: `cd reactapp && npx tsc -b && npm run lint && npm run build`
Expected: all PASS, exit 0.

- [ ] **Step 2: Manual browser walkthrough**

Prereq: Tethys (`:8000`), Dask scheduler + worker, MinIO all running; user logged into Tethys.
Run: `cd reactapp && npm run dev` → open http://localhost:5173

- Upload a benchmark + candidate(s), pick a method, click "Upload & Run".
- The wizard advances to Running: a centered cyan spinner + "Evaluation in progress…" + "(Job #N)". No dev nav buttons.
- In DevTools → Network, confirm `jobs/<id>/` requests fire ~every 3s with a gap between responses (not stacked).
- When the fimeval outputs land in MinIO, the next poll returns `complete` and the wizard auto-advances to the Results step.
- Reload the page mid-run (or trigger Start Over once an error occurs) and confirm in the Network tab that polling stops (no further `jobs/<id>/` requests) — verifies cleanup.
- (Best effort) If a job genuinely errors, the Running step shows "The evaluation failed." + a "Start Over" button that returns to a fresh Upload step.

Report results to the user and **wait for go-ahead before committing.**

- [ ] **Step 3: Commit (only after user approval)**

```bash
git add .
git commit -m "feat: FIMEVAL-FE4 running step status polling

RunningStep now polls GET /api/jobs/{id}/ on a recursive 3s setTimeout loop:
auto-advances to Results on 'complete', shows an error + Start Over on
'error', tolerates transient request failures, and cleans up the loop on
unmount. Add api.getJobStatus + JobStatus type. App passes useCallback-stable
onComplete/onReset and drops the now-unused goNext.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Push (only after user approval)**

```bash
git push
```

---

## Self-Review

**Spec coverage** (against `2026-06-08-fimeval-fe4-running-step-polling-design.md`):
- `api.ts`: `JobStatus` interface + `getJobStatus` (GET, `credentials: same-origin`, non-OK → `parseError`) → Task 1 ✓
- `RunningStep` props `{jobId, onComplete, onReset}`, drops onNext/onBack → Task 2 ✓
- `errored` state → Task 2 ✓
- Recursive `setTimeout` poll loop, deps `[jobId, onComplete]`, cancelled flag + clearTimeout cleanup, immediate first poll → Task 2 ✓
- `complete` → onComplete + stop; `error` → setErrored + stop; else reschedule; throw → tolerate + reschedule (unless cancelled) → Task 2 ✓
- Render: spinner + "Evaluation in progress…" + "(Job #N)"; errored → red "The evaluation failed." + Start Over (`.button-primary`, onReset) → Task 2 ✓
- `RunningStep.css`: centered ~2.5rem cyan spinner, progress/error text, layout → Task 3 ✓
- `App.tsx`: `useCallback` onComplete/onReset, null-guarded RunningStep render, remove goNext, keep goBack → Task 2 ✓
- Verify tsc + lint + build + manual; no test framework → Tasks 1–4 ✓

**Placeholder scan:** No plan-placeholders. All code blocks complete.

**Type consistency:** `getJobStatus(jobId: number): Promise<JobStatus>` (Task 1) matches the call `await getJobStatus(jobId)` in RunningStep (Task 2). `JobStatus.status` union values (`complete`/`error`/`submitted`/`running`) match the branch checks. `RunningStep` props (`jobId: number`, `onComplete`, `onReset`) match App's render site (Task 2), with `jobId !== null` narrowing. `onComplete`/`onReset` `useCallback` identities are stable, matching the effect's deps assumption. CSS classes used in Task 2 (`running-step`, `running-spinner`, `running-message`, `running-jobid`, `running-error`, `running-actions`, `button-primary`) all have rules in Task 3 / the shared theme.

**`react-hooks/exhaustive-deps` note:** the effect references `jobId` and `onComplete` (both in deps) and `getJobStatus` (a module import, not reactive). `onReset` is used only in the error-branch button handler, not in the effect, so it's correctly absent from the deps. No lint suppression needed.
