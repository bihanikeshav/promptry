import { theme, scoreColor } from "../theme";

interface AssertionBarProps {
  score: number | null;
  width?: number;
  height?: number;
}

export default function AssertionBar({
  score,
  width = 120,
  height = 14,
}: AssertionBarProps) {
  if (score === null) {
    return (
      <div
        style={{
          width,
          height,
          background: theme.border,
          borderRadius: 4,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span style={{ fontSize: 10, color: theme.muted }}>N/A</span>
      </div>
    );
  }

  const color = scoreColor(score);
  const fillW = Math.max(0, Math.min(1, score)) * width;

  return (
    <div
      style={{
        width,
        height,
        background: theme.border,
        borderRadius: 4,
        overflow: "hidden",
        position: "relative",
      }}
    >
      <div
        style={{
          width: fillW,
          height: "100%",
          background: color,
          borderRadius: 4,
          transition: "width 0.3s ease",
        }}
      />
    </div>
  );
}
