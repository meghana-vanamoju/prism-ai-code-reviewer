import type { Severity } from '../types/review';

interface SeverityBadgeProps {
  severity: Severity;
}

const severityColors: Record<Severity, string> = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#d97706',
  low: '#65a30d',
  suggestion: '#2563eb',
};

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const color = severityColors[severity];
  return (
    <span
      className="severity-badge"
      style={{ backgroundColor: color }}
    >
      {severity.toUpperCase()}
    </span>
  );
}