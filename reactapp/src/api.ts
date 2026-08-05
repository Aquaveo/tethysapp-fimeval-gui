// reactapp/src/api.ts
const API_BASE = '/apps/fimeval-gui/api';

export interface UploadResult {
  upload_id: string;
  benchmark_key: string;
  candidate_keys: string[];
}

export interface SubmitResult {
  job_id: number;
  status: string;
}

export function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function ensureCsrf(): Promise<void> {
  try {
    await fetch(`${API_BASE}/csrf/`, { credentials: 'same-origin' });
  } catch (e) {
    // best effort — a later POST surfaces any real problem, but log so a
    // failed seeding isn't invisible if a later request 403s.
    console.warn('CSRF cookie seeding failed:', e);
  }
}

async function parseError(response: Response): Promise<never> {
  // 403 with a non-JSON body is Django's CSRF failure page; anything else
  // non-JSON keeps a generic message with the status for context.
  let message =
    response.status === 403
      ? 'Session problem (HTTP 403) — please refresh the page and try again'
      : `Request failed (HTTP ${response.status})`;
  try {
    const body = await response.json();
    if (body && typeof body.error === 'string') message = body.error;
  } catch {
    // non-JSON response; keep the generic message
  }
  throw new Error(message);
}

async function csrfToken(): Promise<string> {
  // Self-healing: the page-load seeding in ensureCsrf() runs only once, so if
  // it failed (e.g. the server was down when the tab loaded) every later POST
  // would 403. Re-seed on demand instead of sending a doomed request.
  if (!getCsrfToken()) await ensureCsrf();
  return getCsrfToken();
}

export async function uploadFiles(
  benchmark: File,
  candidates: File[],
  boundary: File[] = [],
): Promise<UploadResult> {
  const form = new FormData();
  form.append('benchmark', benchmark);
  candidates.forEach((file) => form.append('candidates', file));
  boundary.forEach((file) => form.append('boundary', file));

  const response = await fetch(`${API_BASE}/upload/`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': await csrfToken() },
    body: form,
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export interface PresignTarget {
  field: 'benchmark' | 'candidate' | 'boundary';
  filename: string;
  key: string;
  url: string;
}

export interface PresignResult {
  upload_id: string;
  targets: PresignTarget[];
}

// Ask the server for a fresh upload_id + a presigned PUT URL per file. Only the
// filenames travel to Django here; the bytes go straight to MinIO via putFile().
export async function presignUpload(
  benchmark: File,
  candidates: File[],
  boundary: File[] = [],
): Promise<PresignResult> {
  const response = await fetch(`${API_BASE}/upload/presign/`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': await csrfToken(),
    },
    body: JSON.stringify({
      benchmark: benchmark.name,
      candidates: candidates.map((f) => f.name),
      boundary: boundary.map((f) => f.name),
    }),
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

// Upload one file directly to its presigned MinIO URL. Uses XMLHttpRequest (not
// fetch) because only XHR exposes upload progress events. No CSRF header — this
// request goes to MinIO, not Django.
export function putFile(
  url: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve();
      } else {
        reject(new Error(`Upload of ${file.name} failed (HTTP ${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error(`Upload of ${file.name} failed (network error)`));
    xhr.send(file);
  });
}

export async function submitJob(
  uploadId: string,
  method: string,
): Promise<SubmitResult> {
  const response = await fetch(`${API_BASE}/jobs/`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': await csrfToken(),
    },
    body: JSON.stringify({ upload_id: uploadId, method }),
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export interface JobStatus {
  job_id: number;
  status: 'submitted' | 'queued' | 'running' | 'complete' | 'error';
  created: string | null;
  completed: string | null;
  method: string | null;
  upload_id: string | null;
  reason: string | null;
}

export async function getJobStatus(jobId: number): Promise<JobStatus> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export interface OutputFile {
  name: string;
  key: string;
}

export interface JobOutputs {
  job_id: number;
  files: OutputFile[];
}

export interface MetricRow {
  metric: string;
  values: Record<string, number | null>;
}

export interface JobMetrics {
  job_id: number;
  candidates: string[];
  metrics: MetricRow[];
}

export async function getJobOutputs(jobId: number): Promise<JobOutputs> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/outputs/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export async function getJobMetrics(jobId: number): Promise<JobMetrics> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/metrics/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

export interface BoxStat {
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  outliers: number[];
  n: number;
}

export interface BootstrapStats {
  job_id: number;
  candidates: string[];
  metrics: string[];
  stats: Record<string, Record<string, BoxStat>>;
}

// Resolves only for bootstrap jobs; other methods return 404 (caller treats
// that as "no distribution to show").
export async function getBootstrapDistribution(jobId: number): Promise<BootstrapStats> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/bootstrap/`, {
    credentials: 'same-origin',
  });
  if (!response.ok) return parseError(response);
  return response.json();
}

// Anchor href target. The browser follows the 303 -> presigned MinIO URL as a
// navigation/download, so no CORS is involved (unlike reading the body in JS).
export function downloadUrl(jobId: number, key: string): string {
  return `${API_BASE}/jobs/${jobId}/download/?file=${encodeURIComponent(key)}`;
}

export function downloadAllUrl(jobId: number): string {
  return `${API_BASE}/jobs/${jobId}/download-all/`;
}
