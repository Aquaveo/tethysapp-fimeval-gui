// reactapp/src/RunDetail.tsx
// The detail pane for one run (/runs/:jobId), driven by job status: queued/running
// shows live progress, error shows the captured reason, complete renders the full
// results (ResultsView). Polls until the run reaches a terminal state.
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getJobStatus, submitJob, SubmitTooLargeError,
  type JobStatus, type TooLargeInfo,
} from './api';
import InputFiles from './InputFiles';
import ResultsView from './ResultsView';
import './RunDetail.css';

const METHOD_LABELS: Record<string, string> = {
  smallest_extent: 'Smallest extent',
  convex_hull: 'Convex hull',
  intersected_extent: 'Intersected extent',
  bootstrap: 'Bootstrap',
  AOI: 'AOI',
};

const STATUS_LABEL: Record<JobStatus['status'], string> = {
  submitted: 'Submitted', queued: 'Queued', running: 'Running',
  complete: 'Complete', error: 'Error',
};

function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const inFlight = (s: JobStatus['status']) =>
  s === 'running' || s === 'queued' || s === 'submitted';

export default function RunDetail() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const navigate = useNavigate();
  // Keyed to the id so switching runs shows loading until the new poll returns,
  // without resetting state synchronously inside the effect.
  const [entry, setEntry] = useState<{ id: number; status: JobStatus } | null>(null);
  const [failedId, setFailedId] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [rerunning, setRerunning] = useState(false);
  const [rerunErr, setRerunErr] = useState<string | null>(null);
  const [tooLarge, setTooLarge] = useState<{ info: TooLargeInfo; uploadId: string } | null>(null);

  const status = entry?.id === id ? entry.status : null;
  const failed = failedId === id && status === null;

  useEffect(() => {
    if (!Number.isInteger(id)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const s = await getJobStatus(id);
        if (cancelled) return;
        setEntry({ id, status: s });
        setFailedId((prev) => (prev === id ? null : prev));
        if (inFlight(s.status)) timer = setTimeout(poll, 3000);
      } catch {
        if (cancelled) return;
        setFailedId(id);
        timer = setTimeout(poll, 5000);
      }
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  const running = !!status && inFlight(status.status);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);

  const method = status?.method ? METHOD_LABELS[status.method] ?? status.method : null;
  const terminal = !!status && (status.status === 'complete' || status.status === 'error');
  const canRerun = !!status?.upload_id && !!status?.method;

  // Re-run the same inputs (no re-upload) — resubmit upload_id + method, then open
  // the new run. Reuses the FE24 too-large/downsample modal.
  const rerun = async (downsample = false) => {
    if (!status?.upload_id || !status.method) return;
    setRerunErr(null);
    setTooLarge(null);
    setRerunning(true);
    try {
      const { job_id } = await submitJob(status.upload_id, status.method, downsample);
      navigate(`/runs/${job_id}`);
    } catch (e) {
      if (e instanceof SubmitTooLargeError && status.upload_id) {
        setTooLarge({ info: e.info, uploadId: status.upload_id });
      } else {
        setRerunErr(e instanceof Error ? e.message : 'Re-run failed. Please try again.');
      }
    } finally {
      setRerunning(false);
    }
  };

  return (
    <div className="rd">
      <header className="rd-head">
        <h2>Run #{id}{method ? ` · ${method}` : ''}</h2>
        {status && (
          <span className={`rd-status ${status.status}`}>{STATUS_LABEL[status.status]}</span>
        )}
        {terminal && canRerun && (
          <button type="button" className="rd-rerun" disabled={rerunning} onClick={() => rerun()}>
            ↻ Re-run
          </button>
        )}
      </header>

      {rerunErr && <div className="rd-errbox" role="alert"><p>{rerunErr}</p></div>}

      {status === null && !failed && (
        <div className="rd-center"><span className="rd-spinner" aria-hidden="true" />Loading&hellip;</div>
      )}
      {failed && status === null && (
        <div className="rd-center">Couldn&rsquo;t load this run.</div>
      )}

      {status && status.status !== 'complete' && status.inputs && (
        <InputFiles inputs={status.inputs} />
      )}

      {status && inFlight(status.status) && (
        <div className="rd-center rd-running">
          <span className="rd-spinner rd-spinner-lg" aria-hidden="true" />
          <p className="rd-running-msg">
            {status.status === 'queued'
              ? 'Queued — waiting for a worker slot…'
              : 'Evaluation in progress…'}
          </p>
          {status.status === 'running' && status.created && (
            <p className="rd-elapsed">
              {fmtElapsed(now - Date.parse(status.created))} elapsed — heavy methods
              typically finish in about a minute
            </p>
          )}
        </div>
      )}

      {status?.status === 'error' && (
        <div className="rd-errbox" role="alert">
          <h3>Evaluation failed</h3>
          <p>{status.reason || 'The evaluation did not complete.'}</p>
        </div>
      )}

      {status?.status === 'complete' && <ResultsView jobId={id} />}

      {tooLarge && (
        <div className="rd-modal-backdrop" role="dialog" aria-modal="true">
          <div className="rd-modal">
            <h3 className="rd-modal-title">This evaluation is large</h3>
            <p className="rd-modal-body">{tooLarge.info.error}</p>
            <div className="rd-modal-actions">
              <button type="button" className="button-secondary" onClick={() => setTooLarge(null)} disabled={rerunning}>
                Cancel
              </button>
              <button type="button" className="button-primary" onClick={() => rerun(true)} disabled={rerunning}>
                Run at a coarser resolution
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
