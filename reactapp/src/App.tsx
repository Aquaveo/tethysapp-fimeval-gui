// reactapp/src/App.tsx
import { useState } from 'react';
import { STEP_ORDER, type Step } from './types';
import Stepper from './Stepper';
import UploadStep from './UploadStep';
import RunningStep from './RunningStep';
import ResultsStep from './ResultsStep';
import './App.css';

function App() {
  const [step, setStep] = useState<Step>('upload');

  const index = STEP_ORDER.indexOf(step);
  const goNext = () => {
    if (index < STEP_ORDER.length - 1) setStep(STEP_ORDER[index + 1]);
  };
  const goBack = () => {
    if (index > 0) setStep(STEP_ORDER[index - 1]);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>FIMeval</h1>
        <p className="app-subtitle">Flood Inundation Map Evaluation</p>
      </header>

      <Stepper current={step} />

      <main className="step-container">
        {step === 'upload' && <UploadStep onNext={goNext} />}
        {step === 'running' && <RunningStep onNext={goNext} onBack={goBack} />}
        {step === 'results' && <ResultsStep onBack={goBack} />}
      </main>
    </div>
  );
}

export default App;
