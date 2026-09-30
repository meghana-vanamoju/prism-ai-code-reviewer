import type { JobResponse, SourceMode } from '../types/job';

interface ProgressViewProps {
  job: JobResponse;
  onCancel: () => void;
  cancelling: boolean;
}

interface ProgressStep {
  status: string;
  label: string;
  hint: string;
}

const BASE_STEPS: ProgressStep[] = [
  { status: 'queued', label: 'Queued', hint: 'Review job accepted' },
  { status: 'fetching', label: 'Preparing source', hint: 'Reading files or fetching the branch' },
  { status: 'recalling', label: 'Recalling team memories', hint: 'Loading remembered decisions' },
  { status: 'reviewing', label: 'Reviewing files', hint: 'Line-level analysis in progress' },
];

const REQUIREMENTS_STEP: ProgressStep = {
  status: 'requirements',
  label: 'Checking requirements',
  hint: 'Mapping requirements to code',
};

const STEP_ALIASES: Record<string, string> = {
  queued: 'queued',
  fetching: 'fetching',
  fetch: 'fetching',
  recalling: 'recalling',
  recall: 'recalling',
  reviewing: 'reviewing',
  aggregate: 'reviewing',
  requirements: 'requirements',
  'checking requirements': 'requirements',
  checking: 'requirements',
};

function stepsFor(mode: SourceMode): ProgressStep[] {
  return mode === 'requirements' ? [...BASE_STEPS, REQUIREMENTS_STEP] : BASE_STEPS;
}

function stageOf(job: JobResponse): number {
  const steps = stepsFor(job.mode);
  const aliased = STEP_ALIASES[job.progress.step] ?? job.status;
  const idx = steps.findIndex((step) => step.status === aliased);
  return idx === -1 ? 0 : idx;
}

export function ProgressView({ job, onCancel, cancelling }: ProgressViewProps) {
  const steps = stepsFor(job.mode);
  const stage = stageOf(job);
  const { current, total, current_file: currentFile } = job.progress;
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;

  return (
    <div className="progress-panel">
      <div className="progress-title">
        <div className="progress-heading">
          <span className="panel-eyebrow">Working</span>
          <h2>Review in progress</h2>
        </div>
        <span className="mode-chip">{job.mode} mode</span>
      </div>

      <ol className="progress-steps">
        {steps.map((step, index) => {
          const state = index < stage ? 'done' : index === stage ? 'active' : '';
          return (
            <li key={step.status} className={`progress-step ${state}`.trim()}>
              <span className="step-dot">{state === 'done' ? '✓' : index + 1}</span>
              <span className="step-copy">
                <span className="step-label">{step.label}</span>
                <span className="step-hint">{step.hint}</span>
              </span>
            </li>
          );
        })}
      </ol>

      <div className="progress-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress-bar-fill" style={{ width: `${total > 0 ? Math.max(pct, 4) : 4}%` }} />
      </div>

      <div className="progress-meta">
        <span className="current-file">
          {currentFile ?? (total > 0 ? 'starting…' : 'waiting for worker…')}
        </span>
        {total > 0 && (
          <span>
            {current} / {total} files
          </span>
        )}
      </div>

      <div className="progress-actions">
        <button type="button" className="cancel-button" onClick={onCancel} disabled={cancelling}>
          {cancelling ? 'Cancelling…' : 'Cancel review'}
        </button>
      </div>
    </div>
  );
}
