// reactapp/src/ResultsStep.tsx
interface ResultsStepProps {
  onBack: () => void;
}

function ResultsStep({ onBack }: ResultsStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Results</h2>
      <p>Metrics table and download links will go here (FIMEVAL-FE5).</p>
      {/* TODO(FE5): replace temporary dev nav with real "Start New Evaluation" reset */}
      <div className="dev-nav">
        <button className="btn-back" onClick={onBack}>&larr; Back</button>
      </div>
    </div>
  );
}

export default ResultsStep;
