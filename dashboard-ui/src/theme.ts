export const theme = {
  bg: "#111113",
  surface: "#1a1a1e",
  border: "#2a2a2e",
  text: "#e8e8ec",
  secondary: "#9898a0",
  muted: "#5c5c66",
  accent: "#fb923c",
  success: "#4ade80",
  warning: "#fbbf24",
  error: "#f87171",
  fontUI: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
  fontMono: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
} as const;

export function scoreColor(score: number | null): string {
  if (score === null) return theme.muted;
  if (score >= 0.8) return theme.success;
  if (score >= 0.6) return theme.warning;
  return theme.error;
}
