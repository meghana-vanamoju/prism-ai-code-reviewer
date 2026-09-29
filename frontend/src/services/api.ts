import type {
  ReviewRequest,
  ReviewResponse,
  ReviewFeedbackRequest,
  ReviewFeedbackResponse,
  HealthResponse,
} from '../types/review';

// Default to a same-origin (relative) base URL so requests are proxied by the
// Vite dev/preview server (see vite.config.ts). This keeps the browser on one
// origin, so the backend's CORS allowlist is never involved.
// VITE_API_BASE remains supported as an explicit absolute-URL override.
const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

const REQUEST_TIMEOUT_MS = 10_000;

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, signal: controller.signal });
  } catch {
    // fetch only rejects when the request never produced a response: the server
    // is down, the host/port is wrong, or the response was blocked. Surface the
    // real cause instead of a generic failure.
    if (controller.signal.aborted) {
      throw new ApiRequestError(
        `Request to ${path} timed out after ${REQUEST_TIMEOUT_MS / 1000}s. Is the backend running?`,
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
