import type { ReviewResponse } from '../types/review';

interface SummaryPanelProps {
  review: ReviewResponse;
}

export function SummaryPanel({ review }: SummaryPanelProps) {
  const issueCounts = review.issues.reduce((acc, issue) => {
    acc[issue.severity] = (acc[issue.severity] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const totalIssues = review.issues.length;

  return (
    <div className="summary-panel">
      <h3>Review Summary</h3>
      <p className="summary-text">{review.summary}</p>

      {totalIssues > 0 && (
        <div className="issue-breakdown">
          <span className="breakdown-label">Issues:</span>
          <div className="severity-counts">
            {(['critical', 'high', 'medium', 'low', 'suggestion'] as const).map((severity) => (
              issueCounts[severity] > 0 && (
                <span key={severity} className={`severity-count ${severity}`}>
                  {issueCounts[severity]} {severity}
                </span>
              )
            ))}
          </div>
        </div>
      )}

      {review.suggestions.length > 0 && (
        <div className="suggestions">
          <h4>General Suggestions</h4>
          <ul>
            {review.suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="model-info">
        Model: {review.model_used} | Memories used: {review.memories_used.length}
      </div>
    </div>
  );
}