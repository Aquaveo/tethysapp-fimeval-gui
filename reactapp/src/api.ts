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
  let message = 'Request failed';
  try {
    const body = await response.json();
    if (body && typeof body.error === 'string') message = body.error;
  } catch {
    // non-JSON response; keep the generic message
  }
  throw new Error(message);
}

export async function uploadFiles(
  benchmark: File,
  candidates: File[],
): Promise<UploadResult> {
  const form = new FormData();
  form.append('benchmark', benchmark);
  candidates.forEach((file) => form.append('candidates', file));

  const response = await fetch(`${API_BASE}/upload/`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': getCsrfToken() },
    body: form,
  });
  if (!response.ok) return parseError(response);
  return response.json();
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
      'X-CSRFToken': getCsrfToken(),
    },
    body: JSON.stringify({ upload_id: uploadId, method }),
  });
  if (!response.ok) return parseError(response);
  return response.json();
}
