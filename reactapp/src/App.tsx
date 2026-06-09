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
