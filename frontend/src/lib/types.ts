export type RunStatus = "queued" | "running" | "completed" | "failed" | "stopped";
export type IssueSeverity = "critical" | "major" | "minor" | "suggestion";
export type IssueCategory = "functional" | "ui_ux" | "performance" | "accessibility" | "seo" | "security";

export interface PerformanceMetrics {
  loadTime?: number | null;
  domContentLoaded?: number | null;
  ttfb?: number | null;
  fcp?: number | null;
  resourceCount?: number;
  transferSize?: number;
}

export interface Step {
  index: number;
  action: string;
  target?: string | null;
  value?: string | null;
  thought?: string | null;
  screenshot?: string | null;
  timestamp: number;
  ok: boolean;
  error?: string | null;
  provider?: string | null;
}

export interface Provider {
  id: string;
  name: string;
  base_url: string;
  api_key: string; // masked when coming from the API
  has_api_key: boolean;
  vision_model: string;
  text_model: string;
  enabled: boolean;
}

export interface ProviderPreset {
  name: string;
  base_url: string;
  vision_model: string;
  text_model: string;
  needs_api_key: boolean;
}

export interface Issue {
  id: string;
  severity: IssueSeverity;
  category: IssueCategory;
  title: string;
  description: string;
  recommendation?: string | null;
  screenshot?: string | null;
  step_index?: number | null;
  source: string;
  timestamp: number;
}

export interface Summary {
  overall_assessment: string;
  score?: number | null;
  functional_suggestions: string[];
  ui_ux_suggestions: string[];
  seo_suggestions: string[];
  security_suggestions: string[];
}

export interface TestRun {
  id: string;
  url: string;
  goal: string;
  max_steps: number;
  headless: boolean;
  status: RunStatus;
  started_at: number;
  finished_at?: number | null;
  steps: Step[];
  issues: Issue[];
  summary: Summary;
  performance_metrics: Record<string, PerformanceMetrics>;
  error?: string | null;
  report_html_path?: string | null;
}

export interface TestRunListItem {
  id: string;
  url: string;
  goal: string;
  status: RunStatus;
  started_at: number;
  finished_at?: number | null;
  issue_count: number;
  score?: number | null;
}
