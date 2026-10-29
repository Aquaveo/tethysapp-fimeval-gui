// reactapp/src/RunsList.tsx
// The persistent Runs column: the user's runs from GET api/jobs, click to open a
// run's detail (/runs/:jobId), with the routed run highlighted. Polls while any
// run is in progress, and refetches at once on navigation to a run (FE64: the
// wizard navigates to the new run the moment it's submitted, before the next poll).
import { useEffect, useState } from 'react';
import { useMatch, useNavigate } from 'react-router-dom';
import { fetchJobs, type Job } from './api';
import { methodLabel } from './methodLabel';
import './RunsList.css';

const STATUS: Record<Job['status'], { cls: string; label: string }> = {
  complete: { cls: 'ok', label: 'Completed' },
  running: { cls: 'run', label: 'Running' },
  queued: { cls: 'run', label: 'Queued' },
  submitted: { cls: 'run', label: 'Submitted' },
  error: { cls: 'err', label: 'Error' },
};

function relTime(iso: string | null): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  if (d === 1) return 'yesterday';
  if (d < 7) return `${d} days ago`;
  return new Date(t).toLocaleDateString();
}

const isActive = (s: Job['status']) => s === 'running' || s === 'queued' || s === 'submitted';

export default function RunsList() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [failed, setFailed] = useState(false);
  const navigate = useNavigate();
  const selectedId = useMatch('/runs/:jobId')?.params.jobId;

  // Each run of this effect does one fetch and schedules the next via `tick`:
  // fast while something is in flight, slowly otherwise. It is also keyed on
  // the routed run (FE64), so navigating to a run — in particular the one the
  // wizard just submitted — cancels the pending poll and fetches immediately.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const next = (ms: number) => {
      timer = setTimeout(() => setTick((t) => t + 1), ms);
    };
    (async () => {
      try {
        const j = await fetchJobs();
        if (cancelled) return;
        setJobs(j);
        setFailed(false);
        next(j.some((x) => isActive(x.status)) ? 3000 : 15000);
      } catch {
        if (cancelled) return;
        setFailed(true);
        next(8000);
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tick, selectedId]);

  return (
    <div className="runs">
      <div className="runs-head">
        <h2>Runs</h2>
        {jobs && <span className="runs-count">{jobs.length}</span>}
      </div>
      <div className="runs-scroll">
        {jobs === null && !failed && <p className="runs-msg">Loading&hellip;</p>}
        {failed && jobs === null && <p className="runs-msg">Couldn&rsquo;t load your runs.</p>}
        {jobs && jobs.length === 0 && (
          <p className="runs-msg">No runs yet — start one with &ldquo;＋ New Evaluation&rdquo;.</p>
        )}
        {jobs?.map((j) => {
          const st = STATUS[j.status] ?? { cls: 'run', label: j.status };
          return (
            <button
              key={j.job_id}
              type="button"
              className={'run-item' + (String(j.job_id) === selectedId ? ' selected' : '')}
              onClick={() => navigate(`/runs/${j.job_id}`)}
            >
              <div className="run-top">
                <span className="run-num">#{j.run_number ?? j.job_id}</span>
                <span className={`pill ${st.cls}`}>{st.label}</span>
              </div>
              <div className="run-method">
                {methodLabel(j.method, j.sub_method)}
              </div>
              <div className="run-sub">{relTime(j.created)}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
