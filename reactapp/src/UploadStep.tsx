// reactapp/src/UploadStep.tsx
import { useState } from 'react';
import Dropzone from './Dropzone';
import { presignUpload, putFile, submitJob } from './api';
import './UploadStep.css';

// Per-file upload progress shown while files stream directly to MinIO.
type FileProgress = { name: string; pct: number; failed: boolean };

type Method =
  | 'smallest_extent'
  | 'convex_hull'
  | 'intersected_extent'
  | 'bootstrap'
  | 'AOI';

// ESRI shapefile bundle components (AOI boundary upload).
const SHAPEFILE_EXTS = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.qpj'];

// Append only files not already selected (deduped by name + size).
function mergeUnique(prev: File[], incoming: File[]): File[] {
  const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
  return [...prev, ...incoming.filter((f) => !seen.has(`${f.name}:${f.size}`))];
}

function UploadStep() {
  const [benchmark, setBenchmark] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<File[]>([]);
  const [boundary, setBoundary] = useState<File[]>([]);
  const [method, setMethod] = useState<Method>('smallest_extent');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<FileProgress[] | null>(null);
  const [lastRun, setLastRun] = useState<
    { jobId: number; url: string; blocked: boolean } | null
  >(null);

  const addCandidates = (files: File[]) => setCandidates((prev) => mergeUnique(prev, files));
  const removeCandidate = (index: number) =>
    setCandidates((prev) => prev.filter((_, i) => i !== index));

  const addBoundary = (files: File[]) => setBoundary((prev) => mergeUnique(prev, files));
  const removeBoundary = (index: number) =>
    setBoundary((prev) => prev.filter((_, i) => i !== index));

  const isAOI = method === 'AOI';
  const hasShp = boundary.some((f) => f.name.toLowerCase().endsWith('.shp'));
  const isValid =
    benchmark !== null && candidates.length > 0 && (!isAOI || hasShp);

  const jobViewUrl = (id: number) =>
    `${window.location.origin}${window.location.pathname}?job=${id}`;

  const resetForm = () => {
    setBenchmark(null);
    setCandidates([]);
    setBoundary([]);
    setError(null);
    setProgress(null);
  };

  const handleSubmit = async () => {
    if (!benchmark) return;
    setError(null);
    setLastRun(null);
    setSubmitting(true);

    // Open the results pop-up synchronously, on the click, so the browser
    // doesn't block it — a pop-up opened after the upload's await would be.
    const popup = window.open('', '_blank', 'width=950,height=850');
    if (popup) {
      popup.document.write(
        '<title>FIMeval — preparing…</title>' +
          '<body style="font-family:sans-serif;padding:1.5rem;color:#152428">' +
          'Preparing your evaluation…</body>',
      );
    }

    try {
      const { upload_id, targets } = await presignUpload(
        benchmark, candidates, isAOI ? boundary : [],
      );

      // Pair each presigned target with its File (match by field + filename).
      const pool: { field: string; file: File }[] = [
        { field: 'benchmark', file: benchmark },
        ...candidates.map((f) => ({ field: 'candidate', file: f })),
        ...(isAOI ? boundary : []).map((f) => ({ field: 'boundary', file: f })),
      ];
      const used = new Set<number>();
      const pairs = targets.map((t) => {
        const i = pool.findIndex(
          (p, idx) => !used.has(idx) && p.field === t.field && p.file.name === t.filename,
        );
        if (i < 0) throw new Error(`No local file matched ${t.filename}`);
        used.add(i);
        return { url: t.url, file: pool[i].file };
      });

      setProgress(pairs.map((p) => ({ name: p.file.name, pct: 0, failed: false })));

      // Upload every file directly to MinIO in parallel; Django is out of the
      // data path. Any failed PUT rejects the batch and is marked in the UI.
      await Promise.all(
        pairs.map((p, idx) =>
          putFile(p.url, p.file, (pct) =>
            setProgress((prev) => prev && prev.map((x, i) => (i === idx ? { ...x, pct } : x))),
          ).catch((err) => {
            setProgress((prev) =>
              prev && prev.map((x, i) => (i === idx ? { ...x, failed: true } : x)),
            );
            throw err;
          }),
        ),
      );

      const { job_id } = await submitJob(upload_id, method);
      const url = jobViewUrl(job_id);
      if (popup && !popup.closed) {
        popup.location.href = url;
        setLastRun({ jobId: job_id, url, blocked: false });
      } else {
        setLastRun({ jobId: job_id, url, blocked: true });
      }
      resetForm();
    } catch (e) {
      if (popup && !popup.closed) popup.close();
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
        <option value="intersected_extent">Intersection</option>
        <option value="bootstrap">Bootstrap</option>
        <option value="AOI">AOI (Area of Interest)</option>
      </select>

      {isAOI && (
        <>
          <span className="upload-field-label">AOI shapefile (all parts)</span>
          <Dropzone
            label="Drop the shapefile parts (.shp, .shx, .dbf, .prj…)"
            multiple
            accept={SHAPEFILE_EXTS}
            onAccepted={addBoundary}
          />
          {boundary.length > 0 && (
            <div className="upload-chips">
              {boundary.map((file, i) => (
                <span className="upload-chip" key={`${file.name}:${file.size}`}>
                  <span className="upload-tick" aria-hidden="true">&#10003;</span>
                  {file.name}
                  <button
                    type="button"
                    className="upload-chip-remove"
                    aria-label={`Remove ${file.name}`}
                    onClick={() => removeBoundary(i)}
                  >
                    &#10005;
                  </button>
                </span>
              ))}
            </div>
          )}
          {!hasShp && (
            <p className="upload-hint" role="status">
              Select all parts of the shapefile — a <strong>.shp</strong> file is required.
            </p>
          )}
        </>
      )}

      {error && (
        <div className="upload-error" role="alert">
          {error}
        </div>
      )}

      {progress && (
        <div className="upload-progress" role="status" aria-live="polite">
          {progress.map((p, i) => (
            <div className="upload-progress-row" key={i}>
              <span className="upload-progress-name" title={p.name}>{p.name}</span>
              <span className="upload-progress-track">
                <span
                  className={`upload-progress-fill${p.failed ? ' failed' : ''}`}
                  style={{ width: `${p.pct}%` }}
                />
              </span>
              <span className="upload-progress-pct">
                {p.failed ? 'failed' : p.pct === 100 ? '✓' : `${p.pct}%`}
              </span>
            </div>
          ))}
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

      {lastRun && (
        <div className="upload-launched" role="status">
          {lastRun.blocked ? (
            <>
              Your browser blocked the pop-up.{' '}
              <a href={lastRun.url} target="_blank" rel="noopener noreferrer">
                Open the results window
              </a>
              .
            </>
          ) : (
            <>
              Run #{lastRun.jobId} started in a new window.{' '}
              <a href={lastRun.url} target="_blank" rel="noopener noreferrer">
                Reopen it
              </a>{' '}
              if you closed it.
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default UploadStep;
