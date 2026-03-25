import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { getRunDetail } from "../api/client";
import type { RunDetailResponse, AssertionResult } from "../api/types";
import { theme, scoreColor } from "../theme";
import AssertionBar from "../components/AssertionBar";
import ClaimBreakdown from "../components/ClaimBreakdown";

export default function RunDetail() {
  const { name, runId } = useParams<{ name: string; runId: string }>();
  const [data, setData] = useState<RunDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!name || !runId) return;
    setLoading(true);
    getRunDetail(name, parseInt(runId, 10))
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [name, runId]);

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Group assertions by test_name
  const grouped: Record<string, AssertionResult[]> = {};
  if (data) {
    for (const a of data.assertions) {
      const key = a.test_name || "(unnamed)";
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(a);
    }
  }

  return (
    <div>
      {/* Breadcrumbs */}
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4 }}>
        <Link to="/" style={{ color: theme.accent, textDecoration: "none" }}>
          Overview
        </Link>
        {" / "}
        <Link
          to={`/suite/${encodeURIComponent(name ?? "")}`}
          style={{ color: theme.accent, textDecoration: "none" }}
        >
          {name}
        </Link>
        {" / "}
        <span style={{ color: theme.text }}>Run #{runId}</span>
      </div>

      <h1 style={{ fontSize: 18, fontWeight: 600, color: theme.text, marginBottom: 20 }}>
        Run #{runId}
      </h1>

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
          }}
        >
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          {/* Run metadata */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: 12,
              marginBottom: 24,
            }}
          >
            <MetaCard
              label="Status"
              value={data.run.overall_pass ? "PASS" : "FAIL"}
              color={data.run.overall_pass ? theme.success : theme.error}
            />
            <MetaCard
              label="Score"
              value={
                data.run.overall_score !== null
                  ? (data.run.overall_score * 100).toFixed(1) + "%"
                  : "--"
              }
              color={scoreColor(data.run.overall_score)}
            />
            <MetaCard
              label="Model"
              value={data.run.model_version ?? "--"}
              color={theme.text}
            />
            <MetaCard
              label="Prompt"
              value={
                data.run.prompt_name
                  ? `${data.run.prompt_name} v${data.run.prompt_version ?? "?"}`
                  : "--"
              }
              color={theme.text}
            />
            <MetaCard
              label="Timestamp"
              value={new Date(data.run.timestamp).toLocaleString()}
              color={theme.secondary}
            />
          </div>

          {/* Assertions grouped by test_name */}
          {Object.entries(grouped).map(([testName, assertions]) => (
            <div
              key={testName}
              style={{
                background: theme.surface,
                border: `1px solid ${theme.border}`,
                borderRadius: 6,
                marginBottom: 16,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "10px 16px",
                  borderBottom: `1px solid ${theme.border}`,
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.text,
                }}
              >
                {testName}
              </div>
              {assertions.map((a) => (
                <div key={a.id}>
                  <div
                    onClick={() => toggleExpand(a.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "8px 16px",
                      borderBottom: `1px solid ${theme.border}`,
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background =
                        "rgba(88,166,255,0.04)")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "transparent")
                    }
                  >
                    <span
                      style={{
                        color: a.passed ? theme.success : theme.error,
                        fontWeight: 700,
                        width: 36,
                      }}
                    >
                      {a.passed ? "PASS" : "FAIL"}
                    </span>
                    <span style={{ color: theme.secondary, width: 100 }}>
                      {a.assertion_type}
                    </span>
                    <AssertionBar score={a.score} />
                    <span
                      style={{
                        color: scoreColor(a.score),
                        fontWeight: 600,
                        width: 50,
                        textAlign: "right",
                      }}
                    >
                      {a.score !== null
                        ? (a.score * 100).toFixed(0) + "%"
                        : "--"}
                    </span>
                    {a.latency_ms !== null && (
                      <span style={{ color: theme.muted, marginLeft: "auto" }}>
                        {a.latency_ms}ms
                      </span>
                    )}
                    <span style={{ color: theme.muted, marginLeft: 8 }}>
                      {expandedIds.has(a.id) ? "▼" : "▶"}
                    </span>
                  </div>

                  {/* Expanded details */}
                  {expandedIds.has(a.id) && a.details && (
                    <div
                      style={{
                        padding: "12px 16px 12px 64px",
                        borderBottom: `1px solid ${theme.border}`,
                        background: "rgba(0,0,0,0.15)",
                      }}
                    >
                      <AssertionDetails
                        type={a.assertion_type}
                        details={a.details}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function MetaCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div
      style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: 6,
        padding: "10px 14px",
      }}
    >
      <div style={{ fontSize: 10, color: theme.muted, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color }}>{value}</div>
    </div>
  );
}

function AssertionDetails({
  type,
  details,
}: {
  type: string;
  details: Record<string, unknown>;
}) {
  // Grounded type: render claim-by-claim
  if (type === "grounded") {
    return <ClaimBreakdown details={details} />;
  }

  // Schema type: show errors list
  if (type === "schema" && details.errors) {
    const errors = details.errors as string[];
    return (
      <div>
        <div
          style={{
            fontSize: 11,
            color: theme.error,
            fontWeight: 600,
            marginBottom: 6,
          }}
        >
          Schema Errors:
        </div>
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {errors.map((e, i) => (
            <li
              key={i}
              style={{ color: theme.secondary, fontSize: 12, marginBottom: 4 }}
            >
              {e}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // Default: formatted JSON
  return (
    <pre
      style={{
        color: theme.secondary,
        fontSize: 11,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        margin: 0,
        fontFamily: theme.font,
      }}
    >
      {JSON.stringify(details, null, 2)}
    </pre>
  );
}
