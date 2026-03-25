import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getPrompts } from "../api/client";
import type { PromptSummary } from "../api/types";
import { theme } from "../theme";

export default function Prompts() {
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getPrompts()
      .then(setPrompts)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4 }}>
        Prompts
      </div>
      <h1
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: theme.text,
          marginBottom: 20,
        }}
      >
        Prompt Registry
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

      {!loading && prompts.length === 0 && !error && (
        <div style={{ color: theme.muted, padding: 32, textAlign: "center" }}>
          No prompts found.
        </div>
      )}

      {!loading && prompts.length > 0 && (
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
              fontFamily: theme.font,
            }}
          >
            <thead>
              <tr
                style={{
                  background: theme.surface,
                  borderBottom: `1px solid ${theme.border}`,
                }}
              >
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Latest Version</th>
                <th style={thStyle}>Tags</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map((p) => (
                <tr
                  key={p.name}
                  onClick={() =>
                    navigate(`/prompts/${encodeURIComponent(p.name)}`)
                  }
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
                  <td style={{ ...tdStyle, fontWeight: 600, color: theme.accent }}>
                    {p.name}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "center" }}>
                    v{p.latest_version}
                  </td>
                  <td style={tdStyle}>
                    {p.tags.length > 0 ? (
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {p.tags.map((t) => (
                          <span
                            key={t}
                            style={{
                              padding: "2px 8px",
                              background: "rgba(88,166,255,0.1)",
                              color: theme.accent,
                              borderRadius: 4,
                              fontSize: 11,
                            }}
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: theme.muted }}>--</span>
                    )}
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
  padding: "8px 12px",
  fontWeight: 500,
  color: "#7d8590",
  fontSize: 12,
  textAlign: "left",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px",
  whiteSpace: "nowrap",
};
