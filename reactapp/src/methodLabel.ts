// reactapp/src/methodLabel.ts
// Shared human labels for evaluation methods + bootstrap sub-methods, so the Runs
// list and a run's detail header read the same. Bootstrap runs append the sampling
// sub-method in brackets — "Bootstrap (Systematic)" — so a run is identifiable at a
// glance without remembering which sampling was chosen (handy when re-evaluating).
const METHOD_LABELS: Record<string, string> = {
  smallest_extent: 'Smallest extent',
  convex_hull: 'Convex hull',
  intersected_extent: 'Intersected extent',
  bootstrap: 'Bootstrap',
  AOI: 'AOI',
};

const SUB_METHOD_LABELS: Record<string, string> = {
  random: 'Random',
  systematic: 'Systematic',
  stratified: 'Stratified',
};

export function methodLabel(
  method: string | null | undefined,
  subMethod?: string | null,
): string {
  if (!method) return '—';
  const base = METHOD_LABELS[method] ?? method;
  if (method === 'bootstrap' && subMethod) {
    return `${base} (${SUB_METHOD_LABELS[subMethod] ?? subMethod})`;
  }
  return base;
}
