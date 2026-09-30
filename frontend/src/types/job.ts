import type { Issue, MemoryUsed, RequirementsReport } from './review';

export type SourceMode = 'paste' | 'files' | 'branch' | 'requirements';

export type JobStatus =
  | 'queued'
  | 'fetching'
  | 'recalling'
  | 'reviewing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'cancelled'];

export interface JobProgress {
  step: string;
  current: number;
  total: number;
  current_file: string | null;
}

export interface DiffLine {
  type: 'context' | 'add' | 'del';
  old_no: number | null;
  new_no: number | null;
  text: string;
}

export interface DiffHunk {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  header: string | null;
  lines: DiffLine[];
}

export interface FileDiff {
  path: string;
  old_path: string | null;
  status: string;
  hunks: DiffHunk[];
}

export interface FileSummary {
  path: string;
  language: string;
  issue_count: number;
  skipped: boolean;
  skip_reason: string | null;
  content: string | null;
  truncated: boolean;
}

export interface SeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  suggestion: number;
}

export interface SkippedFile {
  path: string;
  reason: string;
}

export interface ReviewResult {
  summary: string;
  score: number;
  severity_counts: SeverityCounts;
  issues: Issue[];
  suggestions: string[];
  files: FileSummary[];
  diffs: FileDiff[];
  memories_used: MemoryUsed[];
  requirements_report?: RequirementsReport | null;
  model_used: string;
  mode: SourceMode;
  repo_url: string | null;
  branch: string | null;
  base_branch: string | null;
}

export interface JobRequest {
  mode: SourceMode;
  code?: string;
  language?: string;
  query?: string;
  repo_url?: string;
  branch?: string;
  base_branch?: string;
  requirements?: string;
  bank_id?: string;
}

export interface JobResponse {
  job_id: string;
  status: JobStatus;
  progress: JobProgress;
  result: ReviewResult | null;
  error: string | null;
  mode: SourceMode;
  skipped: SkippedFile[];
}

export interface BranchInfo {
  name: string;
  is_default: boolean;
}

export interface BranchListResponse {
  repo_url: string;
  branches: BranchInfo[];
}
