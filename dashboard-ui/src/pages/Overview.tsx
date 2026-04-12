import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getSuites } from "../api/client";
import type { SuiteSummary } from "../api/types";
import { theme, scoreColor } from "../theme";
import Sparkline from "../components/Sparkline";

export default function Overview() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    setError(null);
    getSuites()
      .then(setSuites)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div>
          <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontFamily: theme.fontUI }}>
            Overview
          </div>
          <h1 style={{ fontSize: 18, fontWeight: 600, color: theme.text, fontFamily: theme.fontUI }}>
            Eval Suites
          </h1>
        </div>
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
          }}
        >
          {error}
        </div>
      )}

      {!loading && !error && suites.length === 0 && (
        <div style={{ color: theme.muted, padding: 32, textAlign: "center" }}>
          No eval suites found. Run some evals to get started.
        </div>
      )}

      {!loading && suites.length > 0 && (
        <div
          style={{
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
            overflow: "hidden",
          }}
        >
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13,
            }}
          >
            <thead>
              <tr
                style={{
                  background: theme.surface,
                  borderBottom: `1px solid ${theme.border}`,
                }}
              >
                <th style={thStyle}></th>
                <th style={{ ...thStyle, textAlign: "left" }}>Suite</th>
                <th style={thStyle}>Model</th>
                <th style={thStyle}>Prompt</th>
                <th style={thStyle}>Score</th>
                <th style={thStyle}>Drift</th>
                <th style={thStyle}>Trend</th>
                <th style={thStyle}>Time</th>
              </tr>
            </thead>
            <tbody>
              {suites.map((s) => (
                <tr
                  key={s.name}
                  onClick={() => navigate(`/suite/${encodeURIComponent(s.name)}`)}
                  style={{
                    borderBottom: `1px solid ${theme.border}`,
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = theme.surface)
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = "transparent")
                  }
                >
                  <td style={{ ...tdStyle, width: 32, textAlign: "center" }}>
                    <span
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: s.passed ? theme.success : theme.error,
                      }}
                    />
                  </td>
                  <td style={{ ...tdStyle, fontWeight: 600, fontFamily: theme.fontUI }}>
                    {s.name}
                    {!s.passed && (
                      <span
                        style={{
                          marginLeft: 8,
                          padding: "2px 6px",
                          fontSize: 10,
                          background: "rgba(248,113,113,0.15)",
                          color: theme.error,
                          borderRadius: 4,
                          fontWeight: 600,
                          fontFamily: theme.fontUI,
                        }}
                      >
                        REGRESSION
                      </span>
                    )}
                  </td>
                  <td style={{ ...tdStyle, color: theme.secondary, fontFamily: theme.fontMono }}>
                    {s.model_version ?? "--"}
                  </td>
                  <td style={{ ...tdStyle, color: theme.secondary, fontFamily: theme.fontMono }}>
                    {s.prompt_version !== null ? `v${s.prompt_version}` : "--"}
                  </td>
                  <td
                    style={{
                      ...tdStyle,
                      color: scoreColor(s.latest_score),
                      fontWeight: 600,
                      fontFamily: theme.fontMono,
                    }}
                  >
                    {s.latest_score !== null
                      ? (s.latest_score * 100).toFixed(0) + "%"
                      : "--"}
                  </td>
                  <td style={tdStyle}>
                    <span
                      style={{
                        padding: "2px 6px",
                        fontSize: 10,
                        borderRadius: 4,
                        fontFamily: theme.fontUI,
                        background:
                          s.drift_status === "drifting"
                            ? "rgba(251,191,36,0.15)"
                            : "rgba(74,222,128,0.1)",
                        color:
                          s.drift_status === "drifting"
                            ? theme.warning
                            : theme.success,
                      }}
                    >
                      {s.drift_status}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    <Sparkline scores={s.sparkline_scores} />
                  </td>
                  <td style={{ ...tdStyle, color: theme.muted, fontSize: 11, fontFamily: theme.fontMono }}>
                    {s.timestamp
                      ? new Date(s.timestamp).toLocaleString()
                      : "--"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "6px 10px",
  fontWeight: 500,
  color: theme.secondary,
  fontSize: 12,
  textAlign: "center",
  whiteSpace: "nowrap",
  fontFamily: theme.fontUI,
};

const tdStyle: React.CSSProperties = {
  padding: "8px 10px",
  whiteSpace: "nowrap",
};
