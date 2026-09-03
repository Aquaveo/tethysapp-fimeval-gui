// reactapp/src/WelcomeModal.tsx
// Welcome + file-guidelines modal (FE40). Gives a broad overview of what FIMeval
// does and what to upload before submitting a run. Shows on every load unless
// the user ticks "Don't show this on startup" (persisted by AppShell); it can be
// reopened from the nav's "Guidelines" link. Accessible: role=dialog, focus trap,
// Escape/backdrop close, focus restored to the trigger on close.
import { useEffect, useRef } from 'react';
import './WelcomeModal.css';

type Props = {
  open: boolean;
  onClose: () => void;
  dontShow: boolean;
  onDontShowChange: (value: boolean) => void;
};

export default function WelcomeModal({ open, onClose, dontShow, onDontShowChange }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    // Remember what had focus so we can restore it when the modal closes.
    lastFocused.current = document.activeElement as HTMLElement | null;
    closeBtnRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusables || focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      lastFocused.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="wk-welcome-backdrop" onClick={onClose}>
      <div
        className="wk-welcome"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wk-welcome-title"
        ref={dialogRef}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="wk-welcome-header">
          <div>
            <h2 id="wk-welcome-title" className="wk-welcome-title">Welcome to FIMeval</h2>
            <p className="wk-welcome-tagline">Evaluate candidate flood maps against benchmarks</p>
          </div>
          <button
            type="button"
            className="wk-welcome-x"
            aria-label="Close"
            ref={closeBtnRef}
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="wk-welcome-body">
          <p className="wk-welcome-lead">
            FIMeval compares a <strong>candidate</strong> flood-inundation map against a
            trusted <strong>benchmark</strong> and reports how well they agree — accuracy
            metrics (CSI, POD, FAR…) plus an interactive contingency map showing where the
            two match and differ.
          </p>

          <div className="wk-welcome-alpha" role="note">
            <strong>Alpha — lightweight version.</strong> This build is for testing and is
            sized for moderate inputs. For large case studies or the full feature set, use the{' '}
            <a href="https://github.com/sdmlua/fimeval" target="_blank" rel="noopener noreferrer">
              full FIMeval package
            </a>.
          </div>

          <h3 className="wk-welcome-h3">Before you start</h3>
          <ul className="wk-welcome-list">
            <li>
              <strong>Rasters:</strong> GeoTIFF (<code>.tif</code>/<code>.tiff</code>) — one
              benchmark and one or more candidates.
            </li>
            <li>
              <strong>File size:</strong> up to <strong>2&nbsp;GB</strong> per file.
            </li>
            <li>
              <strong>Resolution:</strong> inputs are aligned to the coarsest one, so a coarse
              candidate downsamples a fine benchmark. Very large, high-resolution inputs may be
              offered a coarser run.
            </li>
            <li>
              <strong>Projection:</strong> inputs are automatically reprojected to{' '}
              <strong>EPSG:5070</strong> (CONUS Albers) — mixed CRSs are fine.
            </li>
            <li>
              <strong>Area of Interest (optional):</strong> to limit the evaluation, add a
              boundary shapefile with all parts (<code>.shp</code>, <code>.shx</code>,{' '}
              <code>.dbf</code>, <code>.prj</code>…).
            </li>
          </ul>

          <div className="wk-welcome-actions">
            <label className="wk-welcome-check">
              <input
                type="checkbox"
                checked={dontShow}
                onChange={(e) => onDontShowChange(e.target.checked)}
              />
              Don&rsquo;t show this on startup
            </label>
            <button type="button" className="button-primary" onClick={onClose}>Got it</button>
          </div>
        </div>
      </div>
    </div>
  );
}
