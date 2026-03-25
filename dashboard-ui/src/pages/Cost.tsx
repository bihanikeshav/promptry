import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { getCostData, getSuites } from "../api/client";
import type { CostResponse, SuiteSummary } from "../api/types";
import { theme } from "../theme";

export default function Cost() {
  const [data, setData] = useState<CostResponse | null>(null);
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [days, setDays] = useState(7);
  const [promptFilter, setPromptFilter] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load suites for filter dropdown
  useEffect(() => {
    getSuites().then(setSuites).catch(() => {});
  }, []);

  // Load cost data
  useEffect(() => {
    setLoading(true);
    setError(null);
    getCostData(
      days,
      promptFilter || undefined,
      modelFilter || undefined
    )
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [days, promptFilter, modelFilter]);

  // Collect unique models from by_name data
  const allModels = data
    ? [...new Set(data.by_name.flatMap((b) => b.models))]
    : [];

  return (
    <div>
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4 }}>
        Cost
      </div>
      <h1
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: theme.text,
          marginBottom: 20,
        }}
      >
        Cost Tracking
      </h1>

      {/* Filters */}
      <div
        style={{
          display: "flex",
          gap: 12,
          marginBottom: 24,
          flexWrap: "wrap",
          alignItems: "flex-end",
        }}
      >
        <FilterGroup label="Days">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={selectStyle}
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </FilterGroup>

        <FilterGroup label="Prompt">
          <select
            value={promptFilter}
            onChange={(e) => setPromptFilter(e.target.value)}
            style={selectStyle}
          >
            <option value="">All prompts</option>
            {data?.by_name.map((b) => (
              <option key={b.name} value={b.name}>
                {b.name}
              </option>
            ))}
          </select>
        </FilterGroup>

        <FilterGroup label="Model">
          <select
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
            style={selectStyle}
          >
            <option value="">All models</option>
            {allModels.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </FilterGroup>
      </div>

      {loading && (
        <div style={{ color: theme.muted, padding: 32, textAlign: "center" }}>
          Loading...
        </div>
      )}

      {error && (
        <div
          style={{
            color: theme.error,
            padding: 16,
            background: "rgba(248,81,73,0.1)",
            borderRadius: 6,
            fontSize: 13,
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          {/* Summary cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: 12,
              marginBottom: 24,
            }}
          >
            <SummaryCard
              label="Total Cost"
              value={`$${data.summary.total_cost.toFixed(4)}`}
            />
            <SummaryCard
              label="Total Calls"
              value={data.summary.total_calls.toLocaleString()}
            />
            <SummaryCard
              label="Tokens (in/out)"
              value={`${formatTokens(data.summary.total_tokens_in)} / ${formatTokens(data.summary.total_tokens_out)}`}
            />
            <SummaryCard
              label="Avg $/Call"
              value={`$${data.summary.avg_cost.toFixed(6)}`}
            />
          </div>

          {/* Daily cost chart */}
          {data.by_date.length > 0 && (
            <div
              style={{
                background: theme.surface,
                border: `1px solid ${theme.border}`,
                borderRadius: 6,
                padding: 16,
                marginBottom: 24,
              }}
            >
              <h3
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.text,
                  marginBottom: 12,
                }}
              >
                Daily Cost
              </h3>
              <div style={{ width: "100%", height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={data.by_date}>
                    <XAxis
                      dataKey="date"
                      tick={{ fill: theme.muted, fontSize: 10 }}
                      axisLine={{ stroke: theme.border }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: theme.muted, fontSize: 10 }}
                      axisLine={{ stroke: theme.border }}
                      tickLine={false}
                      width={50}
                      tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: theme.surface,
                        border: `1px solid ${theme.border}`,
                        borderRadius: 6,
                        color: theme.text,
                        fontSize: 12,
                        fontFamily: theme.font,
                      }}
                      formatter={(value: number) => [
                        `$${value.toFixed(4)}`,
                        "Cost",
                      ]}
                    />
                    <Bar
                      dataKey="cost"
                      fill={theme.accent}
                      radius={[3, 3, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* By-prompt table */}
          {data.by_name.length > 0 && (
            <div
              style={{
                background: theme.surface,
                border: `1px solid ${theme.border}`,
                borderRadius: 6,
                padding: 16,
              }}
            >
              <h3
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.text,
                  marginBottom: 12,
                }}
              >
                By Prompt
              </h3>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 12,
                  fontFamily: theme.font,
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: `1px solid ${theme.border}`,
                    }}
                  >
                    <th style={thStyle}>Name</th>
                    <th style={thStyle}>Calls</th>
                    <th style={thStyle}>Tokens In</th>
                    <th style={thStyle}>Tokens Out</th>
                    <th style={thStyle}>Cost</th>
                    <th style={thStyle}>Models</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_name.map((b) => (
                    <tr
                      key={b.name}
                      style={{
                        borderBottom: `1px solid ${theme.border}`,
                      }}
                    >
                      <td style={{ ...tdStyle, fontWeight: 600 }}>
                        {b.name}
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        {b.calls}
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        {formatTokens(b.tokens_in)}
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        {formatTokens(b.tokens_out)}
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: "center",
                          color: theme.accent,
                        }}
                      >
                        ${b.cost.toFixed(4)}
                      </td>
                      <td style={{ ...tdStyle, color: theme.muted }}>
                        {b.models.join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: 6,
        padding: "12px 16px",
      }}
    >
      <div style={{ fontSize: 10, color: theme.muted, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color: theme.text }}>
        {value}
      </div>
    </div>
  );
}

function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          color: theme.muted,
          marginBottom: 4,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const selectStyle: React.CSSProperties = {
  background: "#161b22",
  border: "1px solid #21262d",
  color: "#e6edf3",
  padding: "8px 12px",
  borderRadius: 6,
  fontSize: 12,
  fontFamily:
    "'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace",
  minWidth: 160,
};

const thStyle: React.CSSProperties = {
  padding: "6px 8px",
  fontWeight: 500,
  color: "#7d8590",
  fontSize: 11,
  textAlign: "left",
};

const tdStyle: React.CSSProperties = {
  padding: "8px",
  whiteSpace: "nowrap",
};
