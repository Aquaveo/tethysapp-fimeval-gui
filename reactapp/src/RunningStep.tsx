// reactapp/src/RunningStep.tsx
interface RunningStepProps {
  jobId: number | null;
  onNext: () => void;
  onBack: () => void;
}

function RunningStep({ jobId, onNext, onBack }: RunningStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Running</h2>
      <p>
        Evaluation running&hellip;
        {jobId !== null && ` (Job #${jobId})`}
      </p>
      {/* TODO(FE4): replace temporary dev nav with real status-poll transition */}
      <div className="dev-nav">
        <button className="btn-back" onClick={onBack}>&larr; Back</button>
        <button className="button-primary" onClick={onNext}>Next &rarr;</button>
      </div>
    </div>
  );
}

export default RunningStep;
