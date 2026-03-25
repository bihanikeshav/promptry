import { theme, scoreColor } from "../theme";

interface SparklineProps {
  scores: number[];
  width?: number;
  height?: number;
}

export default function Sparkline({
  scores,
  width = 80,
  height = 24,
}: SparklineProps) {
  if (scores.length < 2) {
    return (
      <svg width={width} height={height}>
        <text
          x={width / 2}
          y={height / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={theme.muted}
          fontSize={10}
        >
          --
        </text>
      </svg>
    );
  }

  const padding = 2;
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = max - min || 1;

  const points = scores.map((s, i) => {
    const x = padding + (i / (scores.length - 1)) * innerW;
    const y = padding + (1 - (s - min) / range) * innerH;
    return `${x},${y}`;
  });

  const lastScore = scores[scores.length - 1];
  const color = scoreColor(lastScore);

  return (
    <svg width={width} height={height}>
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
