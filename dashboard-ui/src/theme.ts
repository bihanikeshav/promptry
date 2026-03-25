export const theme = {
  bg: "#0d1117",
  surface: "#161b22",
  border: "#21262d",
  text: "#e6edf3",
  secondary: "#7d8590",
  muted: "#484f58",
  accent: "#58a6ff",
  success: "#3fb950",
  warning: "#d29922",
  error: "#f85149",
  font: "'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace",
} as const;

export function scoreColor(score: number | null): string {
  if (score === null) return theme.muted;
  if (score >= 0.8) return theme.success;
  if (score >= 0.6) return theme.warning;
  return theme.error;
}
