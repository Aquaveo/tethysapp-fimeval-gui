// reactapp/src/InputFiles.tsx
// Collapsible "Input Files" disclosure (FE14): lists what a run is evaluating —
// benchmark, candidate(s), and any AOI boundary — with resolution/CRS metadata.
// Shared by the running view (RunningStep) and the results view (ResultsStep).
import { useState } from 'react';
import type { JobInputs } from './api';
import './InputFiles.css';

function formatMeta(x: { resolution: [number, number] | null; crs: string | null }): string {
  const parts: string[] = [];
  if (x.crs) parts.push(x.crs);
  if (x.resolution) parts.push(`res ${x.resolution[0]}`);
  return parts.join(' · ');
}

export default function InputFiles({ inputs }: { inputs: JobInputs }) {
  const [open, setOpen] = useState(false);
  const rows = [
    { role: 'Benchmark', name: inputs.benchmark.name, meta: formatMeta(inputs.benchmark) },
    ...inputs.candidates.map((c) => ({
      role: 'Candidate', name: c.name, meta: formatMeta(c),
    })),
    ...(inputs.boundary
      ? [{ role: 'Boundary', name: inputs.boundary.name, meta: inputs.boundary.crs ?? '' }]
      : []),
  ];
  return (
    <div className="input-files">
      <button
        type="button"
        className="input-files-toggle"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden="true">{open ? '▼' : '▶'}</span> Input Files
      </button>
      {open && (
        <ul className="input-files-list">
          {rows.map((r, i) => (
            <li key={i} className="input-files-row">
              <span className="input-files-role">{r.role}</span>
              <span className="input-files-name">{r.name}</span>
              {r.meta && <span className="input-files-meta">{r.meta}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
