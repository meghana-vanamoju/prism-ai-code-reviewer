import type {
  ReviewRequest,
  ReviewResponse,
  ReviewFeedbackRequest,
  ReviewFeedbackResponse,
  HealthResponse,
} from '../types/review';
import type { BranchListResponse, JobRequest, JobResponse } from '../types/job';

// Default to a same-origin (relative) base URL so requests are proxied by the
// Vite dev/preview server (see vite.config.ts). This keeps the browser on one
// origin, so the backend's CORS allowlist is never involved.
// VITE_API_BASE remains supported as an explicit absolute-URL override.
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

const REQUEST_TIMEOUT_MS = 10_000;
// Branch listing shells out to `git ls-remote` on the remote, which can take
// considerably longer than a normal API round-trip on slow networks.
const BRANCH_TIMEOUT_MS = 60_000;

export type ApiErrorKind = 'network' | 'http';

/** Error carrying whether the request failed at the network layer or on an HTTP status. */
export class ApiRequestError extends Error {
  readonly kind: ApiErrorKind;

  constructor(message: string, kind: ApiErrorKind) {
    super(message);
    this.name = 'ApiRequestError';
    this.kind = kind;
  }
}

function describeBase(): string {
  if (API_BASE) return API_BASE;
  return typeof window === 'undefined' ? 'the API server' : window.location.origin;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiRequestError(error.detail || `HTTP ${response.status}`, 'http');
  }
  return response.json();
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
  } catch {
    // fetch only rejects when the request never produced a response: the server
    // is down, the host/port is wrong, or the response was blocked. Surface the
    // real cause instead of a generic failure.
    if (controller.signal.aborted) {
      throw new ApiRequestError(
        `Request to ${path} timed out after ${timeoutMs / 1000}s. Is the backend running?`,
        'network',
      );
    }
    throw new ApiRequestError(
      `Cannot reach the API at ${describeBase()}. Is the backend running?`,
      'network',
    );
  } finally {
    clearTimeout(timeoutId);
  }

  return handleResponse<T>(response);
}

export async function reviewCode(body: ReviewRequest): Promise<ReviewResponse> {
  return request<ReviewResponse>('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function submitFeedback(body: ReviewFeedbackRequest): Promise<ReviewFeedbackResponse> {
  return request<ReviewFeedbackResponse>('/api/review/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function healthCheck(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

/** Starts a paste or branch review job. Returns immediately with 202 + job id. */
export async function createJob(body: JobRequest): Promise<JobResponse> {
  return request<JobResponse>('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export interface UploadEntry {
  file: File;
  /** Relative path (e.g. webkitRelativePath) used as the server-side path. */
  path?: string;
}

/** Uploads files/folder entries and starts a review job. */
export async function uploadJob(
  entries: UploadEntry[],
  query?: string,
  requirements?: string,
): Promise<JobResponse> {
  const form = new FormData();
  for (const entry of entries) {
    // Passing the relative path as the filename preserves folder structure.
    form.append('files', entry.file, entry.path || entry.file.name);
  }
  if (query) form.append('query', query);
  if (requirements) form.append('requirements', requirements);
  // Do not set Content-Type: the browser must add the multipart boundary.
  return request<JobResponse>('/api/jobs/upload', { method: 'POST', body: form });
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
}

export async function listBranches(repoUrl: string): Promise<BranchListResponse> {
  const qs = new URLSearchParams({ repo_url: repoUrl });
  return request<BranchListResponse>(`/api/branches?${qs.toString()}`, undefined, BRANCH_TIMEOUT_MS);
}
