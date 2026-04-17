import { useState, useEffect } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { getRunDiff } from "../api/client";
import type {
  RunDiff as RunDiffData,
  RunDiffTest,
  RunDiffAssertion,
  RunDiffRunMeta,
} from "../api/types";
import { theme, scoreColor } from "../theme";

export default function RunDiff() {
  const { name } = useParams<{ name: string }>();
  const [params] = useSearchParams();
  const currentId = params.get("current");
  const baselineId = params.get("baseline");

  const [data, setData] = useState<RunDiffData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!currentId || !baselineId) {
      setError("Missing current or baseline run id");
      setLoading(false);
      return;
    }
    setLoading(true);
    getRunDiff(parseInt(currentId, 10), parseInt(baselineId, 10))
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [currentId, baselineId]);

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div>
      {/* Breadcrumbs */}
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontFamily: theme.fontUI }}>
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
        <span style={{ color: theme.text }}>Diff</span>
      </div>

      <h1 style={{ fontSize: 18, fontWeight: 600, color: theme.text, marginBottom: 20, fontFamily: theme.fontUI }}>
        Run Diff
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
            background: "rgba(248,113,113,0.1)",
            borderRadius: 6,
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {!loading && data && (
        <>
          {/* Header: current vs baseline */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto 1fr",
              gap: 12,
              marginBottom: 20,
              alignItems: "stretch",
            }}
          >
            <RunCard label="Baseline" meta={data.baseline} suite={name ?? ""} />
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: theme.muted,
                fontFamily: theme.fontUI,
                fontSize: 18,
                padding: "0 8px",
              }}
            >
              →
            </div>
            <RunCard label="Current" meta={data.current} suite={name ?? ""} />
          </div>

          {/* Overall delta */}
          <div
            style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              padding: "12px 16px",
              marginBottom: 20,
              display: "flex",
              gap: 24,
              flexWrap: "wrap",
            }}
          >
            <DeltaStat
              label="Score Delta"
              value={
                data.score_delta !== null
                  ? (data.score_delta >= 0 ? "+" : "") +
                    (data.score_delta * 100).toFixed(1) +
                    "%"
                  : "--"
              }
              color={deltaColor(data.score_delta)}
            />
            <DeltaStat
              label="Regressed"
              value={String(data.summary.regressed)}
              color={data.summary.regressed > 0 ? theme.error : theme.muted}
            />
            <DeltaStat
              label="Improved"
              value={String(data.summary.improved)}
              color={data.summary.improved > 0 ? theme.success : theme.muted}
            />
            <DeltaStat
              label="Unchanged"
              value={String(data.summary.unchanged)}
              color={theme.secondary}
            />
            <DeltaStat
              label="Total Tests"
              value={String(data.summary.total)}
              color={theme.text}
            />
          </div>

          {/* Test diff cards */}
          {data.tests.length === 0 && (
            <div
              style={{
                color: theme.muted,
                padding: 24,
                textAlign: "center",
                fontSize: 13,
                fontFamily: theme.fontUI,
              }}
            >
              No tests to compare.
            </div>
          )}

          {data.tests.map((test) => (
            <TestDiffCard
              key={test.name}
              test={test}
              expanded={expanded}
              toggle={toggle}
            />
          ))}
        </>
      )}
    </div>
  );
}

function RunCard({
  label,
  meta,
  suite,
}: {
  label: string;
  meta: RunDiffRunMeta;
  suite: string;
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
      <div
        style={{
          fontSize: 10,
          color: theme.muted,
          marginBottom: 6,
          textTransform: "uppercase",
          letterSpacing: 0.6,
          fontFamily: theme.fontUI,
        }}
      >
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
        <Link
          to={`/suite/${encodeURIComponent(suite)}/run/${meta.id}`}
          style={{
            color: theme.accent,
            textDecoration: "none",
            fontSize: 15,
            fontWeight: 700,
            fontFamily: theme.fontMono,
          }}
        >
          #{meta.id}
        </Link>
        <span
          style={{
            color: scoreColor(meta.score),
            fontWeight: 700,
            fontSize: 15,
            fontFamily: theme.fontMono,
          }}
        >
          {meta.score !== null ? (meta.score * 100).toFixed(1) + "%" : "--"}
        </span>
        <span
          style={{
            color: meta.overall_pass ? theme.success : theme.error,
            fontWeight: 600,
            fontSize: 11,
            fontFamily: theme.fontUI,
          }}
        >
          {meta.overall_pass ? "PASS" : "FAIL"}
        </span>
      </div>
      <div style={{ fontSize: 11, color: theme.secondary, fontFamily: theme.fontMono }}>
        {meta.model_version ?? "--"}
        {meta.prompt_name
          ? ` · ${meta.prompt_name} v${meta.prompt_version ?? "?"}`
          : ""}
      </div>
      <div style={{ fontSize: 11, color: theme.muted, fontFamily: theme.fontMono }}>
        {new Date(meta.timestamp).toLocaleString()}
      </div>
    </div>
  );
}

function DeltaStat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div>
      <div style={{ fontSize: 10, color: theme.muted, marginBottom: 2, fontFamily: theme.fontUI }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color, fontFamily: theme.fontMono }}>
        {value}
      </div>
    </div>
  );
}

function TestDiffCard({
  test,
  expanded,
  toggle,
}: {
  test: RunDiffTest;
  expanded: Set<string>;
  toggle: (k: string) => void;
}) {
  const accent = statusColor(test.status);
  return (
    <div
      style={{
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderLeft: `3px solid ${accent}`,
        borderRadius: 6,
        marginBottom: 12,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "10px 16px",
          borderBottom: `1px solid ${theme.border}`,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: theme.text,
            fontFamily: theme.fontUI,
          }}
        >
          {test.name}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: accent,
            textTransform: "uppercase",
            letterSpacing: 0.6,
            fontFamily: theme.fontUI,
            padding: "2px 8px",
            border: `1px solid ${accent}`,
            borderRadius: 4,
          }}
        >
          {test.status}
        </span>
      </div>

      {test.assertions.map((a, idx) => {
        const key = `${test.name}::${a.type}::${idx}`;
        return (
          <AssertionDiffRow
            key={key}
            assertion={a}
            expanded={expanded.has(key)}
            onToggle={() => toggle(key)}
          />
        );
      })}
    </div>
  );
}

function AssertionDiffRow({
  assertion,
  expanded,
  onToggle,
}: {
  assertion: RunDiffAssertion;
  expanded: boolean;
  onToggle: () => void;
}) {
  const change = assertion.status_change;
  const rowColor = statusColor(change);
  const baseline = assertion.baseline;
  const current = assertion.current;

  const baselineScore =
    baseline && baseline.score !== null
      ? (baseline.score * 100).toFixed(0) + "%"
      : baseline
        ? "--"
        : "—";
  const currentScore =
    current && current.score !== null
      ? (current.score * 100).toFixed(0) + "%"
      : current
        ? "--"
        : "—";
  const deltaText =
    assertion.score_delta !== null
      ? (assertion.score_delta >= 0 ? "+" : "") +
        (assertion.score_delta * 100).toFixed(1) +
        "%"
      : "";

  return (
    <div>
      <div
        onClick={onToggle}
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
          (e.currentTarget.style.background = "rgba(249,115,22,0.04)")
        }
        onMouseLeave={(e) =>
          (e.currentTarget.style.background = "transparent")
        }
      >
        <span
          style={{
            color: theme.secondary,
            width: 120,
            fontFamily: theme.fontUI,
          }}
        >
          {assertion.type}
        </span>

        {/* Baseline side */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            width: 120,
            fontFamily: theme.fontMono,
          }}
        >
          <StatusPill pass={baseline?.passed ?? null} />
          <span
            style={{
              color:
                baseline && baseline.score !== null
                  ? scoreColor(baseline.score)
                  : theme.muted,
              fontWeight: 600,
            }}
          >
            {baselineScore}
          </span>
        </span>

        <span style={{ color: theme.muted, fontFamily: theme.fontUI }}>→</span>

        {/* Current side */}
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            width: 120,
            fontFamily: theme.fontMono,
          }}
        >
          <StatusPill pass={current?.passed ?? null} />
          <span
            style={{
              color:
                current && current.score !== null
                  ? scoreColor(current.score)
                  : theme.muted,
              fontWeight: 600,
            }}
          >
            {currentScore}
          </span>
        </span>

        {/* Delta */}
        <span
          style={{
            color: rowColor,
            fontWeight: 700,
            fontFamily: theme.fontMono,
            marginLeft: 8,
            minWidth: 70,
          }}
        >
          {deltaText}
        </span>

        {/* Change label */}
        <span
          style={{
            marginLeft: "auto",
            fontSize: 10,
            fontWeight: 700,
            color: rowColor,
            textTransform: "uppercase",
            letterSpacing: 0.6,
            fontFamily: theme.fontUI,
          }}
        >
          {change === "none" ? "unchanged" : change}
        </span>

        <span style={{ color: theme.muted, marginLeft: 8 }}>
          {expanded ? "▼" : "▶"}
        </span>
      </div>

      {expanded && (
        <div
          style={{
            padding: "12px 16px",
            borderBottom: `1px solid ${theme.border}`,
            background: "rgba(0,0,0,0.15)",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <DetailsColumn label="Baseline" side={baseline} />
          <DetailsColumn label="Current" side={current} />
        </div>
      )}
    </div>
  );
}

function DetailsColumn({
  label,
  side,
}: {
  label: string;
  side: RunDiffAssertion["baseline"];
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          color: theme.muted,
          marginBottom: 6,
          textTransform: "uppercase",
          letterSpacing: 0.6,
          fontFamily: theme.fontUI,
        }}
      >
        {label}
      </div>
      {side === null ? (
        <div style={{ color: theme.muted, fontSize: 11, fontFamily: theme.fontMono }}>
          (not present)
        </div>
      ) : (
        <pre
          style={{
            color: theme.secondary,
            fontSize: 11,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
            fontFamily: theme.fontMono,
          }}
        >
          {JSON.stringify(side.details ?? {}, null, 2)}
        </pre>
      )}
    </div>
  );
}

function StatusPill({ pass }: { pass: boolean | null }) {
  if (pass === null) {
    return (
      <span
        style={{
          color: theme.muted,
          fontWeight: 700,
          fontSize: 10,
          fontFamily: theme.fontUI,
        }}
      >
        —
      </span>
    );
  }
  return (
    <span
      style={{
        color: pass ? theme.success : theme.error,
        fontWeight: 700,
        fontSize: 10,
        fontFamily: theme.fontUI,
      }}
    >
      {pass ? "PASS" : "FAIL"}
    </span>
  );
}

function statusColor(status: string): string {
  switch (status) {
    case "regressed":
      return theme.error;
    case "improved":
    case "passed":
      return theme.success;
    case "unchanged":
    case "none":
    default:
      return theme.secondary;
  }
}

function deltaColor(d: number | null): string {
  if (d === null) return theme.muted;
  if (d > 0.005) return theme.success;
  if (d < -0.005) return theme.error;
  return theme.secondary;
}
