interface ScoreRingProps {
  score: number;
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--ok)';
  if (score >= 60) return 'var(--warn)';
  return 'var(--danger)';
}

export function ScoreRing({ score }: ScoreRingProps) {
  const radius = 53.5;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circumference - (clamped / 100) * circumference;
  const color = scoreColor(clamped);

  return (
    <div className="score-ring">
      <div className="score-ring-wrap">
        <svg viewBox="0 0 116 116" aria-hidden="true">
          <circle
            className="ring-track"
            cx="58"
            cy="58"
            r={radius}
            fill="none"
            strokeWidth="9"
          />
          <circle
            className="ring-value"
            cx="58"
            cy="58"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="score-ring-number">
          <span className="score-value">{clamped}</span>
          <span className="score-unit">/ 100</span>
        </div>
      </div>
      <span className="score-ring-label">Review score</span>
    </div>
  );
}
