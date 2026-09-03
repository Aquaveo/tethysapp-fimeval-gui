// reactapp/src/bootstrapMetrics.ts
// The whole-domain EvaluationMetrics.csv and the bootstrap sampling CSVs name a
// few metrics differently (e.g. "Acc" vs "Accuracy"), so a naive lookup left the
// median column blank for those rows (FE53). Normalize names so the bootstrap
// median lines up with its whole-domain metric row.
import type { BootstrapStats } from './api';

const METRIC_ALIASES: Record<string, string> = {
  acc: 'accuracy',
  accuracy: 'accuracy',
};

export function normalizeMetric(name: string): string {
  const n = name.trim().toLowerCase();
  return METRIC_ALIASES[n] ?? n;
}

// Median of the bootstrap distribution for a whole-domain metric row + candidate,
// or null if that metric wasn't part of the bootstrap (no median to show).
export function bootstrapMedian(
  bootstrap: BootstrapStats | null,
  metric: string,
  candidate: string,
): number | null {
  const stats = bootstrap?.stats?.[candidate];
  if (!stats) return null;
  const target = normalizeMetric(metric);
  for (const [key, stat] of Object.entries(stats)) {
    if (normalizeMetric(key) === target) return stat.median ?? null;
  }
  return null;
}
