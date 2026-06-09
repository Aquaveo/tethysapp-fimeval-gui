// reactapp/src/UploadStep.tsx
import { useState } from 'react';
import Dropzone from './Dropzone';
import { uploadFiles, submitJob } from './api';
import './UploadStep.css';

type Method = 'smallest_extent' | 'convex_hull';

interface UploadStepProps {
  onJobCreated: (jobId: number) => void;
}

function UploadStep({ onJobCreated }: UploadStepProps) {
  const [benchmark, setBenchmark] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<File[]>([]);
  const [method, setMethod] = useState<Method>('smallest_extent');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addCandidates = (files: File[]) => {
    setCandidates((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const fresh = files.filter((f) => !seen.has(`${f.name}:${f.size}`));
      return [...prev, ...fresh];
    });
  };

  const removeCandidate = (index: number) => {
    setCandidates((prev) => prev.filter((_, i) => i !== index));
  };

  const isValid = benchmark !== null && candidates.length > 0;

  const handleSubmit = async () => {
    if (!benchmark) return;
    setError(null);
    setSubmitting(true);
    try {
      const { upload_id } = await uploadFiles(benchmark, candidates);
      const { job_id } = await submitJob(upload_id, method);
      onJobCreated(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="step-placeholder upload-step">
      <h2>Upload Files</h2>

      <span className="upload-field-label">Benchmark raster</span>
      <Dropzone
        label="Drop a .tif here"
        multiple={false}
        accept={['.tif', '.tiff']}
        onAccepted={(files) => setBenchmark(files[0])}
      />
      {benchmark && (
        <div className="upload-selected">
          <span className="upload-tick" aria-hidden="true">&#10003;</span>
          <span className="upload-filename">{benchmark.name}</span>
          <button
            type="button"
            className="upload-remove"
            aria-label="Remove benchmark"
            onClick={() => setBenchmark(null)}
          >
            &#10005;
          </button>
        </div>
      )}

      <span className="upload-field-label">Candidate raster(s)</span>
      <Dropzone
        label="Drop one or more .tif here"
        multiple
        accept={['.tif', '.tiff']}
        onAccepted={addCandidates}
      />
      {candidates.length > 0 && (
        <div className="upload-chips">
          {candidates.map((file, i) => (
            <span className="upload-chip" key={`${file.name}:${file.size}`}>
              <span className="upload-tick" aria-hidden="true">&#10003;</span>
              {file.name}
              <button
                type="button"
                className="upload-chip-remove"
                aria-label={`Remove ${file.name}`}
                onClick={() => removeCandidate(i)}
              >
                &#10005;
              </button>
            </span>
          ))}
        </div>
      )}

      <label className="upload-field-label" htmlFor="method-select">Method</label>
      <select
        id="method-select"
        className="upload-select"
        value={method}
        onChange={(e) => setMethod(e.target.value as Method)}
      >
        <option value="smallest_extent">Smallest extent</option>
        <option value="convex_hull">Convex hull</option>
      </select>

      {error && (
        <div className="upload-error" role="alert">
          {error}
        </div>
      )}

      <div className="upload-actions">
        <button
          type="button"
          className="button-primary"
          disabled={!isValid || submitting}
          onClick={handleSubmit}
        >
          {submitting ? (
            <>
              <span className="upload-spinner" aria-hidden="true" />
              Uploading&hellip;
            </>
          ) : (
            'Upload & Run'
          )}
        </button>
      </div>
    </div>
  );
}

export default UploadStep;
