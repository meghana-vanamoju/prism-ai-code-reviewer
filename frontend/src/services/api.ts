import type { ReviewRequest, ReviewResponse, ReviewFeedbackRequest, ReviewFeedbackResponse } from '../types/review';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function reviewCode(request: ReviewRequest): Promise<ReviewResponse> {
  const response = await fetch(`${API_BASE}/api/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<ReviewResponse>(response);
}

export async function submitFeedback(request: ReviewFeedbackRequest): Promise<ReviewFeedbackResponse> {
  const response = await fetch(`${API_BASE}/api/review/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<ReviewFeedbackResponse>(response);
}

export async function healthCheck(): Promise<{ status: string; service: string }> {
  const response = await fetch(`${API_BASE}/health`);
  return handleResponse(response);
}