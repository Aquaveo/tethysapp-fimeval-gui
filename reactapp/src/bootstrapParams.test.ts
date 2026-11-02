import { describe, it, expect } from 'vitest';
import {
  DEFAULT_BOOTSTRAP_FORM,
  validateBootstrapForm,
  bootstrapSummary,
  formFromBootstrapParams,
  type BootstrapForm,
} from './bootstrapParams';

const form = (over: Partial<BootstrapForm> = {}): BootstrapForm => ({
  ...DEFAULT_BOOTSTRAP_FORM,
  ...over,
});

describe('validateBootstrapForm (FE36)', () => {
  it('defaults are valid and produce the backend defaults', () => {
    const r = validateBootstrapForm(form(), 'stratified');
    expect(r.errors).toEqual({});
    expect(r.payload).toEqual({
      n_iterations: 100, n_points: 500, spacing_range: [100, 1000], seed: null,
    });
  });

  it('parses user values, including a seed', () => {
    const r = validateBootstrapForm(
      form({ nIterations: '250', nPoints: '2000', seed: '42' }), 'random',
    );
    expect(r.errors).toEqual({});
    expect(r.payload).toEqual({
      n_iterations: 250, n_points: 2000, spacing_range: [100, 1000], seed: 42,
    });
  });

  it('rejects iterations outside 1..1000 and non-integers', () => {
    for (const bad of ['0', '1001', 'abc', '2.5', '']) {
      const r = validateBootstrapForm(form({ nIterations: bad }), 'stratified');
      expect(r.errors.nIterations, bad).toBeTruthy();
      expect(r.payload, bad).toBeNull();
    }
  });

  it('rejects points outside 1..50000', () => {
    for (const bad of ['0', '50001', 'x']) {
      const r = validateBootstrapForm(form({ nPoints: bad }), 'random');
      expect(r.errors.nPoints, bad).toBeTruthy();
    }
  });

  it('ignores a bad points value for systematic sampling (points are not used)', () => {
    const r = validateBootstrapForm(form({ nPoints: 'x' }), 'systematic');
    expect(r.errors.nPoints).toBeUndefined();
    expect(r.payload?.n_points).toBe(500); // falls back to the default
  });

  it('requires 0 < min < max for the spacing range, systematic only', () => {
    expect(validateBootstrapForm(form({ spacingMin: '1000', spacingMax: '100' }), 'systematic').errors.spacing).toBeTruthy();
    expect(validateBootstrapForm(form({ spacingMin: '0' }), 'systematic').errors.spacing).toBeTruthy();
    expect(validateBootstrapForm(form({ spacingMin: 'a' }), 'systematic').errors.spacing).toBeTruthy();
    // Non-systematic: spacing is not used, so a bad value does not block.
    const r = validateBootstrapForm(form({ spacingMin: 'a' }), 'stratified');
    expect(r.errors.spacing).toBeUndefined();
    expect(r.payload?.spacing_range).toEqual([100, 1000]);
  });

  it('accepts a decimal spacing range', () => {
    const r = validateBootstrapForm(form({ spacingMin: '12.5', spacingMax: '80' }), 'systematic');
    expect(r.errors).toEqual({});
    expect(r.payload?.spacing_range).toEqual([12.5, 80]);
  });

  it('seed must be an integer when given; blank means random', () => {
    expect(validateBootstrapForm(form({ seed: '1.5' }), 'random').errors.seed).toBeTruthy();
    expect(validateBootstrapForm(form({ seed: 'abc' }), 'random').errors.seed).toBeTruthy();
    expect(validateBootstrapForm(form({ seed: '  ' }), 'random').payload?.seed).toBeNull();
    expect(validateBootstrapForm(form({ seed: '-7' }), 'random').payload?.seed).toBe(-7);
  });
});

describe('bootstrapSummary (FE36)', () => {
  it('describes random/stratified runs by iterations and points', () => {
    expect(bootstrapSummary(
      { n_iterations: 100, n_points: 500, spacing_range: [100, 1000], seed: null }, 'stratified',
    )).toBe('100 iterations × 500 points, random seed');
  });

  it('describes systematic runs by spacing instead of points, and names the seed', () => {
    expect(bootstrapSummary(
      { n_iterations: 50, n_points: 500, spacing_range: [100, 1000], seed: 42 }, 'systematic',
    )).toBe('50 iterations, grid spacing 100–1000 m, seed 42');
  });

  it('returns null without params (pre-FE36 runs)', () => {
    expect(bootstrapSummary(null, 'random')).toBeNull();
  });
});

describe('formFromBootstrapParams (FE36 re-evaluate prefill)', () => {
  it('turns a run\'s stored params back into form strings', () => {
    expect(formFromBootstrapParams(
      { n_iterations: 250, n_points: 2000, spacing_range: [12.5, 80], seed: 42 },
    )).toEqual({ nIterations: '250', nPoints: '2000', spacingMin: '12.5', spacingMax: '80', seed: '42' });
  });

  it('keeps a null seed blank', () => {
    expect(formFromBootstrapParams(
      { n_iterations: 100, n_points: 500, spacing_range: [100, 1000], seed: null },
    ).seed).toBe('');
  });

  it('falls back to the defaults for runs without params', () => {
    expect(formFromBootstrapParams(null)).toEqual(DEFAULT_BOOTSTRAP_FORM);
    expect(formFromBootstrapParams(undefined)).toEqual(DEFAULT_BOOTSTRAP_FORM);
  });
});
