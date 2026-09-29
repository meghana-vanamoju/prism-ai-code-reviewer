export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'suggestion';

export interface Issue {
  severity: Severity;
  title: string;
  description: string;
  recommendation: string;
  memory_reference?: string;
}

export interface MemoryUsed {
  id: string;
  text: string;
  type?: string;
  context?: string;
  metadata?: Record<string, unknown>;
}

export interface ReviewRequest {
  code: string;
  language?: string;
  query?: string;
  bank_id?: string;
  recall_budget?: string;
  max_memories?: number;
}

export interface ReviewResponse {
  summary: string;
  issues: Issue[];
  suggestions: string[];
  memories_used: MemoryUsed[];
  model_used: string;
}

export type IssueDecision = 'accepted' | 'rejected';

export interface IssueFeedback {
  issue_title: string;
  decision: IssueDecision;
  reason?: string;
}

export interface ReviewFeedbackRequest {
  review_id?: string;
  code: string;
  review_summary: string;
  issues: Issue[];
  issue_feedback: IssueFeedback[];
  feedback?: string;
  bank_id?: string;
}

export interface ReviewFeedbackResponse {
  success: boolean;
  message: string;
}

export interface ApiError {
  detail: string;
}