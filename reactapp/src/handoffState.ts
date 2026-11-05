// reactapp/src/handoffState.ts
// FE65: the FIMbench "Run in FIMeval" handoff (BE52) lands the SPA on
//   /?upload_id=<id>&from=fimbench&benchmark_name=<name>      (benchmark staged)
//   /?from=fimbench&error=<code>                               (staging failed)
// This parses that query once so the wizard can open with the benchmark
// pre-staged, or show why it isn't. Pure, so it is unit-tested directly.
export interface HandoffState {
  uploadId: string | null;   // staged upload to add candidates to
  name: string;              // display name of the staged benchmark
  error: string | null;      // human message when the handoff failed
}

const ERRORS: Record<string, string> = {
  bad_url: 'FIMbench sent a benchmark link that is not a .tif raster URL.',
  not_allowed_host: 'The benchmark link points at a host FIMeval is not allowed to fetch from.',
  too_large: 'The benchmark is larger than FIMeval accepts for an upload.',
  not_a_tiff: 'The file at the benchmark link is not a GeoTIFF.',
  unreachable: 'FIMeval could not download the benchmark from FIMbench.',
  storage: 'FIMeval could not store the benchmark; please try again.',
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseHandoff(search: string): HandoffState | null {
  const q = new URLSearchParams(search);
  if (q.get('from') !== 'fimbench') return null;
  const error = q.get('error');
  if (error) {
    return { uploadId: null, name: '', error: ERRORS[error] ?? `The handoff from FIMbench failed (${error}).` };
  }
  const uploadId = q.get('upload_id');
  if (!uploadId || !UUID.test(uploadId)) {
    return { uploadId: null, name: '', error: 'The handoff from FIMbench did not include a valid upload.' };
  }
  return { uploadId, name: (q.get('benchmark_name') || '').trim() || 'benchmark from FIMbench', error: null };
}
