import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getSuiteRuns, getRunDetail } from "../api/client";
import type { EvalRun, AssertionResult } from "../api/types";
import { theme, scoreColor } from "../theme";
import ScoreChart from "../components/ScoreChart";

export default function SuiteDetail() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [assertions, setAssertions] = useState<AssertionResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!name) return;
    setLoading(true);
    setError(null);

    getSuiteRuns(name, 50)
      .then(async (r) => {
        setRuns(r);
        // Load assertions for latest run
        if (r.length > 0) {
          const detail = await getRunDetail(name, r[0].id);
          setAssertions(detail.assertions);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [name]);

  const latest = runs[0] ?? null;
  const previous = runs[1] ?? null;

  // Root cause analysis
  let rootCause = "";
  if (latest && previous) {
    if (latest.prompt_version !== previous.prompt_version) {
      rootCause = `prompt v${previous.prompt_version ?? "?"} → v${latest.prompt_version ?? "?"}`;
    } else if (latest.model_version !== previous.model_version) {
      rootCause = `model ${previous.model_version ?? "?"} → ${latest.model_version ?? "?"}`;
    }
  }

  // Score history chart data
  const chartData = [...runs]
    .reverse()
    .filter((r) => r.overall_score !== null)
    .map((r, i) => ({
      label: `#${r.id}`,
      score: r.overall_score!,
    }));

  // Assertion breakdown: group by assertion_type and compute stats
  const assertionBreakdown = (() => {
    const byType: Record<
      string,
      { type: string; total: number; passed: number; avgScore: number }
    > = {};
    for (const a of assertions) {
      if (!byType[a.assertion_type]) {
        byType[a.assertion_type] = {
          type: a.assertion_type,
          total: 0,
          passed: 0,
          avgScore: 0,
        };
      }
      byType[a.assertion_type].total++;
      if (a.passed) byType[a.assertion_type].passed++;
      if (a.score !== null) byType[a.assertion_type].avgScore += a.score;
    }
    return Object.values(byType).map((b) => ({
      ...b,
      avgScore: b.total > 0 ? b.avgScore / b.total : 0,
    }));
  })();

  return (
    <div>
      {/* Breadcrumbs */}
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontFamily: theme.fontUI }}>
        <Link to="/" style={{ color: theme.accent, textDecoration: "none" }}>
          Overview
        </Link>
        {" / "}
        <span style={{ color: theme.text }}>{name}</span>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 20,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 600, color: theme.text, fontFamily: theme.fontUI }}>
          {name}
        </h1>
        <button
          onClick={load}
          style={{
            background: theme.surface,
            border: `1px solid ${theme.border}`,
            color: theme.accent,
            padding: "6px 14px",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 12,
            fontFamily: theme.fontUI,
          }}
        >
          Refresh
        </button>
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
            background: "rgba(248,113,113,0.1)",
            borderRadius: 6,
            fontSize: 13,
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {!loading && latest && (
        <>
          {/* Status cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: 12,
              marginBottom: 24,
            }}
          >
            <Card
              label="Status"
              value={latest.overall_pass ? "PASS" : "FAIL"}
              valueColor={latest.overall_pass ? theme.success : theme.error}
            />
            <Card
              label="Score"
              value={
                latest.overall_score !== null
                  ? (latest.overall_score * 100).toFixed(1) + "%"
                  : "--"
              }
              valueColor={scoreColor(latest.overall_score)}
            />
            <Card
              label="Model"
              value={latest.model_version ?? "--"}
              valueColor={theme.text}
            />
            {rootCause && (
              <Card
                label="Root Cause"
                value={rootCause}
                valueColor={theme.warning}
              />
            )}
          </div>

          {/* Score history chart */}
          {chartData.length > 1 && (
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
                  fontFamily: theme.fontUI,
                }}
              >
                Score History
              </h3>
              <ScoreChart data={chartData} />
            </div>
          )}

          {/* Assertion breakdown */}
          {assertionBreakdown.length > 0 && (
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
                  fontFamily: theme.fontUI,
                }}
              >
                Assertion Breakdown (Latest Run)
              </h3>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 12,
                }}
              >
                <thead>
                  <tr
                    style={{ borderBottom: `1px solid ${theme.border}` }}
                  >
                    <th style={thStyle}>Type</th>
                    <th style={thStyle}>Passed</th>
                    <th style={thStyle}>Total</th>
                    <th style={thStyle}>Avg Score</th>
                  </tr>
                </thead>
                <tbody>
                  {assertionBreakdown.map((b) => (
                    <tr
                      key={b.type}
                      style={{
                        borderBottom: `1px solid ${theme.border}`,
                      }}
                    >
                      <td style={{ ...tdStyle, fontFamily: theme.fontUI }}>{b.type}</td>
                      <td style={{ ...tdStyle, textAlign: "center", fontFamily: theme.fontMono }}>
                        {b.passed}
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center", fontFamily: theme.fontMono }}>
                        {b.total}
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: "center",
                          color: scoreColor(b.avgScore),
                          fontFamily: theme.fontMono,
                        }}
                      >
                        {(b.avgScore * 100).toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Recent runs table */}
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
                fontFamily: theme.fontUI,
              }}
            >
              Recent Runs
            </h3>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 12,
              }}
            >
              <thead>
                <tr style={{ borderBottom: `1px solid ${theme.border}` }}>
                  <th style={thStyle}>Run</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Score</th>
                  <th style={thStyle}>Model</th>
                  <th style={thStyle}>Prompt</th>
                  <th style={thStyle}>Time</th>
                  <th style={thStyle}></th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 20).map((r, idx) => {
                  const prev = runs[idx + 1];
                  return (
                    <tr
                      key={r.id}
                      onClick={() =>
                        navigate(
                          `/suite/${encodeURIComponent(name!)}/run/${r.id}`
                        )
                      }
                      style={{
                        borderBottom: `1px solid ${theme.border}`,
                        cursor: "pointer",
                      }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.background =
                          "rgba(249,115,22,0.04)")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.background = "transparent")
                      }
                    >
                      <td style={{ ...tdStyle, fontFamily: theme.fontMono }}>#{r.id}</td>
                      <td style={tdStyle}>
                        <span
                          style={{
                            color: r.overall_pass ? theme.success : theme.error,
                            fontWeight: 600,
                            fontFamily: theme.fontUI,
                          }}
                        >
                          {r.overall_pass ? "PASS" : "FAIL"}
                        </span>
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          color: scoreColor(r.overall_score),
                          fontWeight: 600,
                          fontFamily: theme.fontMono,
                        }}
                      >
                        {r.overall_score !== null
                          ? (r.overall_score * 100).toFixed(1) + "%"
                          : "--"}
                      </td>
                      <td style={{ ...tdStyle, color: theme.secondary, fontFamily: theme.fontMono }}>
                        {r.model_version ?? "--"}
                      </td>
                      <td style={{ ...tdStyle, color: theme.secondary, fontFamily: theme.fontMono }}>
                        {r.prompt_version !== null
                          ? `v${r.prompt_version}`
                          : "--"}
                      </td>
                      <td style={{ ...tdStyle, color: theme.muted, fontFamily: theme.fontMono }}>
                        {new Date(r.timestamp).toLocaleString()}
                      </td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>
                        {prev && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(
                                `/suite/${encodeURIComponent(name!)}/diff?current=${r.id}&baseline=${prev.id}`
                              );
                            }}
                            style={{
                              background: "transparent",
                              border: `1px solid ${theme.border}`,
                              color: theme.accent,
                              padding: "3px 10px",
                              borderRadius: 4,
                              cursor: "pointer",
                              fontSize: 11,
                              fontFamily: theme.fontUI,
                            }}
                            title={`Compare #${r.id} with #${prev.id}`}
                          >
                            Compare
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Card({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor: string;
}) {
  return (
    <div
      style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: 6,
        padding: "12px 16px",
      }}
    >
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontFamily: theme.fontUI }}>
        {label}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, color: valueColor, fontFamily: theme.fontMono }}>
        {value}
      </div>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "6px 8px",
  fontWeight: 500,
  color: theme.secondary,
  fontSize: 11,
  textAlign: "left",
  fontFamily: theme.fontUI,
};

const tdStyle: React.CSSProperties = {
  padding: "8px",
  whiteSpace: "nowrap",
};
