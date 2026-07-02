// reactapp/src/App.tsx
import { useCallback, useEffect, useState } from 'react';
import type { Step } from './types';
import { ensureCsrf, getJobStatus } from './api';
import Stepper from './Stepper';
import UploadStep from './UploadStep';
import RunningStep from './RunningStep';
import ResultsStep from './ResultsStep';
import './App.css';

const METHOD_LABELS: Record<string, string> = {
  smallest_extent: 'Smallest Extent',
  convex_hull: 'Convex Hull',
  intersected_extent: 'Intersection',
  bootstrap: 'Bootstrap',
  AOI: 'AOI',
};

function AppHeader({ method }: { method?: string | null }) {
  return (
    <header className="app-header">
      <h1>FIMeval</h1>
      <p className="app-subtitle">Flood Inundation Map Evaluation</p>
      {method && (
        <span className="app-method-badge">{METHOD_LABELS[method] ?? method}</span>
      )}
    </header>
  );
}

// The pop-up window view: shows Running → Results for one job (identified by the
// ?job=<id> URL param). "Start over" returns this window to the upload form.
function JobWindow({ jobId }: { jobId: number }) {
  const [step, setStep] = useState<Step>('running');
  const [method, setMethod] = useState<string | null>(null);
  const onComplete = useCallback(() => setStep('results'), []);
  const onReset = useCallback(() => {
    window.location.assign(window.location.pathname);
  }, []);

  // Fetch the job's method once so it can be highlighted in the header.
  useEffect(() => {
    let cancelled = false;
    getJobStatus(jobId)
      .then((s) => {
        if (!cancelled) setMethod(s.method);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  return (
    <div className="app">
      <AppHeader method={method} />
      <Stepper current={step} />
      <main className="step-container">
        {step === 'running' && (
          <RunningStep jobId={jobId} onComplete={onComplete} onReset={onReset} />
        )}
        {step === 'results' && <ResultsStep jobId={jobId} onReset={onReset} />}
      </main>
    </div>
  );
}

// The main window: an upload launcher. Each run opens its results in a pop-up
// (see UploadStep) and the form resets, ready for another run.
function MainWindow() {
  return (
    <div className="app">
      <AppHeader />
      <main className="step-container">
        <UploadStep />
      </main>
    </div>
  );
}

function App() {
  useEffect(() => {
    ensureCsrf();
  }, []);

  const jobParam = new URLSearchParams(window.location.search).get('job');
  const jobId = jobParam !== null ? Number(jobParam) : NaN;

  return Number.isInteger(jobId) && jobId >= 0 ? (
    <JobWindow jobId={jobId} />
  ) : (
    <MainWindow />
  );
}

export default App;
