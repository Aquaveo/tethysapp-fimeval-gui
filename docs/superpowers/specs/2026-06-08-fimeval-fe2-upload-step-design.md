# FIMEVAL-FE2 — Upload Step UI

**Date:** 2026-06-08
**Status:** Approved, ready for implementation plan

## Goal

Replace the FE1 Upload placeholder with a real upload form: a drag-and-drop
benchmark picker, a drag-and-drop multi-candidate picker, a method selector, and
client-side validation gating the "Upload & Run" button. **UI and form state
only — no network requests.** The actual upload + job submission is FE3.

## Context

The app is a three-step wizard (FE1): Upload → Running → Results. `App.tsx` owns
the `step` state and passes `onNext` down to each step. FE1 left placeholder step
components with temporary dev nav buttons. This task fills in the Upload step.

The brand theme is already in place: `styles/theme.css` (CSS variables,
`.button-primary`), `theme.ts` (inline-style tokens), Alan Sans font, cyan
`#25C2DF` primary.

The backend upload contract (FE3 will use it, not this task) is multipart with
field `benchmark` (single file) and `candidates` (one or more files), plus a
JSON submit with `method` ∈ {`smallest_extent`, `convex_hull`}.

## Components & File Structure

All under `reactapp/src/`.

### `Dropzone.tsx` (new, reusable)
The drag-and-drop input primitive, used for both the benchmark and candidate
pickers.

- **Props:** `{ label: string; multiple: boolean; accept: string[]; onAccepted: (files: File[]) => void }`
  - `accept` is a list of lowercase extensions, e.g. `['.tif', '.tiff']`.
- **Renders:** a dashed zone showing the `label` and a "browse" affordance, plus a
  visually hidden `<input type="file">` (with `multiple` when the prop is set, and
  an `accept=".tif,.tiff"` attribute derived from `accept`).
- **Drag behavior:** highlights (border → `var(--color-primary)`, bg →
  `var(--color-surface-alt)`) while a drag is over the zone; clears on dragleave/drop.
- **Extension filtering:** on drop or input change, split the incoming files by
  whether their name ends with one of `accept` (case-insensitive). Pass the
  accepted files to `onAccepted`. If any file was rejected, show an inline
  rejection message inside the zone: "Only .tif/.tiff files are accepted." The
  message clears the next time an accepted file arrives.
- **Owns:** its drag-highlight state and its own rejection message. It does NOT
  own the selected-file list — it only emits accepted files upward.

### `Dropzone.css` (new)
Styles for the dashed zone (idle / dragover states), the browse link, and the
rejection message.

### `UploadStep.tsx` (rewritten)
Owns the form state and composes the pieces.

- **State (local):**
  - `benchmark: File | null` — a new accepted file replaces the previous one.
  - `candidates: File[]` — accepted files are appended to the existing list,
    deduped by `name` + `size`. Each is individually removable.
  - `method: 'smallest_extent' | 'convex_hull'` — defaults to `'smallest_extent'`.
- **Renders, top to bottom:**
  1. Benchmark `Dropzone` (`multiple={false}`), and below it the selected
     benchmark filename with a ✕ button to clear it (shown only when set).
  2. Candidate `Dropzone` (`multiple={true}`), and below it the selected
     candidates as removable chips (pale-cyan pills with a ✕), one per file.
  3. Method `<select>` with two options: "Smallest extent" (`smallest_extent`)
     and "Convex hull" (`convex_hull`).
  4. "Upload & Run" button.
- **Validation:** the button is `disabled` unless
  `benchmark !== null && candidates.length > 0`. Disabled state is grayed with a
  `not-allowed` cursor. There is no submit-time error text — the only inline
  errors are the per-zone `.tif` rejection messages owned by `Dropzone`.
- **Props:** keeps the existing `{ onNext: () => void }`. When the form is valid
  and "Upload & Run" is clicked, it calls `onNext()` to advance to the Running
  step (placeholder transition for this task).

### `UploadStep.css` (new)
Styles for the selected benchmark row, candidate chips, method select, the form
layout, and a `.button-primary:disabled` rule (added here, not in the verbatim
`theme.css`).

## Data Flow

```
Dropzone (benchmark)  --onAccepted(files)-->  UploadStep: setBenchmark(files[0])
Dropzone (candidates) --onAccepted(files)-->  UploadStep: append+dedupe into candidates
UploadStep: method <select>                -->  setMethod(value)
UploadStep: "Upload & Run" (enabled iff valid) --onClick--> onNext()  (advance step)
```

File/method state stays local to `UploadStep` because no later step needs the raw
files. FE3 will add the POST logic inside `UploadStep` and replace the `onNext`
prop with an `onJobCreated(jobId)` callback.

## Styling

Brand theme throughout:
- Dropzone: dashed `var(--color-border)` idle → `var(--color-primary)` on dragover;
  background `var(--color-surface-alt)` on dragover.
- Candidate chips: `var(--color-surface-alt)` background, `var(--color-text-secondary)`
  text, rounded pill, ✕ remove control.
- "Upload & Run": existing `.button-primary` class; new `:disabled` rule grays it
  and sets `cursor: not-allowed`.
- Font is inherited (Alan Sans) — the FE1 global `button { font-family: inherit }`
  already covers buttons; `<select>` gets `font-family: inherit` too.

## Out of Scope

- Any network request (upload, submit) — FE3.
- Upload progress indicators — FE3/FE4.
- File *content* validation (valid GeoTIFF, CRS, etc.) — only the filename
  extension is checked client-side; the backend/fimeval validate content.
- Persisting selections across step navigation — local component state only.
- A component test framework — none is set up; adding one is out of scope.

## Testing

Consistent with FE1:
- `npx tsc -b` type-checks cleanly.
- `npm run lint` passes.
- Manual browser walkthrough:
  - Drag (and browse) a `.tif` onto the benchmark zone → filename shows with ✕;
    clearing it removes it.
  - Drop multiple `.tif`s onto the candidate zone → chips appear; dropping more
    appends; duplicates (same name+size) are not added twice; ✕ removes a chip.
  - Drop a non-`.tif` onto either zone → inline "Only .tif/.tiff files are
    accepted" message; the file is not added.
  - "Upload & Run" is grayed until a benchmark + at least one candidate are
    present, then becomes active; clicking it advances to the Running step.
  - The method dropdown defaults to "Smallest extent" and switches to
    "Convex hull".
