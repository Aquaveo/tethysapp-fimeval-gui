// reactapp/src/RunningStep.tsx
import { useEffect, useState } from 'react';
import { getJobStatus, type JobInputs } from './api';
import './RunningStep.css';

function formatMeta(x: { resolution: [number, number] | null; crs: string | null }): string {
  const parts: string[] = [];
  if (x.crs) parts.push(x.crs);
  if (x.resolution) parts.push(`res ${x.resolution[0]}`);
  return parts.join(' · ');
}

function InputFiles({ inputs }: { inputs: JobInputs }) {
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

interface RunningStepProps {
  jobId: number;
  onComplete: () => void;
  onReset: () => void;
}

function formatElapsed(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function RunningStep({ jobId, onComplete, onReset }: RunningStepProps) {
  const [errored, setErrored] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [inputs, setInputs] = useState<JobInputs | null>(null);
  const [phase, setPhase] = useState<'submitted' | 'queued' | 'running'>('submitted');
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const status = await getJobStatus(jobId);
        if (cancelled) return;
        if (status.inputs) setInputs(status.inputs);
        if (status.status === 'complete') {
          onComplete();
          return;
        }
        if (status.status === 'error') {
          setReason(status.reason ?? null);
          setErrored(true);
          return;
        }
        if (status.status === 'queued' || status.status === 'running') {
          setPhase(status.status);
        }
        // Elapsed counts from job creation; fall back to first-poll time if
        // the backend didn't record a creation timestamp.
        if (status.created) {
          const created = Date.parse(status.created);
          if (!Number.isNaN(created)) setStartedAt(created);
        } else {
          setStartedAt((prev) => prev ?? Date.now());
        }
        // submitted / queued / running — keep polling
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

  // 1s tick so the elapsed readout advances between polls.
  useEffect(() => {
    if (phase !== 'running') return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [phase]);

  if (errored) {
    return (
      <div className="step-placeholder running-step">
        <h2>Evaluation Failed</h2>
        <p className="running-error">{reason || 'The evaluation failed.'}</p>
        <div className="running-actions">
          <button type="button" className="button-primary" onClick={onReset}>
            Start Over
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'queued') {
    return (
      <div className="step-placeholder running-step">
        <h2>Queued</h2>
        <div className="running-queued-dot" aria-hidden="true" />
        <p className="running-message">Waiting for a worker slot&hellip;</p>
        <p className="running-hint">
          Your job is waiting for an available worker. It will start automatically.
        </p>
        <p className="running-jobid">(Job #{jobId})</p>
        {inputs && <InputFiles inputs={inputs} />}
      </div>
    );
  }

  return (
    <div className="step-placeholder running-step">
      <h2>Running</h2>
      <div className="running-spinner" aria-hidden="true" />
      <p className="running-message">Evaluation in progress&hellip;</p>
      {phase === 'running' && startedAt !== null && (
        <p className="running-elapsed">
          {formatElapsed(now - startedAt)} elapsed — heavy methods typically
          finish in about a minute
        </p>
      )}
      <p className="running-jobid">(Job #{jobId})</p>
      {inputs && <InputFiles inputs={inputs} />}
    </div>
  );
}

export default RunningStep;
