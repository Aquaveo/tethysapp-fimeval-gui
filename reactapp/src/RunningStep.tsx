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
        <h2>Evaluation Failed</h2>
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
