import { useState, useEffect } from "react";
import { getSuites, getModelVersions, compareModels } from "../api/client";
import type {
  SuiteSummary,
  ModelVersion,
  ModelCompareReport,
} from "../api/types";
import { theme, scoreColor } from "../theme";

export default function Models() {
  const [suites, setSuites] = useState<SuiteSummary[]>([]);
  const [selectedSuite, setSelectedSuite] = useState("");
  const [modelVersions, setModelVersions] = useState<ModelVersion[]>([]);
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const [report, setReport] = useState<ModelCompareReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSuites().then(setSuites).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedSuite) {
      setModelVersions([]);
      return;
    }
    getModelVersions(selectedSuite)
      .then((d) => {
        setModelVersions(d.versions);
        setBaseline("");
        setCandidate("");
        setReport(null);
      })
      .catch(() => setModelVersions([]));
  }, [selectedSuite]);

  const handleCompare = () => {
    if (!selectedSuite || !baseline || !candidate) return;
    setLoading(true);
    setError(null);
    setReport(null);
    compareModels(selectedSuite, baseline, candidate)
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const verdictColor = (v: string) => {
    if (v === "switch") return theme.success;
    if (v === "keep_baseline") return theme.error;
    return theme.warning;
  };

  const verdictLabel = (v: string) => {
    if (v === "switch") return "SWITCH";
    if (v === "keep_baseline") return "KEEP BASELINE";
    return "COMPARABLE";
  };

  return (
    <div>
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4 }}>
        Models
      </div>
      <h1
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: theme.text,
          marginBottom: 20,
        }}
      >
        Model Comparison
      </h1>

      {/* Controls */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "flex-end",
          marginBottom: 24,
          flexWrap: "wrap",
        }}
      >
        <SelectGroup label="Suite">
          <select
            value={selectedSuite}
            onChange={(e) => setSelectedSuite(e.target.value)}
            style={selectStyle}
          >
            <option value="">Select suite...</option>
            {suites.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
        </SelectGroup>

        <SelectGroup label="Baseline">
          <select
            value={baseline}
            onChange={(e) => setBaseline(e.target.value)}
            style={selectStyle}
            disabled={modelVersions.length === 0}
          >
            <option value="">Select baseline...</option>
            {modelVersions.map((m) => (
              <option key={m.model_version} value={m.model_version}>
                {m.model_version} ({m.run_count} runs)
              </option>
            ))}
          </select>
        </SelectGroup>

        <SelectGroup label="Candidate">
          <select
            value={candidate}
            onChange={(e) => setCandidate(e.target.value)}
            style={selectStyle}
            disabled={modelVersions.length === 0}
          >
            <option value="">Select candidate...</option>
            {modelVersions.map((m) => (
              <option key={m.model_version} value={m.model_version}>
                {m.model_version} ({m.run_count} runs)
              </option>
            ))}
          </select>
        </SelectGroup>

        <button
          onClick={handleCompare}
          disabled={!selectedSuite || !baseline || !candidate || loading}
          style={{
            background: theme.accent,
            color: "#fff",
            border: "none",
            padding: "8px 20px",
            borderRadius: 6,
            cursor:
              !selectedSuite || !baseline || !candidate
                ? "not-allowed"
                : "pointer",
            fontSize: 12,
            fontFamily: theme.font,
            fontWeight: 600,
            opacity: !selectedSuite || !baseline || !candidate ? 0.5 : 1,
          }}
        >
          {loading ? "Comparing..." : "Compare"}
        </button>
      </div>

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

      {report && (
        <>
          {/* Verdict banner */}
          <div
            style={{
              background: theme.surface,
              border: `2px solid ${verdictColor(report.verdict)}`,
              borderRadius: 6,
              padding: "16px 20px",
              marginBottom: 24,
              textAlign: "center",
            }}
          >
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: verdictColor(report.verdict),
                marginBottom: 6,
              }}
            >
              {verdictLabel(report.verdict)}
            </div>
            <div style={{ fontSize: 12, color: theme.secondary }}>
              {report.verdict_reason}
            </div>
          </div>

          {/* Score comparison cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: 12,
              marginBottom: 24,
            }}
          >
            <CompareCard
              label="Baseline Score"
              value={`${(report.baseline.overall_mean * 100).toFixed(1)}%`}
              sub={`${report.baseline.model_version} (${report.baseline.run_count} runs)`}
              color={scoreColor(report.baseline.overall_mean)}
            />
            <CompareCard
              label="Candidate Score"
              value={`${(report.candidate.overall_mean * 100).toFixed(1)}%`}
              sub={`${report.candidate.model_version} (${report.candidate.run_count} runs)`}
              color={scoreColor(report.candidate.overall_mean)}
            />
            <CompareCard
              label="Delta"
              value={`${report.overall_delta > 0 ? "+" : ""}${(report.overall_delta * 100).toFixed(1)}%`}
              sub={`Percentile: ${report.percentile.toFixed(0)}th`}
              color={
                report.overall_delta > 0
                  ? theme.success
                  : report.overall_delta < 0
                    ? theme.error
                    : theme.secondary
              }
            />
            {report.cost_ratio !== null && (
              <CompareCard
                label="Cost Ratio"
                value={`${report.cost_ratio.toFixed(2)}x`}
                sub={
                  report.score_per_dollar_baseline !== null &&
                  report.score_per_dollar_candidate !== null
                    ? `$/score: ${report.score_per_dollar_baseline.toFixed(4)} vs ${report.score_per_dollar_candidate.toFixed(4)}`
                    : ""
                }
                color={
                  report.cost_ratio <= 1.0
                    ? theme.success
                    : theme.warning
                }
              />
            )}
          </div>

          {/* Per-assertion table */}
          {report.assertion_comparisons.length > 0 && (
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
                Per-Assertion Comparison
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
                    <th style={thStyle}>Assertion</th>
                    <th style={thStyle}>Baseline</th>
                    <th style={thStyle}>Candidate</th>
                    <th style={thStyle}>Delta</th>
                    <th style={thStyle}>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {report.assertion_comparisons.map((ac) => (
                    <tr
                      key={ac.assertion_type}
                      style={{
                        borderBottom: `1px solid ${theme.border}`,
                      }}
                    >
                      <td style={tdStyle}>{ac.assertion_type}</td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        {(ac.baseline_mean * 100).toFixed(1)}%
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        {(ac.candidate_score * 100).toFixed(1)}%
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          textAlign: "center",
                          color:
                            ac.delta > 0
                              ? theme.success
                              : ac.delta < 0
                                ? theme.error
                                : theme.secondary,
                        }}
                      >
                        {ac.delta > 0 ? "+" : ""}
                        {(ac.delta * 100).toFixed(1)}%
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 600,
                            background:
                              ac.verdict === "better"
                                ? "rgba(63,185,80,0.15)"
                                : ac.verdict === "worse"
                                  ? "rgba(248,81,73,0.15)"
                                  : "rgba(125,133,144,0.15)",
                            color:
                              ac.verdict === "better"
                                ? theme.success
                                : ac.verdict === "worse"
                                  ? theme.error
                                  : theme.secondary,
                          }}
                        >
                          {ac.verdict.toUpperCase()}
                        </span>
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

function SelectGroup({
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

function CompareCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
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
      <div style={{ fontSize: 10, color: theme.muted, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
      {sub && (
        <div style={{ fontSize: 10, color: theme.muted, marginTop: 2 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  background: theme.surface,
  border: `1px solid ${theme.border}`,
  color: theme.text,
  padding: "8px 12px",
  borderRadius: 6,
  fontSize: 12,
  fontFamily:
    "'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace",
  minWidth: 180,
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
