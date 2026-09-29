import { useState } from 'react';
import type { Issue, IssueFeedback, IssueDecision } from '../types/review';
import { SeverityBadge } from './SeverityBadge';

interface IssuesPanelProps {
  issues: Issue[];
  onFeedback?: (feedback: IssueFeedback[]) => void;
}

export function IssuesPanel({ issues, onFeedback }: IssuesPanelProps) {
  if (issues.length === 0) {
    return (
      <div className="issues-panel empty">
        <div className="empty-state">
          <svg className="check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <p>No actionable issues found</p>
          <p className="empty-hint">
            PRISM found no issues requiring changes based on the current team standards and remembered decisions.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="issues-panel">
      <h3>Issues Found ({issues.length})</h3>
      <div className="issues-list">
        {issues.map((issue, index) => (
          <IssueCard key={`${issue.title}-${index}`} issue={issue} onFeedback={onFeedback} />
        ))}
      </div>
    </div>
  );
}

interface IssueCardProps {
  issue: Issue;
  onFeedback?: (feedback: IssueFeedback[]) => void;
}

function IssueCard({ issue, onFeedback }: IssueCardProps) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [decision, setDecision] = useState<IssueDecision | null>(null);
  const [reason, setReason] = useState('');

  const handleSubmitFeedback = () => {
    if (!onFeedback || !decision) return;
    onFeedback([
      {
        issue_title: issue.title,
        decision,
        reason: reason.trim() || undefined,
      },
    ]);
    setShowFeedback(false);
    setDecision(null);
    setReason('');
  };

  if (!onFeedback) {
    return (
      <div className="issue-card">
        <div className="issue-header">
          <SeverityBadge severity={issue.severity} />
          <h4>{issue.title}</h4>
        </div>
        <p className="issue-description">{issue.description}</p>
        <p className="issue-recommendation"><strong>Recommendation:</strong> {issue.recommendation}</p>
        {issue.memory_reference && (
          <p className="issue-memory-ref"><strong>Based on:</strong> {issue.memory_reference}</p>
        )}
      </div>
    );
  }

  return (
    <div className="issue-card">
      <div className="issue-header">
        <SeverityBadge severity={issue.severity} />
        <h4>{issue.title}</h4>
      </div>
      <p className="issue-description">{issue.description}</p>
      <p className="issue-recommendation"><strong>Recommendation:</strong> {issue.recommendation}</p>
      {issue.memory_reference && (
        <p className="issue-memory-ref"><strong>Based on:</strong> {issue.memory_reference}</p>
      )}

      <div className="feedback-section">
        <button
          type="button"
          className={`feedback-toggle ${showFeedback ? 'active' : ''}`}
          onClick={() => setShowFeedback(!showFeedback)}
        >
          {showFeedback ? 'Hide Feedback' : 'Provide Feedback'}
        </button>

        {showFeedback && (
          <div className="feedback-form">
            <div className="feedback-options">
              <label className={`decision-option ${decision === 'accepted' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name={`decision-${issue.title}`}
                  value="accepted"
                  checked={decision === 'accepted'}
                  onChange={() => setDecision('accepted')}
                />
                <span className="decision-label accepted">Accept</span>
              </label>
              <label className={`decision-option ${decision === 'rejected' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name={`decision-${issue.title}`}
                  value="rejected"
                  checked={decision === 'rejected'}
                  onChange={() => setDecision('rejected')}
                />
                <span className="decision-label rejected">Reject</span>
              </label>
            </div>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Optional: why did you accept or reject this?"
              rows={3}
              className="feedback-reason"
            />
            <button
              type="button"
              className="submit-feedback-btn"
              onClick={handleSubmitFeedback}
              disabled={!decision}
            >
              Submit Decision
            </button>
          </div>
        )}
      </div>
    </div>
  );
}