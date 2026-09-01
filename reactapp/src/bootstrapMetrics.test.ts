import { describe, it, expect } from 'vitest';
import { bootstrapMedian, normalizeMetric } from './bootstrapMetrics';
import type { BootstrapStats, BoxStat } from './api';

const stat = (median: number): BoxStat => ({
  min: 0, q1: 0, median, q3: 0, max: 0, outliers: [], n: 5,
});

const boot: BootstrapStats = {
  job_id: 1,
  candidates: ['cand_0'],
  metrics: ['CSI', 'Accuracy'],
  stats: { cand_0: { CSI: stat(0.36), Accuracy: stat(0.91) } },
};

describe('bootstrapMedian (FE53)', () => {
  it('matches identical metric names', () => {
    expect(bootstrapMedian(boot, 'CSI', 'cand_0')).toBe(0.36);
  });

  it('maps whole-domain "Acc" to bootstrap "Accuracy"', () => {
    // The whole-domain EvaluationMetrics.csv row is "Acc"; bootstrap key is
    // "Accuracy" — the median must still resolve.
    expect(bootstrapMedian(boot, 'Acc', 'cand_0')).toBe(0.91);
  });

  it('is case-insensitive', () => {
    expect(bootstrapMedian(boot, 'csi', 'cand_0')).toBe(0.36);
  });

  it('returns null for a metric that was not bootstrapped', () => {
    expect(bootstrapMedian(boot, 'TN', 'cand_0')).toBeNull();
  });

  it('returns null when there is no bootstrap data', () => {
    expect(bootstrapMedian(null, 'CSI', 'cand_0')).toBeNull();
  });
});

describe('normalizeMetric', () => {
  it('aliases Acc → accuracy', () => {
    expect(normalizeMetric('Acc')).toBe('accuracy');
    expect(normalizeMetric('Accuracy')).toBe('accuracy');
  });
});
