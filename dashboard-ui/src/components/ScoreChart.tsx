import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { theme } from "../theme";

interface ScoreChartProps {
  data: { label: string; score: number }[];
}

export default function ScoreChart({ data }: ScoreChartProps) {
  return (
    <div style={{ width: "100%", height: 260 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <XAxis
            dataKey="label"
            tick={{ fill: theme.muted, fontSize: 11 }}
            axisLine={{ stroke: theme.border }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fill: theme.muted, fontSize: 11 }}
            axisLine={{ stroke: theme.border }}
            tickLine={false}
            width={36}
          />
          <Tooltip
            contentStyle={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              color: theme.text,
              fontSize: 12,
              fontFamily: theme.fontMono,
            }}
          />
          <ReferenceLine y={0.8} stroke={theme.success} strokeDasharray="4 4" />
          <ReferenceLine y={0.6} stroke={theme.warning} strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="score"
            stroke={theme.accent}
            strokeWidth={2}
            dot={{ fill: theme.accent, r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
