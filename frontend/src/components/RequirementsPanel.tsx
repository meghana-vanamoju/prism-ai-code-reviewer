import type { RequirementItem, RequirementStatus, RequirementsReport } from '../types/review';

interface RequirementsPanelProps {
  report: RequirementsReport;
  onSelect?: (file: string, line?: number) => void;
}

const STATUS_LABEL: Record<RequirementStatus, string> = {
  implemented: 'Implemented',
  partial: 'Partial',
  missing: 'Missing',
};

const STATUS_TONE: Record<RequirementStatus, string> = {
  implemented: 'ok',
  partial: 'warn',
  missing: 'danger',
};

function parseEvidence(ref: string): { path: string; line?: number } | null {
  const match = /^(.*):(\d+)$/.exec(ref);
  if (!match) return null;
  return { path: match[1], line: Number(match[2]) };
}

export function RequirementsPanel({ report, onSelect }: RequirementsPanelProps) {
  const total = report.items.length;

  return (
    <div className="requirements-panel">
      <div className="panel-head">
        <span className="panel-eyebrow">Coverage</span>
        <h3>Requirements ({total})</h3>
      </div>

      <div className="req-coverage">
        <div className="req-coverage-track">
          <div className="req-coverage-fill" style={{ width: `${report.coverage_pct}%` }} />
        </div>
        <span className="req-coverage-pct">{report.coverage_pct}% covered</span>
      </div>

      <div className="req-stats">
        <span className="req-stat ok">
          <strong>{report.implemented}</strong> implemented
        </span>
        <span className="req-stat warn">
          <strong>{report.partial}</strong> partial
        </span>
        <span className="req-stat danger">
          <strong>{report.missing}</strong> missing
        </span>
      </div>

      {report.summary && <p className="req-summary">{report.summary}</p>}

      {total === 0 ? (
        <div className="empty-state req-empty">
          <p>No requirements were matched against this code.</p>
        </div>
      ) : (
        <ul className="req-list">
          {report.items.map((item, index) => (
            <RequirementRow
              key={`${item.id}-${index}`}
              item={item}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface RequirementRowProps {
  item: RequirementItem;
  onSelect?: (file: string, line?: number) => void;
}

function RequirementRow({ item, onSelect }: RequirementRowProps) {
  return (
    <li className="req-item">
      <div className="req-item-head">
        <span className={`req-status ${STATUS_TONE[item.status]}`}>
          {STATUS_LABEL[item.status]}
        </span>
        <span className="req-id">{item.id}</span>
        <span className="req-title">{item.title}</span>
        <span className="req-kind">{item.kind}</span>
      </div>

      {item.evidence.length > 0 && (
        <div className="req-evidence">
          <span className="req-evidence-label">Evidence</span>
          {item.evidence.map((ref, i) => {
            const parsed = parseEvidence(ref);
            if (parsed && onSelect) {
              return (
                <button
                  key={`${ref}-${i}`}
                  type="button"
                  className="req-evidence-btn"
                  onClick={() => onSelect(parsed.path, parsed.line)}
                  title="Jump to location"
                >
                  {parsed.line !== undefined ? `${parsed.path}:${parsed.line}` : parsed.path}
                </button>
              );
            }
            return (
              <span key={`${ref}-${i}`} className="req-evidence-text">
                {ref}
              </span>
            );
          })}
        </div>
      )}

      {item.gaps && (
        <p className="req-gaps">
          <strong>Gaps:</strong> {item.gaps}
        </p>
      )}
      {item.notes && <p className="req-notes">{item.notes}</p>}
    </li>
  );
}
