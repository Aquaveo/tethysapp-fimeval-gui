// reactapp/src/ResultsStep.tsx
import { useEffect, useState } from 'react';
import {
  getJobOutputs,
  getJobMetrics,
  getBootstrapDistribution,
  downloadUrl,
  downloadAllUrl,
} from './api';
import type { OutputFile, JobMetrics, BootstrapStats } from './api';
import BootstrapBoxPlots from './BootstrapBoxPlots';
import ErrorBoundary from './ErrorBoundary';
import './ResultsStep.css';

interface ResultsStepProps {
  jobId: number;
  onReset: () => void;
}

const HEADLINE_METRICS = ['CSI', 'POD', 'FAR'];

function formatValue(v: number | null): string {
  if (v === null) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(4);
}

function ResultsStep({ jobId, onReset }: ResultsStepProps) {
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [metrics, setMetrics] = useState<JobMetrics | null>(null);
  const [bootstrap, setBootstrap] = useState<BootstrapStats | null>(null);

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
          // 404 for non-bootstrap jobs — treated as "no distribution to show".
          const b = await getBootstrapDistribution(jobId);
          if (!cancelled) setBootstrap(b);
        } catch {
          if (!cancelled) setBootstrap(null);
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
      <div className="step-placeholder results-step">
        <div className="results-spinner" aria-hidden="true" />
        <p className="results-loading">Loading results&hellip;</p>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="step-placeholder results-step">
        <h2>Results</h2>
        <p className="results-error">Could not load the evaluation results.</p>
        <div className="results-actions">
          <button type="button" className="button-primary" onClick={onReset}>
            Start Over
          </button>
        </div>
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
  const headline = HEADLINE_METRICS
    .map((name) => ({ name, value: metricValue(name) }))
    .filter((h) => h.value !== null);

  return (
    <div className="step-placeholder results-step">
      <header className="results-header">
        <h2>Evaluation Results</h2>
        <p className="results-subtitle">
          Job #{jobId}
          {candidates.length > 0 && ` · ${candidates.join(', ')}`}
        </p>
      </header>

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
          <div className="results-panel-title">All metrics</div>
          <table className="results-table">
            <thead>
              <tr>
                <th>Metric</th>
                {candidates.map((c) => (
                  <th key={c} className="num">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metrics.metrics.map((row) => (
                <tr key={row.metric}>
                  <td>{row.metric}</td>
                  {candidates.map((c) => (
                    <td key={c} className="num">{formatValue(row.values[c] ?? null)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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

      <div className="results-panel">
        <div className="results-downloadall">
          <div className="results-downloadall-text">
            <div className="results-panel-title results-downloadall-title">Download results</div>
            <span className="results-downloadall-hint">All output files bundled into one ZIP.</span>
          </div>
          <a className="button-primary results-download-all" href={downloadAllUrl(jobId)}>
            Download Results (.zip)
          </a>
        </div>
        <div className="results-panel-title">Individual files</div>
        <ul className="results-files">
          {outputs.map((f) => (
            <li className="results-file" key={f.key}>
              <span className="results-file-name">{f.name}</span>
              <a
                className="results-download-link"
                href={downloadUrl(jobId, f.key)}
                download
              >
                Download
              </a>
            </li>
          ))}
        </ul>
      </div>

      <div className="results-actions">
        <button type="button" className="button-primary" onClick={onReset}>
          Start New Evaluation
        </button>
      </div>
    </div>
  );
}

export default ResultsStep;
