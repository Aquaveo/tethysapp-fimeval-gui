import { describe, it, expect } from 'vitest';
import { bootstrapMedian, isCountClass, normalizeMetric, plotMetrics } from './bootstrapMetrics';
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

// A run whose CSV uses "Precision"/"Sensitivity", to exercise the whole-domain
// aliases (Prec, sen/TPR/POD).
const boot2: BootstrapStats = {
  job_id: 2,
  candidates: ['cand_0'],
  metrics: ['Precision', 'Sensitivity'],
  stats: { cand_0: { Precision: stat(0.6), Sensitivity: stat(0.5) } },
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

describe('bootstrapMedian — whole-domain name aliases (PR #18)', () => {
  it('maps whole-domain "Prec" to bootstrap "Precision"', () => {
    expect(bootstrapMedian(boot2, 'Prec', 'cand_0')).toBe(0.6);
  });

  it('maps "sen" / "TPR" / "POD" to bootstrap "Sensitivity" (same metric)', () => {
    expect(bootstrapMedian(boot2, 'sen', 'cand_0')).toBe(0.5);
    expect(bootstrapMedian(boot2, 'TPR', 'cand_0')).toBe(0.5);
    expect(bootstrapMedian(boot2, 'POD', 'cand_0')).toBe(0.5);
  });
});

describe('normalizeMetric', () => {
  it('aliases Acc → accuracy', () => {
    expect(normalizeMetric('Acc')).toBe('accuracy');
    expect(normalizeMetric('Accuracy')).toBe('accuracy');
  });

  it('collapses Prec / Precision → precision', () => {
    expect(normalizeMetric('Prec')).toBe('precision');
    expect(normalizeMetric('Precision')).toBe('precision');
  });

  it('collapses TPR / POD / sen / Sensitivity / Recall → sensitivity', () => {
    for (const n of ['TPR', 'POD', 'sen', 'Sensitivity', 'Recall']) {
      expect(normalizeMetric(n)).toBe('sensitivity');
    }
  });
});

// FE60: the raw count classes (TP/FP/FN/TN) are on a pixel-count scale and
// swamp the score metrics in the box plots, so they are dropped from the plots
// only. The medians table keeps every column (BE46).
describe('plotMetrics (FE60)', () => {
  it('drops TP, FP, FN and TN and keeps the scores in CSV order', () => {
    expect(plotMetrics(['TP', 'FP', 'FN', 'TN', 'CSI', 'POD', 'Accuracy', 'F1']))
      .toEqual(['CSI', 'POD', 'Accuracy', 'F1']);
  });

  it('is case-insensitive about the count-class names', () => {
    expect(plotMetrics(['tp', 'Fp', 'fN', 'tn', 'MCC'])).toEqual(['MCC']);
  });

  it('also drops the spelled-out count names', () => {
    expect(plotMetrics(['True Positive', 'False Negative', 'Kappa'])).toEqual(['Kappa']);
  });

  it('leaves a list with no count classes untouched', () => {
    expect(plotMetrics(['CSI', 'FAR'])).toEqual(['CSI', 'FAR']);
  });

  it('returns an empty list when only counts were bootstrapped', () => {
    expect(plotMetrics(['TP', 'TN'])).toEqual([]);
  });
});

describe('isCountClass', () => {
  it('recognises the four count classes and nothing else', () => {
    for (const n of ['TP', 'FP', 'FN', 'TN', 'true negative', 'False Positive']) {
      expect(isCountClass(n)).toBe(true);
    }
    for (const n of ['CSI', 'FNR', 'FAR', 'TPR', 'POD']) {
      expect(isCountClass(n)).toBe(false);
    }
  });
});
