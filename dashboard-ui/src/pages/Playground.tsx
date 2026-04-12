import { useState } from "react";
import { runPlaygroundEval } from "../api/client";
import type {
  PlaygroundAssertionDef,
  PlaygroundAssertionResult,
  PlaygroundEvalResponse,
} from "../api/types";
import { theme } from "../theme";

type AssertionType = PlaygroundAssertionDef["type"];

const ASSERTION_TYPES: { value: AssertionType; label: string }[] = [
  { value: "contains", label: "Contains keywords" },
  { value: "not_contains", label: "Does not contain" },
  { value: "json_valid", label: "Valid JSON" },
  { value: "matches", label: "Regex match" },
];

interface AssertionRow {
  id: number;
  type: AssertionType;
  value: string;
}

let nextId = 1;

function newAssertion(): AssertionRow {
  return { id: nextId++, type: "contains", value: "" };
}

export default function Playground() {
  const [systemPrompt, setSystemPrompt] = useState("");
  const [mockResponse, setMockResponse] = useState("");
  const [assertions, setAssertions] = useState<AssertionRow[]>([newAssertion()]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evalResult, setEvalResult] = useState<PlaygroundEvalResponse | null>(null);

  const addAssertion = () => {
    setAssertions((prev) => [...prev, newAssertion()]);
  };

  const removeAssertion = (id: number) => {
    setAssertions((prev) => prev.filter((a) => a.id !== id));
  };

  const updateAssertion = (id: number, field: keyof AssertionRow, value: string) => {
    setAssertions((prev) =>
      prev.map((a) => (a.id === id ? { ...a, [field]: value } : a)),
    );
  };

  const handleRun = async () => {
    if (!mockResponse.trim()) {
      setError("Please provide a mock response to evaluate.");
      return;
    }
    if (assertions.length === 0) {
      setError("Add at least one assertion.");
      return;
    }

    setLoading(true);
    setError(null);
    setEvalResult(null);

    try {
      const defs: PlaygroundAssertionDef[] = assertions.map((a) => {
        if (a.type === "contains" || a.type === "not_contains") {
          const keywords = a.value
            .split(",")
            .map((k) => k.trim())
            .filter(Boolean);
          return { type: a.type, value: keywords };
        }
        if (a.type === "matches") {
          return { type: a.type, value: a.value, options: { fullmatch: false } };
        }
        // json_valid needs no value
        return { type: a.type };
      });

      const result = await runPlaygroundEval(mockResponse, defs);
      setEvalResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontFamily: theme.fontUI }}>
        Playground
      </div>
      <h1
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: theme.text,
          marginBottom: 20,
          fontFamily: theme.fontUI,
        }}
      >
        Prompt Playground
      </h1>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 20,
          alignItems: "start",
        }}
      >
        {/* Left panel: Input */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* System prompt */}
          <div
            style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              padding: 16,
            }}
          >
            <label
              style={{
                display: "block",
                fontSize: 10,
                color: theme.muted,
                marginBottom: 6,
                textTransform: "uppercase",
                fontFamily: theme.fontUI,
              }}
            >
              System Prompt (reference only)
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="You are a helpful assistant..."
              rows={4}
              style={textareaStyle}
            />
          </div>

          {/* Mock response */}
          <div
            style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              padding: 16,
            }}
          >
            <label
              style={{
                display: "block",
                fontSize: 10,
                color: theme.muted,
                marginBottom: 6,
                textTransform: "uppercase",
                fontFamily: theme.fontUI,
              }}
            >
              Mock Response (paste what the LLM would say)
            </label>
            <textarea
              value={mockResponse}
              onChange={(e) => setMockResponse(e.target.value)}
              placeholder="Paste the LLM output to evaluate..."
              rows={8}
              style={textareaStyle}
            />
          </div>

          {/* Assertions */}
          <div
            style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              padding: 16,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 12,
              }}
            >
              <label
                style={{
                  fontSize: 10,
                  color: theme.muted,
                  textTransform: "uppercase",
                  fontFamily: theme.fontUI,
                }}
              >
                Assertions
              </label>
              <button onClick={addAssertion} style={addBtnStyle}>
                + Add
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {assertions.map((a) => (
                <div
                  key={a.id}
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                  }}
                >
                  <select
                    value={a.type}
                    onChange={(e) =>
                      updateAssertion(a.id, "type", e.target.value)
                    }
                    style={selectStyle}
                  >
                    {ASSERTION_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>

                  {a.type !== "json_valid" && (
                    <input
                      type="text"
                      value={a.value}
                      onChange={(e) =>
                        updateAssertion(a.id, "value", e.target.value)
                      }
                      placeholder={
                        a.type === "matches"
                          ? "regex pattern"
                          : "keyword1, keyword2, ..."
                      }
                      style={inputStyle}
                    />
                  )}
                  {a.type === "json_valid" && (
                    <span
                      style={{
                        flex: 1,
                        fontSize: 11,
                        color: theme.muted,
                        fontFamily: theme.fontUI,
                      }}
                    >
                      Checks if response is valid JSON
                    </span>
                  )}

                  <button
                    onClick={() => removeAssertion(a.id)}
                    style={removeBtnStyle}
                    title="Remove assertion"
                  >
                    x
                  </button>
                </div>
              ))}
              {assertions.length === 0 && (
                <div
                  style={{
                    fontSize: 12,
                    color: theme.muted,
                    fontFamily: theme.fontUI,
                    padding: "8px 0",
                  }}
                >
                  No assertions defined. Click "+ Add" to create one.
                </div>
              )}
            </div>
          </div>

          {/* Run button */}
          <button
            onClick={handleRun}
            disabled={loading}
            style={{
              background: theme.accent,
              color: "#fff",
              border: "none",
              padding: "10px 24px",
              borderRadius: 6,
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: 13,
              fontFamily: theme.fontUI,
              fontWeight: 600,
              opacity: loading ? 0.6 : 1,
              alignSelf: "flex-start",
            }}
          >
            {loading ? "Running..." : "Run"}
          </button>
        </div>

        {/* Right panel: Output */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Raw response preview */}
          <div
            style={{
              background: theme.surface,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              padding: 16,
            }}
          >
            <label
              style={{
                display: "block",
                fontSize: 10,
                color: theme.muted,
                marginBottom: 6,
                textTransform: "uppercase",
                fontFamily: theme.fontUI,
              }}
            >
              Response Preview
            </label>
            <pre
              style={{
                fontFamily: theme.fontMono,
                fontSize: 12,
                color: theme.text,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
                minHeight: 80,
                maxHeight: 300,
                overflow: "auto",
              }}
            >
              {mockResponse || (
                <span style={{ color: theme.muted }}>
                  Response will appear here...
                </span>
              )}
            </pre>
          </div>

          {/* Error */}
          {error && (
            <div
              style={{
                color: theme.error,
                padding: 16,
                background: "rgba(248,113,113,0.1)",
                borderRadius: 6,
                fontSize: 13,
                fontFamily: theme.fontUI,
              }}
            >
              {error}
            </div>
          )}

          {/* Results */}
          {evalResult && (
            <div
              style={{
                background: theme.surface,
                border: `1px solid ${theme.border}`,
                borderRadius: 6,
                padding: 16,
              }}
            >
              {/* Overall score banner */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  marginBottom: 16,
                  paddingBottom: 12,
                  borderBottom: `1px solid ${theme.border}`,
                }}
              >
                <div
                  style={{
                    fontSize: 24,
                    fontWeight: 700,
                    fontFamily: theme.fontMono,
                    color: evalResult.overall_passed
                      ? theme.success
                      : theme.error,
                  }}
                >
                  {(evalResult.overall_score * 100).toFixed(0)}%
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      fontFamily: theme.fontUI,
                      color: evalResult.overall_passed
                        ? theme.success
                        : theme.error,
                    }}
                  >
                    {evalResult.overall_passed ? "ALL PASSED" : "SOME FAILED"}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: theme.secondary,
                      fontFamily: theme.fontUI,
                    }}
                  >
                    {evalResult.passed_count}/{evalResult.total_count} assertions passed
                  </div>
                </div>
              </div>

              {/* Per-assertion results */}
              <label
                style={{
                  display: "block",
                  fontSize: 10,
                  color: theme.muted,
                  marginBottom: 8,
                  textTransform: "uppercase",
                  fontFamily: theme.fontUI,
                }}
              >
                Assertion Results
              </label>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {evalResult.results.map((r: PlaygroundAssertionResult) => (
                  <div
                    key={r.index}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      padding: "8px 10px",
                      borderRadius: 4,
                      background: r.passed
                        ? "rgba(74,222,128,0.08)"
                        : "rgba(248,113,113,0.08)",
                      border: `1px solid ${r.passed ? "rgba(74,222,128,0.2)" : "rgba(248,113,113,0.2)"}`,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: r.passed ? theme.success : theme.error,
                        fontFamily: theme.fontMono,
                        flexShrink: 0,
                        marginTop: 1,
                      }}
                    >
                      {r.passed ? "PASS" : "FAIL"}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: theme.text,
                          fontFamily: theme.fontUI,
                          marginBottom: 2,
                        }}
                      >
                        {r.type}
                        <span
                          style={{
                            marginLeft: 8,
                            fontSize: 11,
                            fontWeight: 400,
                            color: theme.secondary,
                            fontFamily: theme.fontMono,
                          }}
                        >
                          score: {r.score.toFixed(2)}
                        </span>
                      </div>
                      {r.details && Object.keys(r.details).length > 0 && (
                        <pre
                          style={{
                            fontSize: 10,
                            fontFamily: theme.fontMono,
                            color: theme.secondary,
                            margin: 0,
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                          }}
                        >
                          {JSON.stringify(r.details, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const textareaStyle: React.CSSProperties = {
  width: "100%",
  background: theme.bg,
  border: `1px solid ${theme.border}`,
  color: theme.text,
  fontFamily: theme.fontMono,
  fontSize: 12,
  padding: "10px 12px",
  borderRadius: 4,
  resize: "vertical",
  outline: "none",
  boxSizing: "border-box",
};

const selectStyle: React.CSSProperties = {
  background: theme.surface,
  border: `1px solid ${theme.border}`,
  color: theme.text,
  padding: "6px 10px",
  borderRadius: 4,
  fontSize: 12,
  fontFamily: theme.fontUI,
  minWidth: 160,
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  background: theme.bg,
  border: `1px solid ${theme.border}`,
  color: theme.text,
  padding: "6px 10px",
  borderRadius: 4,
  fontSize: 12,
  fontFamily: theme.fontMono,
  outline: "none",
};

const addBtnStyle: React.CSSProperties = {
  background: "transparent",
  border: `1px solid ${theme.border}`,
  color: theme.secondary,
  padding: "4px 12px",
  borderRadius: 4,
  fontSize: 11,
  fontFamily: theme.fontUI,
  cursor: "pointer",
};

const removeBtnStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: theme.muted,
  padding: "4px 8px",
  fontSize: 13,
  fontFamily: theme.fontMono,
  cursor: "pointer",
  flexShrink: 0,
};
