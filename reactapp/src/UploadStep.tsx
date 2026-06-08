// reactapp/src/UploadStep.tsx
interface UploadStepProps {
  onNext: () => void;
}

function UploadStep({ onNext }: UploadStepProps) {
  return (
    <div className="step-placeholder">
      <h2>Upload Files</h2>
      <p>File pickers and method selector will go here (FIMEVAL-FE2).</p>
      {/* TODO(FE3): replace temporary dev nav with real upload+submit transition */}
      <div className="dev-nav">
        <button className="button-primary" onClick={onNext}>Next &rarr;</button>
      </div>
    </div>
  );
}

export default UploadStep;
