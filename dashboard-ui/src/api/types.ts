export interface SuiteSummary {
  name: string;
  latest_score: number | null;
  passed: boolean;
  model_version: string | null;
  prompt_version: number | null;
  timestamp: string;
  drift_status: "stable" | "drifting";
  drift_slope: number;
  sparkline_scores: number[];
}

export interface EvalRun {
  id: number;
  suite_name: string;
  prompt_name: string | null;
  prompt_version: number | null;
  model_version: string | null;
  timestamp: string;
  overall_pass: boolean;
  overall_score: number | null;
}

export interface AssertionResult {
  id: number;
  run_id: number;
  test_name: string;
  assertion_type: string;
  passed: boolean;
  score: number | null;
  details: Record<string, unknown> | null;
  latency_ms: number | null;
}

export interface RunDetailResponse {
  run: EvalRun;
  assertions: AssertionResult[];
}

export interface PromptSummary {
  name: string;
  latest_version: number;
  tags: string[];
}

export interface PromptVersion {
  version: number;
  hash: string;
  created_at: string;
  tags: string[];
}

export interface DiffLine {
  type: "unchanged" | "added" | "deleted";
  old_num: number | null;
  new_num: number | null;
  content: string;
}

export interface DiffResponse {
  additions: number;
  deletions: number;
  lines: DiffLine[];
}

export interface ModelVersion {
  model_version: string;
  run_count: number;
}

export interface AssertionComparison {
  assertion_type: string;
  baseline_mean: number;
  baseline_std: number;
  candidate_score: number;
  delta: number;
  verdict: "better" | "worse" | "comparable";
}

export interface ModelCompareReport {
  suite_name: string;
  baseline: {
    model_version: string;
    run_count: number;
    overall_mean: number;
    overall_std: number;
  };
  candidate: {
    model_version: string;
    run_count: number;
    overall_mean: number;
    overall_std: number;
  };
  overall_delta: number;
  percentile: number;
  assertion_comparisons: AssertionComparison[];
  cost_ratio: number | null;
  score_per_dollar_baseline: number | null;
  score_per_dollar_candidate: number | null;
  verdict: "switch" | "comparable" | "keep_baseline";
  verdict_reason: string;
}

export interface PlaygroundAssertionDef {
  type: "contains" | "not_contains" | "json_valid" | "matches";
  value?: string | string[];
  options?: Record<string, unknown>;
}

export interface PlaygroundAssertionResult {
  index: number;
  type: string;
  passed: boolean;
  score: number;
  details: Record<string, unknown>;
}

export interface PlaygroundEvalResponse {
  overall_passed: boolean;
  overall_score: number;
  passed_count: number;
  total_count: number;
  results: PlaygroundAssertionResult[];
}

export interface RunDiffSide {
  passed: boolean;
  score: number | null;
  details: Record<string, unknown> | null;
  latency_ms: number | null;
}

export interface RunDiffAssertion {
  type: string;
  baseline: RunDiffSide | null;
  current: RunDiffSide | null;
  score_delta: number | null;
  status_change: "none" | "regressed" | "improved" | "passed";
}

export interface RunDiffTest {
  name: string;
  status: "passed" | "failed" | "regressed" | "improved" | "unchanged";
  assertions: RunDiffAssertion[];
}

export interface RunDiffRunMeta {
  id: number;
  suite_name: string;
  score: number | null;
  overall_pass: boolean;
  model_version: string | null;
  prompt_name: string | null;
  prompt_version: number | null;
  timestamp: string;
}

export interface RunDiff {
  current: RunDiffRunMeta;
  baseline: RunDiffRunMeta;
  score_delta: number | null;
  summary: {
    regressed: number;
    improved: number;
    unchanged: number;
    total: number;
  };
  tests: RunDiffTest[];
}

export interface CostResponse {
  summary: {
    total_cost: number;
    total_calls: number;
    total_tokens_in: number;
    total_tokens_out: number;
    avg_cost: number;
  };
  by_name: {
    name: string;
    calls: number;
    tokens_in: number;
    tokens_out: number;
    cost: number;
    models: string[];
  }[];
  by_date: {
    date: string;
    calls: number;
    tokens_in: number;
    tokens_out: number;
    cost: number;
  }[];
}
