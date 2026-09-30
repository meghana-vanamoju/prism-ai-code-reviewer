import { useCallback, useEffect, useRef, useState } from 'react';
import { SummaryPanel } from './components/SummaryPanel';
import { RequirementsPanel } from './components/RequirementsPanel';
import { IssuesPanel } from './components/IssuesPanel';
import { MemoriesPanel } from './components/MemoriesPanel';
import { ScoreRing } from './components/ScoreRing';
import { SourceIntake } from './components/SourceIntake';
import { ProgressView } from './components/ProgressView';
import { CodeViewer } from './components/CodeViewer';
import {
  cancelJob,
  createJob,
  getJob,
  healthCheck,
  submitFeedback,
  uploadJob,
} from './services/api';
import type { UploadEntry } from './services/api';
import {
  TERMINAL_STATUSES,
} from './types/job';
import type { JobRequest, JobResponse, ReviewResult, SourceMode } from './types/job';
import type { IssueFeedback, ReviewRequest, ReviewResponse } from './types/review';
import './App.css';

type ApiStatus = 'checking' | 'connected' | 'disconnected';
type Theme = 'dark' | 'light';

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

const THEME_STORAGE_KEY = 'prism-theme';
const POLL_INTERVAL_MS = 800;
const MAX_CONSECUTIVE_POLL_ERRORS = 3;
// How often to re-probe /health after a failed check.
const HEALTH_RETRY_MS = 5_000;
// Errors produced by api.ts when the request never reached the backend.
const NETWORK_ERROR_RE = /Cannot reach the API|timed out after/;

function isTerminal(status: JobResponse['status']): boolean {
  return TERMINAL_STATUSES.includes(status);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // localStorage can be unavailable (private mode); fall back to dark.
  }
  return 'dark';
}

const MODE_LABEL: Record<SourceMode, string> = {
  paste: 'Paste',
  files: 'Files',
  branch: 'Branch',
  requirements: 'Requirements',
};

function App() {
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking');
  const [apiDetail, setApiDetail] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [focusLine, setFocusLine] = useState<number | null>(null);
  const pollTokenRef = useRef<{ cancelled: boolean } | null>(null);

  const running = Boolean(job && !isTerminal(job.status));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Ignore quota/private-mode failures — the UI theme still applies.
    }
  }, [theme]);

  // Stop polling if the component unmounts mid-review.
  useEffect(
    () => () => {
      if (pollTokenRef.current) pollTokenRef.current.cancelled = true;
    },
    [],
  );

  // Reports the real outcome of GET /health: connected only when the backend
  // answers with a healthy status, disconnected when it is unreachable or
  // reports a non-healthy status.
  const runHealthCheck = useCallback(async () => {
    try {
      const health = await healthCheck();
      if (health.status === 'healthy') {
        setApiStatus('connected');
        setApiDetail(health.service);
        // Connectivity is restored: drop a stale network error banner so it
        // cannot outlive the failure it describes.
        setError((prev) => (prev && NETWORK_ERROR_RE.test(prev) ? null : prev));
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

  // Self-heal: while the backend looks unreachable, keep re-checking so a
  // restart or a stale tab recovers without a manual page refresh. The
  // interval is torn down as soon as the check succeeds.
  useEffect(() => {
    if (apiStatus !== 'disconnected') return;
    const id = setInterval(() => {
      void runHealthCheck();
    }, HEALTH_RETRY_MS);
    return () => clearInterval(id);
  }, [apiStatus, runHealthCheck]);

  const finishJob = useCallback(
    (finished: JobResponse) => {
      if (finished.status === 'completed' && finished.result) {
        const files = finished.result.files;
        const preferred =
          files.find((f) => f.issue_count > 0 && !f.skipped) ??
          files.find((f) => !f.skipped) ??
          files[0];
        setResult(finished.result);
        setSelectedFile(preferred?.path ?? '');
        setFocusLine(null);
        setJob(finished);
        setApiStatus('connected');
        setApiDetail(null);
        return;
      }
      if (finished.status === 'failed') {
        setError(finished.error || 'Review failed');
        void refreshApiHealth();
        setJob(finished);
        return;
      }
      // cancelled: drop the job so the input panel returns.
      setJob(null);
    },
    [refreshApiHealth],
  );

  const runJob = useCallback(
    async (starter: () => Promise<JobResponse>) => {
      if (pollTokenRef.current) pollTokenRef.current.cancelled = true;
      setError(null);
      setFeedbackError(null);
      setFeedbackSuccess(null);
      setResult(null);
      setJob(null);
      setIsSubmitting(true);
      try {
        const initial = await starter();
        setJob(initial);
        if (isTerminal(initial.status)) {
          finishJob(initial);
          return;
        }
        const token = { cancelled: false };
        pollTokenRef.current = token;
        let failures = 0;
        while (!token.cancelled) {
          await delay(POLL_INTERVAL_MS);
          if (token.cancelled) break;
          try {
            const next = await getJob(initial.job_id);
            failures = 0;
            if (token.cancelled) break;
            setJob(next);
            if (isTerminal(next.status)) {
              finishJob(next);
              break;
            }
          } catch (pollErr) {
            failures += 1;
            if (failures >= MAX_CONSECUTIVE_POLL_ERRORS) throw pollErr;
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Review failed');
        void refreshApiHealth();
      } finally {
        setIsSubmitting(false);
      }
    },
    [finishJob, refreshApiHealth],
  );

  const handlePasteSubmit = (request: ReviewRequest, requirements?: string) => {
    const trimmedRequirements = requirements?.trim();
    void runJob(() =>
      createJob({
        mode: trimmedRequirements ? 'requirements' : 'paste',
        code: request.code,
        language: request.language,
        query: request.query,
        requirements: trimmedRequirements || undefined,
      }),
    );
  };

  const handleFilesSubmit = (entries: UploadEntry[], query: string, requirements?: string) => {
    void runJob(() => uploadJob(entries, query || undefined, requirements?.trim() || undefined));
  };

  const handleBranchSubmit = (request: JobRequest) => {
    void runJob(() => createJob(request));
  };

  const handleCancel = async () => {
    if (!job) return;
    setCancelling(true);
    if (pollTokenRef.current) pollTokenRef.current.cancelled = true;
    try {
      await cancelJob(job.job_id);
      setJob(null);
      setResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel review');
      void refreshApiHealth();
    } finally {
      setCancelling(false);
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setResult(null);
    setJob(null);
    setError(null);
    setFocusLine(null);
    setSelectedFile('');
    setFeedbackError(null);
    setFeedbackSuccess(null);
  };

  const handleFeedback = async (issueFeedback: IssueFeedback[]) => {
    if (!result) return;
    setFeedbackError(null);
    setFeedbackSuccess(null);
    try {
      const review: ReviewResponse = {
        summary: result.summary,
        issues: result.issues,
        suggestions: result.suggestions,
        memories_used: result.memories_used,
        model_used: result.model_used,
      };
      await submitFeedback({
        code: '',
        review_summary: review.summary,
        issues: review.issues,
        issue_feedback: issueFeedback,
      });
      setFeedbackSuccess('Feedback stored in Hindsight — future reviews will recall this decision');
      setTimeout(() => setFeedbackSuccess(null), 5000);
      setApiStatus('connected');
      setApiDetail(null);
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : 'Failed to store feedback');
      void refreshApiHealth();
    }
  };

  const handleIssueSelect = (file: string, line?: number) => {
    setSelectedFile(file);
    setFocusLine(typeof line === 'number' ? line : null);
  };

  // Dismissible so a failure message can never outlive the problem it describes.
  const errorBanner = error ? (
    <div className="error-banner" role="alert">
      <span className="error-banner-text">{error}</span>
      <button
        type="button"
        className="error-banner-dismiss"
        aria-label="Dismiss error"
        onClick={() => setError(null)}
      >
        ×
      </button>
    </div>
  ) : null;

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <div className="logo">
            <span className="logo-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2a8 8 0 0 0-8 8c0 4.4 4 8 8 8s8-3.6 8-8a8 8 0 0 0-8-8z" />
                <path d="M12 6v4" />
                <path d="M12 14v4" />
                <path d="M8 10h8" />
                <path d="M8 14h8" />
              </svg>
            </span>
            <span className="logo-word">PRISM</span>
            <span className="logo-badge">AI code review</span>
          </div>
          <p className="tagline">Persistent Review Intelligence & Standards Memory</p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☾ Dark' : '☀ Light'}
          </button>
          <button
            type="button"
            className="health-indicator"
            id="health-indicator"
            data-status={apiStatus}
            title={apiDetail ? `${apiDetail} — click to re-check` : 'Re-check API connection'}
            onClick={refreshApiHealth}
          >
            <span className={`health-dot ${API_STATUS_DOT[apiStatus]}`.trim()}></span>
            <span>{API_STATUS_LABEL[apiStatus]}</span>
          </button>
        </div>
      </header>

      <main className="app-main">
        {running && job ? (
          <div className="stage stage-progress">
            <ProgressView job={job} onCancel={handleCancel} cancelling={cancelling} />
            {errorBanner}
          </div>
        ) : !result ? (
          <div className="stage stage-landing">
            <section className="hero">
              <span className="hero-eyebrow">Diff-aware · standards-memory · line-level</span>
              <h1 className="hero-title">
                Review <span className="hero-accent">files</span>, folders and branches against
                standards that remember.
              </h1>
              <p className="hero-sub">
                Drop source files, scan a whole directory, or diff a remote branch. PRISM reviews
                every changed line and recalls the decisions your team has already made.
              </p>
              <ul className="hero-points">
                <li>Line-level findings</li>
                <li>Branch diffing</li>
                <li>Persistent team memory</li>
              </ul>
            </section>

            <SourceIntake
              disabled={isSubmitting}
              onSubmitPaste={handlePasteSubmit}
              onSubmitFiles={handleFilesSubmit}
              onSubmitBranch={handleBranchSubmit}
            />
            {errorBanner}
          </div>
        ) : (
          <div className="layout">
            <section className="input-section">
              <SourceIntake
                disabled={isSubmitting}
                onSubmitPaste={handlePasteSubmit}
                onSubmitFiles={handleFilesSubmit}
                onSubmitBranch={handleBranchSubmit}
              />
              {errorBanner}
            </section>

            <section className="results-section">
              <div className="result-header">
                <ScoreRing score={result.score} />
                <div className="result-header-body">
                  <div className="result-source-line">
                    <span className="source-badge">{MODE_LABEL[result.mode]}</span>
                    {result.repo_url && <span className="source-chip">{result.repo_url}</span>}
                    {result.branch && (
                      <span className="source-chip mono">
                        {result.branch}
                        {result.base_branch ? ` ← ${result.base_branch}` : ''}
                      </span>
                    )}
                  </div>
                  <div className="stat-tiles">
                    <StatTile label="Files" value={result.files.length} />
                    <StatTile
                      label="Issues"
                      value={result.issues.length}
                      tone={result.issues.length > 0 ? 'warn' : 'ok'}
                    />
                    <StatTile label="Memories" value={result.memories_used.length} />
                    <StatTile label="Model" value={result.model_used} mono />
                  </div>
                </div>
                <button type="button" className="review-button secondary" onClick={handleReset}>
                  New review
                </button>
              </div>

              <SummaryPanel review={result} />
              {result.requirements_report && (
                <RequirementsPanel report={result.requirements_report} onSelect={handleIssueSelect} />
              )}
              <CodeViewer
                result={result}
                selectedFile={selectedFile}
                onSelectFile={(path) => {
                  setSelectedFile(path);
                  setFocusLine(null);
                }}
                focusLine={focusLine}
                onIssueFocusHandled={() => setFocusLine(null)}
              />
              <IssuesPanel
                issues={result.issues}
                onFeedback={handleFeedback}
                onSelect={handleIssueSelect}
              />
              <MemoriesPanel memories={result.memories_used} />
              {(feedbackSuccess || feedbackError) && (
                <div className="feedback-status">
                  {feedbackSuccess && <div className="success-toast">{feedbackSuccess}</div>}
                  {feedbackError && <div className="error-toast">{feedbackError}</div>}
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

interface StatTileProps {
  label: string;
  value: number | string;
  tone?: 'ok' | 'warn';
  mono?: boolean;
}

function StatTile({ label, value, tone, mono }: StatTileProps) {
  return (
    <div className="stat-tile">
      <span className={`stat-value ${tone ?? ''} ${mono ? 'mono' : ''}`.trim()}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

export default App;
