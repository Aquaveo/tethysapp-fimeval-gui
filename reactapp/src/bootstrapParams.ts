// reactapp/src/bootstrapParams.ts
// FE36: advanced bootstrap parameters — form state, validation and a one-line
// summary. Pure (no React) so it is unit-testable and shared by the wizard's
// review step and the run detail header. Caps mirror the backend's
// MAX_N_ITERATIONS / MAX_N_POINTS so the server never rejects what we send.

export type SubMethod = 'random' | 'stratified' | 'systematic';

/** What the wizard holds while the user types (strings, never coerced). */
export interface BootstrapForm {
  nIterations: string;
  nPoints: string;
  spacingMin: string;
  spacingMax: string;
  seed: string;
}

/** What goes on the wire and comes back on a job (keys mirror fimeval). */
export interface BootstrapParams {
  n_iterations: number;
  n_points: number;
  spacing_range: [number, number];
  seed: number | null;
}

export const MAX_N_ITERATIONS = 1000;
export const MAX_N_POINTS = 50000;

export const DEFAULT_BOOTSTRAP_PARAMS: BootstrapParams = {
  n_iterations: 100,
  n_points: 500,
  spacing_range: [100, 1000],
  seed: null,
};

export const DEFAULT_BOOTSTRAP_FORM: BootstrapForm = {
  nIterations: '100',
  nPoints: '500',
  spacingMin: '100',
  spacingMax: '1000',
  seed: '',
};

export type BootstrapFormErrors = Partial<Record<'nIterations' | 'nPoints' | 'spacing' | 'seed', string>>;

function parseInteger(raw: string): number | null {
  const s = raw.trim();
  return /^-?\d+$/.test(s) ? Number(s) : null;
}

function parseNumber(raw: string): number | null {
  const s = raw.trim();
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/**
 * Validate the form for the chosen sampling approach. Fields the approach does
 * not use (points for systematic; spacing for the others) are not validated and
 * fall back to the defaults in the payload, so a stale value never blocks Next.
 */
export function validateBootstrapForm(
  form: BootstrapForm,
  subMethod: SubMethod,
): { errors: BootstrapFormErrors; payload: BootstrapParams | null } {
  const errors: BootstrapFormErrors = {};
  const payload: BootstrapParams = { ...DEFAULT_BOOTSTRAP_PARAMS };
  const systematic = subMethod === 'systematic';

  const iters = parseInteger(form.nIterations);
  if (iters === null || iters < 1 || iters > MAX_N_ITERATIONS) {
    errors.nIterations = `Iterations must be a whole number from 1 to ${MAX_N_ITERATIONS}.`;
  } else {
    payload.n_iterations = iters;
  }

  if (!systematic) {
    const pts = parseInteger(form.nPoints);
    if (pts === null || pts < 1 || pts > MAX_N_POINTS) {
      errors.nPoints = `Points per iteration must be a whole number from 1 to ${MAX_N_POINTS.toLocaleString()}.`;
    } else {
      payload.n_points = pts;
    }
  }

  if (systematic) {
    const min = parseNumber(form.spacingMin);
    const max = parseNumber(form.spacingMax);
    if (min === null || max === null || min <= 0 || min >= max) {
      errors.spacing = 'Spacing range needs 0 < min < max, in metres.';
    } else {
      payload.spacing_range = [min, max];
    }
  }

  if (form.seed.trim() !== '') {
    const seed = parseInteger(form.seed);
    if (seed === null) {
      errors.seed = 'Seed must be a whole number, or blank for a random seed.';
    } else {
      payload.seed = seed;
    }
  }

  return { errors, payload: Object.keys(errors).length ? null : payload };
}

/** One line for the review step and run detail, e.g. "100 iterations × 500 points, seed 42". */
export function bootstrapSummary(
  params: BootstrapParams | null | undefined,
  subMethod: string | null | undefined,
): string | null {
  if (!params) return null;
  const seed = params.seed === null || params.seed === undefined ? 'random seed' : `seed ${params.seed}`;
  if (subMethod === 'systematic') {
    const [min, max] = params.spacing_range;
    return `${params.n_iterations} iterations, grid spacing ${min}–${max} m, ${seed}`;
  }
  return `${params.n_iterations} iterations × ${params.n_points} points, ${seed}`;
}

/** Re-evaluate (FE41): seed the wizard form from a run's stored params. */
export function formFromBootstrapParams(
  params: BootstrapParams | null | undefined,
): BootstrapForm {
  if (!params) return DEFAULT_BOOTSTRAP_FORM;
  return {
    nIterations: String(params.n_iterations),
    nPoints: String(params.n_points),
    spacingMin: String(params.spacing_range[0]),
    spacingMax: String(params.spacing_range[1]),
    seed: params.seed === null || params.seed === undefined ? '' : String(params.seed),
  };
}
