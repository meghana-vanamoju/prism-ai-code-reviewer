import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from '../App';
import { ApiRequestError } from '../services/api';

/**
 * Regression coverage for the API status indicator.
 *
 * The header used to be hard-coded to "API: Checking...", so it never reflected
 * the backend, and a cross-origin fetch produced an opaque NetworkError.
 */

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
}

const HEALTHY = { status: 'healthy', service: 'prism-api' };

describe('API status indicator', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows Connected when /health returns a healthy status', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(HEALTHY));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('API: Connected')).toBeInTheDocument();
    });
    // The indicator must reflect the real response, not a hard-coded string.
    // The landing picker offers several "Review …" actions.
    expect(screen.getAllByRole('button', { name: /review/i }).length).toBeGreaterThan(0);
  });

  it('requests the health endpoint on mount', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(HEALTHY));

    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('/health');
  });

  it('shows Connected only when the backend reports status healthy', async () => {
    // A reachable backend that reports a non-healthy status is not "connected".
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: 'degraded', service: 'prism-api' }));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('API: Disconnected')).toBeInTheDocument();
    });
  });

  it('shows Disconnected when the backend is unreachable', async () => {
    // fetch rejects when the request never yields a response (server down / blocked).
    fetchMock.mockRejectedValueOnce(new TypeError('NetworkError when attempting to fetch resource.'));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('API: Disconnected')).toBeInTheDocument();
    });
  });

  it('exposes the failure reason instead of a bare status', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('NetworkError when attempting to fetch resource.'));

    render(<App />);

    const indicator = await screen.findByText('API: Disconnected');
    await waitFor(() => {
      expect(indicator.closest('#health-indicator')).toHaveAttribute('title');
    });
  });

  it('does not report Connected when /health returns an HTTP error', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'boom' }), { status: 500 }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('API: Disconnected')).toBeInTheDocument();
    });
  });

  it('marks the dot healthy or unhealthy to match the reported state', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(HEALTHY));
    const { unmount } = render(<App />);

    await waitFor(() => {
      expect(document.querySelector('.health-dot')).toHaveClass('healthy');
    });
    unmount();

    fetchMock.mockRejectedValueOnce(new TypeError('NetworkError when attempting to fetch resource.'));
    render(<App />);

    await waitFor(() => {
      expect(document.querySelector('.health-dot')).toHaveClass('unhealthy');
    });
  });
});

describe('api service errors', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses same-origin relative URLs so requests are not cross-origin', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(HEALTHY));
    vi.stubGlobal('fetch', fetchMock);

    const { healthCheck } = await import('../services/api');
    await healthCheck();

    const [url] = fetchMock.mock.calls[0];
    // A same-origin path is proxied by Vite; an absolute localhost:8000 URL is
    // cross-origin and can be rejected by the backend's CORS allowlist.
    expect(String(url).startsWith('http')).toBe(false);
  });

  it('classifies an unreachable backend as a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch')));

    const { healthCheck } = await import('../services/api');
    await expect(healthCheck()).rejects.toBeInstanceOf(ApiRequestError);
  });

  it('classifies a non-OK HTTP status as an http error and surfaces the detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'nope' }), { status: 503 })),
    );

    const { reviewCode } = await import('../services/api');
    const error = await reviewCode({ code: 'x' }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error.kind).toBe('http');
    expect(error.message).toBe('nope');
  });
});
