import { useCallback, useEffect, useState } from 'react';
import { CodeEditor } from './components/CodeEditor';
import { SummaryPanel } from './components/SummaryPanel';
import { IssuesPanel } from './components/IssuesPanel';
import { MemoriesPanel } from './components/MemoriesPanel';
import { reviewCode, submitFeedback, healthCheck } from './services/api';
import type { ReviewResponse, IssueFeedback } from './types/review';
import './App.css';

type ApiStatus = 'checking' | 'connected' | 'disconnected';

const API_STATUS_LABEL: Record<ApiStatus, string> = {
  checking: 'API: Checking...',
  connected: 'API: Connected',
  disconnected: 'API: Disconnected',
};

const API_STATUS_DOT: Record<ApiStatus, string> = {
  checking: '',
  connected: 'healthy',
  disconnected: 'unhealthy',
};

function App() {
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking');
  const [apiDetail, setApiDetail] = useState<string | null>(null);

  // Reports the real outcome of GET /health: connected only when the backend
  // answers with a healthy status, disconnected when it is unreachable or
  // reports a non-healthy status.
  const runHealthCheck = useCallback(async () => {
    try {
      const health = await healthCheck();
      if (health.status === 'healthy') {
        setApiStatus('connected');
        setApiDetail(health.service);
      } else {
        setApiStatus('disconnected');
        setApiDetail(`Unexpected status: ${health.status}`);
      }
    } catch (err) {
      setApiStatus('disconnected');
      setApiDetail(err instanceof Error ? err.message : 'Health check failed');
    }
  }, []);

  // Re-runs the check after a failed request, showing the pending state first.
  const refreshApiHealth = useCallback(() => {
    setApiStatus('checking');
    return runHealthCheck();
  }, [runHealthCheck]);

  useEffect(() => {
    // Initial state is already "checking", so this only starts the request.
    // runHealthCheck is async, so no state updates happen synchronously here.
    // oxlint-disable-next-line react/set-state-in-effect
    void runHealthCheck();
  }, [runHealthCheck]);

  const handleReview = async (request: { code: string; language?: string; query?: string }) => {
    setIsLoading(true);
    setError(null);
    setReview(null);
    try {
      const result = await reviewCode(request);
      setReview(result);
      // The request succeeded, so the API is reachable.
      setApiStatus('connected');
      setApiDetail(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review failed');
      void refreshApiHealth();
    } finally {
      setIsLoading(false);
    }
  };

  const handleFeedback = async (issueFeedback: IssueFeedback[]) => {
    if (!review) return;
    setFeedbackError(null);
    setFeedbackSuccess(null);
    try {
      await submitFeedback({
        code: '',
        review_summary: review.summary,
        issues: review.issues,
        issue_feedback: issueFeedback,
      });
      setFeedbackSuccess('Feedback stored in Hindsight — future reviews will recall this decision');
      // Clear after 5 seconds
      setTimeout(() => setFeedbackSuccess(null), 5000);
      setApiStatus('connected');
      setApiDetail(null);
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : 'Failed to store feedback');
      void refreshApiHealth();
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <div className="logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2a8 8 0 0 0-8 8c0 4.4 4 8 8 8s8-3.6 8-8a8 8 0 0 0-8-8z" />
              <path d="M12 6v4" />
              <path d="M12 14v4" />
              <path d="M8 10h8" />
              <path d="M8 14h8" />
            </svg>
            <span>PRISM</span>
          </div>
          <p className="tagline">Persistent Review Intelligence & Standards Memory</p>
        </div>
        <div
          className="health-indicator"
          id="health-indicator"
          data-status={apiStatus}
          title={apiDetail ?? undefined}
        >
          <span className={`health-dot ${API_STATUS_DOT[apiStatus]}`.trim()}></span>
          <span>{API_STATUS_LABEL[apiStatus]}</span>
        </div>
      </header>

      <main className="app-main">
        <div className="layout">
          <section className="input-section">
            <CodeEditor
              onSubmit={handleReview}
              isLoading={isLoading}
              defaultCode={`function calculateTotal(items) {
  let total = 0;
  for (const item of items) {
    total += item.price;
  }
  return total;
}`}
            />
            {error && <div className="error-banner">{error}</div>}
          </section>

          {review && (
            <section className="results-section">
              <SummaryPanel review={review} />
              <IssuesPanel issues={review.issues} onFeedback={handleFeedback} />
              <MemoriesPanel memories={review.memories_used} />
              {(feedbackSuccess || feedbackError) && (
                <div className="feedback-status">
                  {feedbackSuccess && <div className="success-toast">{feedbackSuccess}</div>}
                  {feedbackError && <div className="error-toast">{feedbackError}</div>}
                </div>
              )}
            </section>
          )}

          {!review && !isLoading && (
            <section className="results-section empty">
              <div className="empty-results">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 2a8 8 0 0 0-8 8c0 4.4 4 8 8 8s8-3.6 8-8a8 8 0 0 0-8-8z" />
                  <path d="M12 6v4" />
                  <path d="M12 14v4" />
                  <path d="M8 10h8" />
                  <path d="M8 14h8" />
                </svg>
                <p>Submit code for review to see results</p>
                <p className="hint">Hindsight memories will appear here when relevant</p>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;