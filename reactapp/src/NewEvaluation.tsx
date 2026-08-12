// reactapp/src/NewEvaluation.tsx
// Guided 3-step New Evaluation wizard (Upload → Method → Run) in the detail pane.
// Reuses the presign → direct-to-MinIO upload → submit path and the FE24
// too-large/downsample modal; on success it routes to the new run (no pop-up).
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Dropzone from './Dropzone';
import { presignUpload, putFile, submitJob, SubmitTooLargeError, type TooLargeInfo } from './api';
import './NewEvaluation.css';

type Method = 'smallest_extent' | 'convex_hull' | 'intersected_extent' | 'bootstrap' | 'AOI';
type FileProgress = { name: string; pct: number; failed: boolean };

const SHAPEFILE_EXTS = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.qpj'];

const METHODS: { value: Method; label: string; desc: string }[] = [
  { value: 'bootstrap', label: 'Bootstrap (random sampling)', desc: 'Resampled distribution of each metric — shows the box-plot.' },
  { value: 'smallest_extent', label: 'Smallest extent', desc: 'Evaluate over the overlapping extent of the inputs.' },
  { value: 'convex_hull', label: 'Convex hull', desc: 'Evaluate within the convex hull of the wet cells.' },
  { value: 'intersected_extent', label: 'Intersected extent', desc: 'Evaluate only where both maps have data.' },
  { value: 'AOI', label: 'Area of interest (AOI)', desc: 'Evaluate inside an uploaded boundary shapefile.' },
];

function mergeUnique(prev: File[], incoming: File[]): File[] {
  const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
  return [...prev, ...incoming.filter((f) => !seen.has(`${f.name}:${f.size}`))];
}

export default function NewEvaluation() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [benchmark, setBenchmark] = useState<File | null>(null);
  const [candidates, setCandidates] = useState<File[]>([]);
  const [boundary, setBoundary] = useState<File[]>([]);
  const [method, setMethod] = useState<Method>('bootstrap');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<FileProgress[] | null>(null);
  const [tooLarge, setTooLarge] = useState<{ info: TooLargeInfo; uploadId: string } | null>(null);

  const isAOI = method === 'AOI';
  const hasShp = boundary.some((f) => f.name.toLowerCase().endsWith('.shp'));
  const step1Valid = benchmark !== null && candidates.length > 0;
  const step2Valid = !isAOI || hasShp;

  const addCandidates = (files: File[]) => setCandidates((p) => mergeUnique(p, files));
  const removeCandidate = (i: number) => setCandidates((p) => p.filter((_, idx) => idx !== i));
  const addBoundary = (files: File[]) => setBoundary((p) => mergeUnique(p, files));
  const removeBoundary = (i: number) => setBoundary((p) => p.filter((_, idx) => idx !== i));

  const runEvaluation = async () => {
    if (!benchmark) return;
    setError(null);
    setTooLarge(null);
    setSubmitting(true);
    let uploadId: string | null = null;
    try {
      const { upload_id, targets } = await presignUpload(
        benchmark, candidates, isAOI ? boundary : [],
      );
      uploadId = upload_id;

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

      // Upload every file straight to MinIO in parallel; Django is out of the path.
      await Promise.all(
        pairs.map((p, idx) =>
          putFile(p.url, p.file, (pct) =>
            setProgress((prev) => prev && prev.map((x, i) => (i === idx ? { ...x, pct } : x))),
          ).catch((err) => {
            setProgress((prev) => prev && prev.map((x, i) => (i === idx ? { ...x, failed: true } : x)));
            throw err;
          }),
        ),
      );

      const { job_id } = await submitJob(upload_id, method);
      navigate(`/runs/${job_id}`);
    } catch (e) {
      if (e instanceof SubmitTooLargeError && uploadId) {
        // Files already uploaded — offer a coarser run instead of re-uploading.
        setTooLarge({ info: e.info, uploadId });
      } else {
        setError(e instanceof Error ? e.message : 'Upload failed. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Accept the coarser-resolution run: resubmit the same upload with downsample.
  const acceptDownsample = async () => {
    if (!tooLarge) return;
    const { uploadId } = tooLarge;
    setTooLarge(null);
    setError(null);
    setSubmitting(true);
    try {
      const { job_id } = await submitJob(uploadId, method, true);
      navigate(`/runs/${job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Submission failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const next = () => (step < 3 ? setStep(step + 1) : runEvaluation());
  const nextDisabled =
    submitting || (step === 1 && !step1Valid) || (step === 2 && !step2Valid);

  return (
    <div className="ne">
      <header className="ne-head">
        <h2>New Evaluation</h2>
        <p>A quick guided flow — upload, choose a method, and run. It opens right here.</p>
      </header>

      <div className="ne-stepper">
        {['Upload', 'Method', 'Run'].map((label, i) => {
          const n = i + 1;
          return (
            <div key={label} className="ne-step-wrap">
              <div className={`ne-step${n === step ? ' active' : ''}${n < step ? ' done' : ''}`}>
                <span className="ne-dot">{n < step ? '✓' : n}</span> {label}
              </div>
              {n < 3 && <span className={`ne-line${n < step ? ' done' : ''}`} />}
            </div>
          );
        })}
      </div>

      <div className="ne-card">
        {step === 1 && (
          <div className="ne-body">
            <span className="ne-label">Benchmark raster</span>
            <Dropzone label="Drop a .tif here" multiple={false} accept={['.tif', '.tiff']}
              onAccepted={(f) => setBenchmark(f[0])} />
            {benchmark && (
              <div className="ne-selected">
                <span className="ne-tick" aria-hidden="true">✓</span>
                <span className="ne-fname">{benchmark.name}</span>
                <button type="button" className="ne-x" aria-label="Remove benchmark"
                  onClick={() => setBenchmark(null)}>✕</button>
              </div>
            )}

            <span className="ne-label">Candidate raster(s)</span>
            <Dropzone label="Drop one or more .tif here" multiple accept={['.tif', '.tiff']}
              onAccepted={addCandidates} />
            {candidates.length > 0 && (
              <div className="ne-chips">
                {candidates.map((f, i) => (
                  <span className="ne-chip" key={`${f.name}:${f.size}`}>
                    <span className="ne-tick" aria-hidden="true">✓</span>{f.name}
                    <button type="button" className="ne-chip-x" aria-label={`Remove ${f.name}`}
                      onClick={() => removeCandidate(i)}>✕</button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="ne-body">
            <div className="ne-methods">
              {METHODS.map((m) => (
                <button key={m.value} type="button"
                  className={`ne-method${method === m.value ? ' sel' : ''}`}
                  onClick={() => setMethod(m.value)}>
                  <span className="ne-mradio" aria-hidden="true" />
                  <span>
                    <span className="ne-mt">{m.label}</span>
                    <span className="ne-md">{m.desc}</span>
                  </span>
                </button>
              ))}
            </div>
            {isAOI && (
              <div className="ne-aoi">
                <span className="ne-label">AOI boundary shapefile (all parts)</span>
                <Dropzone label="Drop the shapefile parts (.shp, .shx, .dbf, .prj…)" multiple
                  accept={SHAPEFILE_EXTS} onAccepted={addBoundary} />
                {boundary.length > 0 && (
                  <div className="ne-chips">
                    {boundary.map((f, i) => (
                      <span className="ne-chip" key={`${f.name}:${f.size}`}>
                        <span className="ne-tick" aria-hidden="true">✓</span>{f.name}
                        <button type="button" className="ne-chip-x" aria-label={`Remove ${f.name}`}
                          onClick={() => removeBoundary(i)}>✕</button>
                      </span>
                    ))}
                  </div>
                )}
                {!hasShp && (
                  <p className="ne-hint">Select all parts — a <strong>.shp</strong> file is required.</p>
                )}
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="ne-body">
            <div className="ne-review-row"><span className="ne-k">Benchmark</span><span>{benchmark?.name}</span></div>
            <div className="ne-review-row"><span className="ne-k">Candidates</span><span>{candidates.map((c) => c.name).join(', ')}</span></div>
            {isAOI && (
              <div className="ne-review-row"><span className="ne-k">Boundary</span><span>{boundary.map((b) => b.name).join(', ')}</span></div>
            )}
            <div className="ne-review-row"><span className="ne-k">Method</span><span>{METHODS.find((m) => m.value === method)?.label}</span></div>
          </div>
        )}
      </div>

      {error && <div className="ne-error" role="alert">{error}</div>}

      {progress && (
        <div className="ne-progress" role="status" aria-live="polite">
          {progress.map((p, i) => (
            <div className="ne-prog-row" key={i}>
              <span className="ne-prog-name" title={p.name}>{p.name}</span>
              <span className="ne-prog-track">
                <span className={`ne-prog-fill${p.failed ? ' failed' : ''}`} style={{ width: `${p.pct}%` }} />
              </span>
              <span className="ne-prog-pct">{p.failed ? 'failed' : p.pct === 100 ? '✓' : `${p.pct}%`}</span>
            </div>
          ))}
        </div>
      )}

      <div className="ne-nav">
        <button type="button" className="button-secondary" disabled={step === 1 || submitting}
          onClick={() => setStep(step - 1)}>← Back</button>
        <button type="button" className="button-primary" disabled={nextDisabled} onClick={next}>
          {submitting ? 'Working…' : step === 3 ? 'Run evaluation' : 'Next →'}
        </button>
      </div>

      {tooLarge && (
        <div className="ne-modal-backdrop" role="dialog" aria-modal="true">
          <div className="ne-modal">
            <h3 className="ne-modal-title">This evaluation is large</h3>
            <p className="ne-modal-body">{tooLarge.info.error}</p>
            <div className="ne-modal-actions">
              <button type="button" className="button-secondary" onClick={() => setTooLarge(null)} disabled={submitting}>
                Cancel
              </button>
              <button type="button" className="button-primary" onClick={acceptDownsample} disabled={submitting}>
                Run at a coarser resolution
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
