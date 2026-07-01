// reactapp/src/App.tsx
import { useCallback, useEffect, useState } from 'react';
import type { Step } from './types';
import { ensureCsrf } from './api';
import Stepper from './Stepper';
import UploadStep from './UploadStep';
import RunningStep from './RunningStep';
import ResultsStep from './ResultsStep';
import './App.css';

function AppHeader() {
  return (
    <header className="app-header">
      <h1>FIMeval</h1>
      <p className="app-subtitle">Flood Inundation Map Evaluation</p>
    </header>
  );
}

// The pop-up window view: shows Running → Results for one job (identified by the
// ?job=<id> URL param). "Start over" returns this window to the upload form.
function JobWindow({ jobId }: { jobId: number }) {
  const [step, setStep] = useState<Step>('running');
  const onComplete = useCallback(() => setStep('results'), []);
  const onReset = useCallback(() => {
    window.location.assign(window.location.pathname);
  }, []);

  return (
    <div className="app">
      <AppHeader />
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
