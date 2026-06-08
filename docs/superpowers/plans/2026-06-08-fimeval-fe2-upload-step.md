# FIMEVAL-FE2 — Upload Step UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the FE1 Upload placeholder with a real upload form — two drag-and-drop pickers (benchmark + candidates), a method selector, and validation that gates the "Upload & Run" button. UI and form state only; no network requests.

**Architecture:** A reusable `Dropzone` component handles all drag/drop/browse/extension-filtering and owns its own rejection message, emitting accepted files upward via `onAccepted`. `UploadStep` owns the form state (benchmark, candidates, method), composes two `Dropzone`s, renders the selected-file displays + method `<select>` + the gated button, and calls the existing `onNext` prop to advance when valid. Co-located CSS files keep styles out of `App.css`.

**Tech Stack:** React 19, TypeScript (strict, `verbatimModuleSyntax`), Vite, plain CSS (no UI library).

---

## Project-Specific Constraints (read before starting)

- **`verbatimModuleSyntax: true`** — type imports need the `type` modifier (inline form: `import { useState, type ChangeEvent } from 'react'`). A plain type import fails the build.
- **`react-refresh/only-export-components`** (ESLint) — a file exporting a component exports ONLY components. Both `Dropzone.tsx` and `UploadStep.tsx` export a single default component. Do not export helper functions or types from them.
- **React 19 + `react-jsx`** — do not `import React`. Import only the hooks/types you use.
- **`strict`, `noUnusedLocals`, `noUnusedParameters`** — no unused variables or parameters.
- **No component test framework** — vitest is installed but there is no `@testing-library/react`/jsdom. Do NOT add one. Verification is `npx tsc -b` + `npm run lint` + a manual browser walkthrough.
- **Brand theme already exists** — use CSS variables from `src/styles/theme.css` (`--color-primary` `#25C2DF`, `--color-surface-alt` `#E1F4F9`, `--color-border` `#D1EFF6`, `--color-text` `#152428`, `--color-text-secondary` `#267788`, `--color-text-muted` `#28899D`, `--radius-md`, `--radius-lg`, `--color-error` `#CC0000`). The `.button-primary` class is defined there; do NOT edit `theme.css`.
- **FE1 already added** a global `button { font-family: inherit; }` in `index.css`.

## File Structure

All paths under `reactapp/src/`.

- **Create `Dropzone.tsx`** — reusable drag-and-drop file input. Props `{ label, multiple, accept, onAccepted }`. Owns drag-highlight state + its own `.tif` rejection message. Emits accepted files.
- **Create `Dropzone.css`** — dashed zone (idle/dragover), browse link, rejection message.
- **Rewrite `UploadStep.tsx`** — owns form state (benchmark/candidates/method), composes two `Dropzone`s + selected displays + method `<select>` + gated button.
- **Create `UploadStep.css`** — selected benchmark row, candidate chips, method select, form layout, `.button-primary:disabled` rule.

## Git / Commit Convention (project-specific)

Per this project's working style, **commits require explicit user go-ahead and the user tests manually first.** This plan does NOT commit per sub-task. Implement all tasks, run the type-check and lint gates, then hand off for a manual browser walkthrough. A single commit happens at the end **only after the user approves** (Task 5).

---

### Task 1: Dropzone component

**Files:**
- Create: `reactapp/src/Dropzone.tsx`

The component manages two pieces of local state: whether a drag is currently over the zone (`dragOver`) and whether the last input contained a rejected file (`rejected`). A visually hidden `<input type="file">` is triggered by clicking the zone. Both the drop handler and the input `onChange` funnel through one `handleFiles` routine that filters by extension.

- [ ] **Step 1: Create the Dropzone component**

```tsx
// reactapp/src/Dropzone.tsx
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import './Dropzone.css';

interface DropzoneProps {
  label: string;
  multiple: boolean;
  accept: string[]; // lowercase extensions, e.g. ['.tif', '.tiff']
  onAccepted: (files: File[]) => void;
}

function Dropzone({ label, multiple, accept, onAccepted }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [rejected, setRejected] = useState(false);

  const isAccepted = (file: File) =>
    accept.some((ext) => file.name.toLowerCase().endsWith(ext));

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const files = Array.from(fileList);
    const good = files.filter(isAccepted);
    setRejected(good.length !== files.length);
    if (good.length > 0) onAccepted(good);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    e.target.value = ''; // allow re-selecting the same file
  };

  return (
    <div className="dropzone-wrap">
      <div
        className={`dropzone ${dragOver ? 'dropzone--over' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <span className="dropzone-arrow">&#8595;</span>
        <span className="dropzone-label">
          {label} or <span className="dropzone-browse">browse</span>
        </span>
        <input
          ref={inputRef}
          type="file"
          className="dropzone-input"
          multiple={multiple}
          accept={accept.join(',')}
          onChange={onChange}
        />
      </div>
      {rejected && (
        <p className="dropzone-error">Only .tif/.tiff files are accepted</p>
      )}
    </div>
  );
}

export default Dropzone;
```

Notes:
- `e.target.value = ''` after handling lets the user re-pick the same filename (otherwise `onChange` won't fire twice for an identical selection).
- The hidden input's `accept` attribute is a hint for the browse dialog; the real enforcement is `isAccepted`, which also covers drag-and-drop.

- [ ] **Step 2: Type-check**

Run: `cd reactapp && npx tsc -b`
Expected: PASS. (`Dropzone.css` does not exist yet — the import resolves at build time via Vite, but `tsc` does not check CSS imports, so this passes. If you prefer, create `Dropzone.css` empty first; Task 2 fills it.)

---

### Task 2: Dropzone styles

**Files:**
- Create: `reactapp/src/Dropzone.css`

- [ ] **Step 1: Create Dropzone.css**

```css
/* reactapp/src/Dropzone.css */

.dropzone-wrap {
  margin-bottom: 1rem;
}

.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: 1.25rem 1rem;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.dropzone--over {
  border-color: var(--color-primary);
  background: var(--color-surface-alt);
}
.dropzone-arrow {
  font-size: 1.1rem;
  color: var(--color-text-secondary);
  line-height: 1;
}
.dropzone-label {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}
.dropzone-browse {
  color: var(--color-link);
  font-weight: 600;
}
.dropzone-input {
  display: none;
}
.dropzone-error {
  margin: 0.4rem 0 0;
  font-size: 0.78rem;
  color: var(--color-error);
}
```

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS.

---

### Task 3: Rewrite UploadStep

**Files:**
- Modify: `reactapp/src/UploadStep.tsx` (full replace)

`UploadStep` holds the three pieces of form state. Benchmark is replaced on each accepted drop (take the first file, since the zone is single). Candidates are appended and deduped by `name` + `size`. The button is disabled unless a benchmark and at least one candidate are present.

- [ ] **Step 1: Replace UploadStep.tsx**

```tsx
// reactapp/src/UploadStep.tsx
import { useState } from 'react';
import Dropzone from './Dropzone';
import './UploadStep.css';

type Method = 'smallest_extent' | 'convex_hull';

interface UploadStepProps {
  onNext: () => void;
}

function UploadStep({ onNext }: UploadStepProps) {
  const [benchmark, setBenchmark] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<File[]>([]);
  const [method, setMethod] = useState<Method>('smallest_extent');

  const addCandidates = (files: File[]) => {
    setCandidates((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const fresh = files.filter((f) => !seen.has(`${f.name}:${f.size}`));
      return [...prev, ...fresh];
    });
  };

  const removeCandidate = (index: number) => {
    setCandidates((prev) => prev.filter((_, i) => i !== index));
  };

  const isValid = benchmark !== null && candidates.length > 0;

  return (
    <div className="step-placeholder upload-step">
      <h2>Upload Files</h2>

      <label className="upload-field-label">Benchmark raster</label>
      <Dropzone
        label="Drop a .tif here"
        multiple={false}
        accept={['.tif', '.tiff']}
        onAccepted={(files) => setBenchmark(files[0])}
      />
      {benchmark && (
        <div className="upload-selected">
          <span className="upload-filename">{benchmark.name}</span>
          <button
            type="button"
            className="upload-remove"
            aria-label="Remove benchmark"
            onClick={() => setBenchmark(null)}
          >
            &#10005;
          </button>
        </div>
      )}

      <label className="upload-field-label">Candidate raster(s)</label>
      <Dropzone
        label="Drop one or more .tif here"
        multiple={true}
        accept={['.tif', '.tiff']}
        onAccepted={addCandidates}
      />
      {candidates.length > 0 && (
        <div className="upload-chips">
          {candidates.map((file, i) => (
            <span className="upload-chip" key={`${file.name}:${file.size}`}>
              {file.name}
              <button
                type="button"
                className="upload-chip-remove"
                aria-label={`Remove ${file.name}`}
                onClick={() => removeCandidate(i)}
              >
                &#10005;
              </button>
            </span>
          ))}
        </div>
      )}

      <label className="upload-field-label" htmlFor="method-select">Method</label>
      <select
        id="method-select"
        className="upload-select"
        value={method}
        onChange={(e) => setMethod(e.target.value as Method)}
      >
        <option value="smallest_extent">Smallest extent</option>
        <option value="convex_hull">Convex hull</option>
      </select>

      <div className="upload-actions">
        <button
          type="button"
          className="button-primary"
          disabled={!isValid}
          onClick={onNext}
        >
          Upload &amp; Run
        </button>
      </div>
    </div>
  );
}

export default UploadStep;
```

Notes:
- The `Method` type is local to this file (not exported) — that keeps `react-refresh/only-export-components` satisfied (only the component is exported).
- The chip `key` uses `name:size`, which is safe because duplicates with the same name+size are deduped away in `addCandidates`.
- `method` is read into state and used by the `<select>`; FE3 consumes it when building the submit request, so it is not "unused" even though this task doesn't send it anywhere.

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS. (`UploadStep.css` import resolves at build; create it in Task 4. If `tsc`/lint complain about the missing module, do Task 4 first — neither tool type-checks CSS, so this normally passes.)

---

### Task 4: UploadStep styles

**Files:**
- Create: `reactapp/src/UploadStep.css`

- [ ] **Step 1: Create UploadStep.css**

```css
/* reactapp/src/UploadStep.css */

.upload-step {
  text-align: left;
}

.upload-field-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 0.4rem;
}

/* Selected benchmark filename row */
.upload-selected {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: -0.5rem 0 1rem;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}
.upload-filename {
  word-break: break-all;
}

/* Candidate chips */
.upload-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: -0.5rem 0 1rem;
}
.upload-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--color-surface-alt);
  color: var(--color-text-secondary);
  border-radius: 999px;
  padding: 0.25rem 0.65rem;
  font-size: 0.78rem;
}

/* Shared ✕ remove buttons (benchmark + chips) */
.upload-remove,
.upload-chip-remove {
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0;
  font-size: 0.8rem;
  line-height: 1;
}
.upload-remove:hover,
.upload-chip-remove:hover {
  color: var(--color-error);
}

/* Method select */
.upload-select {
  display: block;
  width: 100%;
  font-family: inherit;
  font-size: 0.9rem;
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0.5rem 0.7rem;
  margin-bottom: 1.5rem;
}

/* Actions */
.upload-actions {
  display: flex;
  justify-content: flex-end;
}

/* Disabled state for the shared .button-primary (kept out of verbatim theme.css) */
.button-primary:disabled {
  background: var(--color-border);
  color: var(--color-text-muted);
  cursor: not-allowed;
}
.button-primary:disabled:hover {
  background: var(--color-border);
}
```

- [ ] **Step 2: Type-check and lint**

Run: `cd reactapp && npx tsc -b && npm run lint`
Expected: both PASS.

---

### Task 5: Verify and commit (await user go-ahead)

**Files:** none (verification + git)

- [ ] **Step 1: Final type-check, lint, and build**

Run: `cd reactapp && npx tsc -b && npm run lint && npm run build`
Expected: all PASS, exit 0. (The build confirms the new CSS imports bundle correctly.)

- [ ] **Step 2: Manual browser walkthrough**

Run: `cd reactapp && npm run dev`
Open http://localhost:5173 (Upload is the first step) and confirm:
- Two dashed dropzones (Benchmark, Candidates) + a Method dropdown defaulting to "Smallest extent" + a grayed-out "Upload & Run" button.
- Dragging a file over a zone highlights it cyan; leaving/ dropping clears the highlight.
- Browse: clicking a zone opens the file dialog; the dialog filters to .tif/.tiff.
- Drop/select a `.tif` on Benchmark → filename appears below with a ✕; clicking ✕ removes it.
- Drop/select multiple `.tif`s on Candidates → chips appear; dropping more appends; dropping the same file again does NOT duplicate; each chip's ✕ removes just that one.
- Drop a non-`.tif` (e.g. a .png) on either zone → red "Only .tif/.tiff files are accepted" appears under that zone; the file is not added. The message clears on the next valid drop.
- "Upload & Run" stays grayed until a benchmark AND ≥1 candidate are present, then turns cyan/active. Clicking it advances to the Running step.
- Switching the dropdown to "Convex hull" works.

Report the result to the user and **wait for their go-ahead before committing.**

- [ ] **Step 3: Commit (only after user approval)**

```bash
git add .
git commit -m "feat: FIMEVAL-FE2 upload step UI with drag-and-drop pickers

Add reusable Dropzone (drag/drop/browse, .tif extension filtering, own
rejection message) and rewrite UploadStep with benchmark + candidate
pickers, removable candidate chips, method selector, and a validity-gated
Upload & Run button. UI/state only; no network calls (FE3).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Push (only after user approval)**

```bash
git push
```

---

## Self-Review

**Spec coverage** (against `2026-06-08-fimeval-fe2-upload-step-design.md`):
- `Dropzone.tsx` props `{label, multiple, accept, onAccepted}` → Task 1 ✓
- Dashed zone, label + browse, hidden input → Task 1 + Task 2 ✓
- Dragover highlight (border `--color-primary`, bg `--color-surface-alt`) → Task 1 (`dropzone--over`) + Task 2 ✓
- Extension filtering, case-insensitive, accept hint on input → Task 1 (`isAccepted`, `accept.join(',')`) ✓
- Dropzone owns its rejection message, clears on next accepted → Task 1 (`rejected` state, reset in `handleFiles`) ✓
- `UploadStep` state: benchmark replace, candidates append+dedupe by name+size, method default `smallest_extent` → Task 3 (`setBenchmark(files[0])`, `addCandidates`, `useState<Method>('smallest_extent')`) ✓
- Benchmark filename row with ✕ clear → Task 3 + Task 4 ✓
- Removable candidate chips → Task 3 + Task 4 ✓
- Method `<select>` (Smallest extent / Convex hull) → Task 3 ✓
- Button disabled unless `benchmark && candidates.length > 0`; grayed + not-allowed → Task 3 (`disabled={!isValid}`) + Task 4 (`.button-primary:disabled`) ✓
- Valid click calls `onNext` to advance → Task 3 ✓
- `.button-primary:disabled` added outside `theme.css` → Task 4 (in `UploadStep.css`) ✓
- `<select>` inherits Alan Sans → Task 4 (`font-family: inherit`) ✓
- Co-located CSS keeps `App.css` from growing → Tasks 2 & 4 ✓
- Verify tsc + lint + manual; no test framework → Tasks 2–5 ✓

**Placeholder scan:** No "TBD/handle edge cases" plan-placeholders. All code blocks are complete.

**Type consistency:** `onAccepted: (files: File[]) => void` in Task 1 matches both call sites in Task 3 (`(files) => setBenchmark(files[0])` and `addCandidates`). `Method` type defined and used consistently in Task 3. Class names used in Tasks 1/3 (`dropzone`, `dropzone--over`, `dropzone-error`, `upload-chip`, `upload-remove`, `button-primary`) all have matching rules in Tasks 2/4. CSS variables referenced all exist in `styles/theme.css`.

**Note on task ordering:** Tasks 1 and 3 import CSS files created in Tasks 2 and 4. `tsc`/ESLint don't type-check CSS imports, so the gates pass regardless of order, but for a clean `npm run dev`/`build` the CSS must exist. Implementing 1→2→3→4 in order avoids any missing-module warning.
