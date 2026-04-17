import type {
  SuiteSummary,
  EvalRun,
  RunDetailResponse,
  RunDiff,
  PromptSummary,
  PromptVersion,
  DiffResponse,
  ModelVersion,
  ModelCompareReport,
  CostResponse,
  PlaygroundAssertionDef,
  PlaygroundEvalResponse,
} from "./types";

function getBaseUrl(): string {
  const params = new URLSearchParams(window.location.search);
  const port = params.get("port") || "8420";
  const hostname = window.location.hostname;

  // If we're on localhost and the page is served from the same backend, use relative URLs
  if (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "0.0.0.0"
  ) {
    return "";
  }

  // Otherwise, point to the backend explicitly
  return `http://localhost:${port}`;
}

const BASE = getBaseUrl();

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// ---- Suites ----

export function getSuites(): Promise<SuiteSummary[]> {
  return fetchJson("/api/suites");
}

export function getSuiteRuns(
  name: string,
  limit = 20
): Promise<EvalRun[]> {
  return fetchJson(`/api/suite/${encodeURIComponent(name)}/runs?limit=${limit}`);
}

export function getRunDetail(
  name: string,
  runId: number
): Promise<RunDetailResponse> {
  return fetchJson(
    `/api/suite/${encodeURIComponent(name)}/run/${runId}`
  );
}

export function getRunDiff(
  currentId: number,
  baselineId: number
): Promise<RunDiff> {
  return fetchJson(`/api/runs/${currentId}/diff/${baselineId}`);
}

// ---- Prompts ----

export function getPrompts(): Promise<PromptSummary[]> {
  return fetchJson("/api/prompts");
}

export function getPromptVersions(
  name: string
): Promise<{ versions: PromptVersion[] }> {
  return fetchJson(`/api/prompts/${encodeURIComponent(name)}`);
}

export function getPromptDiff(
  name: string,
  v1: number,
  v2: number
): Promise<DiffResponse> {
  return fetchJson(
    `/api/prompts/${encodeURIComponent(name)}/diff?v1=${v1}&v2=${v2}`
  );
}

// ---- Models ----

export function getModelVersions(
  suite: string
): Promise<{ versions: ModelVersion[] }> {
  return fetchJson(`/api/models/${encodeURIComponent(suite)}`);
}

export function compareModels(
  suite: string,
  baseline: string,
  candidate: string
): Promise<ModelCompareReport> {
  return fetchJson(
    `/api/models/${encodeURIComponent(suite)}/compare?baseline=${encodeURIComponent(baseline)}&candidate=${encodeURIComponent(candidate)}`
  );
}

// ---- Cost ----

// ---- Playground ----

export async function runPlaygroundEval(
  response: string,
  assertions: PlaygroundAssertionDef[],
): Promise<PlaygroundEvalResponse> {
  const res = await fetch(`${BASE}/api/playground/eval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ response, assertions }),
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// ---- Cost ----

export function getCostData(
  days = 7,
  name?: string,
  model?: string
): Promise<CostResponse> {
  const params = new URLSearchParams({ days: String(days) });
  if (name) params.set("name", name);
  if (model) params.set("model", model);
  return fetchJson(`/api/cost?${params.toString()}`);
}
