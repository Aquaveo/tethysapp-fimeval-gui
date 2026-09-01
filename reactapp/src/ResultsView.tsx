// reactapp/src/ResultsView.tsx
// Renders a completed run's results in the detail pane: Input Files, the
// contingency map (first, FE21), box plots (bootstrap) / metrics table, headline
// cards, and per-file downloads. Self-loads outputs/metrics/bootstrap/inputs.
// (Export + Re-run actions are added in FE31.)
import { Fragment, useEffect, useState } from 'react';
import {
  getJobOutputs,
  getJobMetrics,
  getBootstrapDistribution,
  getJobStatus,
  downloadUrl,
  downloadAllUrl,
} from './api';
import type { OutputFile, JobMetrics, BootstrapStats, JobInputs } from './api';
import BootstrapBoxPlots from './BootstrapBoxPlots';
import { bootstrapMedian } from './bootstrapMetrics';
import ContingencyMap from './ContingencyMap';
import InputFiles from './InputFiles';
import ErrorBoundary from './ErrorBoundary';
import './ResultsStep.css';

const HEADLINE_METRICS = ['CSI', 'POD', 'FAR'];

function formatValue(v: number | null): string {
  if (v === null) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(4);
}

export default function ResultsView({ jobId }: { jobId: number }) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [metrics, setMetrics] = useState<JobMetrics | null>(null);
  const [bootstrap, setBootstrap] = useState<BootstrapStats | null>(null);
  const [inputs, setInputs] = useState<JobInputs | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retried = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const out = await getJobOutputs(jobId);
        if (cancelled) return;
        setOutputs(out.files);
        try {
          const m = await getJobMetrics(jobId);
          if (!cancelled) setMetrics(m);
        } catch {
          if (!cancelled) setMetrics(null);
        }
        try {
          const b = await getBootstrapDistribution(jobId);
          if (!cancelled) setBootstrap(b);
        } catch {
          if (!cancelled) setBootstrap(null);
        }
        try {
          const s = await getJobStatus(jobId);
          if (!cancelled) setInputs(s.inputs ?? null);
        } catch {
          if (!cancelled) setInputs(null);
        }
        if (!cancelled) setPhase('ready');
      } catch {
        if (cancelled) return;
        if (!retried) {
          retried = true;
          timeout = setTimeout(load, 2000);
        } else {
          setPhase('error');
        }
      }
    };

    load();
    return () => {
      cancelled = true;
      if (timeout !== undefined) clearTimeout(timeout);
    };
  }, [jobId]);

  if (phase === 'loading') {
    return (
      <div className="results-step">
        <div className="results-spinner" aria-hidden="true" />
        <p className="results-loading">Loading results&hellip;</p>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="results-step">
        <p className="results-error">Could not load the evaluation results.</p>
      </div>
    );
  }

  const candidates = metrics?.candidates ?? [];
  const firstCand = candidates[0];
  const metricValue = (name: string): number | null => {
    if (!metrics || !firstCand) return null;
    const row = metrics.metrics.find((m) => m.metric === name);
    return row ? row.values[firstCand] ?? null : null;
  };
  // FE51: for bootstrap runs, show the whole-domain metric alongside the median
  // of the bootstrap distribution. Names are normalized (FE53: "Acc" ↔
  // "Accuracy") so the median lines up with its whole-domain row.
  const showBoot = !!(bootstrap && bootstrap.candidates.length > 0);
  const bootMedian = (metric: string, cand: string): number | null =>
    bootstrapMedian(bootstrap, metric, cand);
  const headline = HEADLINE_METRICS
    .map((name) => ({ name, value: metricValue(name) }))
    .filter((h) => h.value !== null);
  // A convenience download for the contingency raster (also in the file list).
  const contingency = outputs.find(
    (f) => /contingenc/i.test(f.name) && /\.tiff?$/i.test(f.name),
  );

  return (
    <div className="results-step">
      {/* What the run evaluated (FE22). */}
      {inputs && <InputFiles inputs={inputs} />}

      {/* Contingency map first (FE21); renders nothing when there's no COG. */}
      <ContingencyMap jobId={jobId} />

      {/* Second: box plots for bootstrap, else the metrics table. */}
      {bootstrap && bootstrap.candidates.length > 0 && (
        <ErrorBoundary
          fallback={
            <div className="results-panel results-panel-title">
              Could not render the bootstrap distribution chart.
            </div>
          }
        >
          <BootstrapBoxPlots data={bootstrap} />
        </ErrorBoundary>
      )}

      {headline.length > 0 && (
        <div className="results-cards">
          {headline.map((h) => (
            <div className="results-card" key={h.name}>
              <div className="results-card-label">{h.name}</div>
              <div className={`results-card-value ${h.name === 'CSI' ? 'is-csi' : ''}`}>
                {formatValue(h.value)}
              </div>
            </div>
          ))}
        </div>
      )}

      {metrics && metrics.metrics.length > 0 && (
        <div className="results-panel">
          <div className="results-panel-title">
            {showBoot ? 'Metrics — whole domain vs. bootstrap' : 'All metrics'}
          </div>
          <table className="results-table">
            <thead>
              {showBoot ? (
                <>
                  <tr>
                    <th rowSpan={2}>Metric</th>
                    {candidates.map((c) => (
                      <th key={c} className="num" colSpan={2}>{c}</th>
                    ))}
                  </tr>
                  <tr>
                    {candidates.map((c) => (
                      <Fragment key={c}>
                        <th className="num">Whole domain</th>
                        <th className="num">Bootstrap median</th>
                      </Fragment>
                    ))}
                  </tr>
                </>
              ) : (
                <tr>
                  <th>Metric</th>
                  {candidates.map((c) => (
                    <th key={c} className="num">{c}</th>
                  ))}
                </tr>
              )}
            </thead>
            <tbody>
              {metrics.metrics.map((row) => (
                <tr key={row.metric}>
                  <td>{row.metric}</td>
                  {candidates.map((c) =>
                    showBoot ? (
                      <Fragment key={c}>
                        <td className="num">{formatValue(row.values[c] ?? null)}</td>
                        <td className="num">{formatValue(bootMedian(row.metric, c))}</td>
                      </Fragment>
                    ) : (
                      <td key={c} className="num">{formatValue(row.values[c] ?? null)}</td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {showBoot && (
            <p className="results-table-note">
              <strong>Whole domain</strong> = the metric computed over all evaluated pixels.{' '}
              <strong>Bootstrap median</strong> = the median across the resampling iterations
              (full distribution shown in the box-plots above).
            </p>
          )}
        </div>
      )}

      <div className="results-panel">
        <div className="results-downloadall">
          <div className="results-downloadall-text">
            <div className="results-panel-title results-downloadall-title">Download results</div>
            <span className="results-downloadall-hint">All output files bundled into one ZIP.</span>
          </div>
          <div className="results-download-buttons">
            {contingency && (
              <a className="button-secondary" href={downloadUrl(jobId, contingency.key)} download>
                ⬇ Contingency map (GeoTIFF)
              </a>
            )}
            <a className="button-primary results-download-all" href={downloadAllUrl(jobId)}>
              Download Results (.zip)
            </a>
          </div>
        </div>
        <div className="results-panel-title">Individual files</div>
        <ul className="results-files">
          {outputs.map((f) => (
            <li className="results-file" key={f.key}>
              <span className="results-file-name">{f.name}</span>
              <a className="results-download-link" href={downloadUrl(jobId, f.key)} download>
                Download
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
