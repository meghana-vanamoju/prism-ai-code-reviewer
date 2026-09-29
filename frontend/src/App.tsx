import { useState } from 'react';
import { CodeEditor } from './components/CodeEditor';
import { SummaryPanel } from './components/SummaryPanel';
import { IssuesPanel } from './components/IssuesPanel';
import { MemoriesPanel } from './components/MemoriesPanel';
import { reviewCode, submitFeedback } from './services/api';
import type { ReviewResponse, IssueFeedback } from './types/review';
import './App.css';

function App() {
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);

  const handleReview = async (request: { code: string; language?: string; query?: string }) => {
    setIsLoading(true);
    setError(null);
    setReview(null);
    try {
      const result = await reviewCode(request);
      setReview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review failed');
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
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : 'Failed to store feedback');
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
        <div className="health-indicator" id="health-indicator">
          <span className="health-dot"></span>
          <span>API: Checking...</span>
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