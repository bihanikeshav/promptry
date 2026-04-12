import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { getPromptVersions, getPromptDiff } from "../api/client";
import type { PromptVersion, DiffResponse } from "../api/types";
import { theme } from "../theme";
import DiffView from "../components/DiffView";

export default function PromptDetail() {
  const { name } = useParams<{ name: string }>();
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [selectedV1, setSelectedV1] = useState<number | null>(null);
  const [selectedV2, setSelectedV2] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!name) return;
    setLoading(true);
    getPromptVersions(name)
      .then((data) => {
        const sorted = [...data.versions].sort(
          (a, b) => b.version - a.version
        );
        setVersions(sorted);
        // Default: compare latest vs previous
        if (sorted.length >= 2) {
          setSelectedV1(sorted[1].version);
          setSelectedV2(sorted[0].version);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [name]);

  // Load diff when selection changes
  useEffect(() => {
    if (!name || selectedV1 === null || selectedV2 === null) {
      setDiff(null);
      return;
    }
    getPromptDiff(name, selectedV1, selectedV2)
      .then(setDiff)
      .catch(() => setDiff(null));
  }, [name, selectedV1, selectedV2]);

  return (
    <div>
      {/* Breadcrumbs */}
      <div style={{ fontSize: 11, color: theme.muted, marginBottom: 4, fontFamily: theme.fontUI }}>
        <Link
          to="/prompts"
          style={{ color: theme.accent, textDecoration: "none" }}
        >
          Prompts
        </Link>
        {" / "}
        <span style={{ color: theme.text }}>{name}</span>
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
        {name}
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

      {!loading && (
        <div style={{ display: "flex", gap: 20 }}>
          {/* Version sidebar */}
          <div style={{ width: 240, flexShrink: 0 }}>
            <div
              style={{
                background: theme.surface,
                border: `1px solid ${theme.border}`,
                borderRadius: 6,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "10px 14px",
                  borderBottom: `1px solid ${theme.border}`,
                  fontSize: 12,
                  fontWeight: 600,
                  color: theme.text,
                  fontFamily: theme.fontUI,
                }}
              >
                Versions ({versions.length})
              </div>
              {versions.map((v) => {
                const isSelected =
                  v.version === selectedV1 || v.version === selectedV2;
                return (
                  <div
                    key={v.version}
                    style={{
                      padding: "8px 14px",
                      borderBottom: `1px solid ${theme.border}`,
                      background: isSelected
                        ? "rgba(249,115,22,0.08)"
                        : "transparent",
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                    onClick={() => {
                      // Click sets the "new" version; shift+click or if only 1 selected sets old
                      if (selectedV2 === v.version) return;
                      setSelectedV1(selectedV2);
                      setSelectedV2(v.version);
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span
                        style={{
                          color: isSelected ? theme.accent : theme.text,
                          fontWeight: isSelected ? 600 : 400,
                          fontFamily: theme.fontMono,
                        }}
                      >
                        v{v.version}
                      </span>
                      <span style={{ color: theme.muted, fontSize: 10, fontFamily: theme.fontMono }}>
                        {v.hash.substring(0, 8)}
                      </span>
                    </div>
                    <div style={{ color: theme.muted, fontSize: 10, marginTop: 2, fontFamily: theme.fontMono }}>
                      {new Date(v.created_at).toLocaleString()}
                    </div>
                    {v.tags.length > 0 && (
                      <div
                        style={{
                          display: "flex",
                          gap: 4,
                          marginTop: 4,
                          flexWrap: "wrap",
                        }}
                      >
                        {v.tags.map((t) => (
                          <span
                            key={t}
                            style={{
                              padding: "1px 5px",
                              background: "rgba(249,115,22,0.1)",
                              color: theme.accent,
                              borderRadius: 3,
                              fontSize: 9,
                              fontFamily: theme.fontUI,
                            }}
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Diff view */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {selectedV1 !== null && selectedV2 !== null && (
              <div
                style={{
                  marginBottom: 12,
                  fontSize: 12,
                  color: theme.secondary,
                  fontFamily: theme.fontUI,
                }}
              >
                Comparing <span style={{ fontFamily: theme.fontMono }}>v{selectedV1}</span> → <span style={{ fontFamily: theme.fontMono }}>v{selectedV2}</span>
              </div>
            )}
            {diff ? (
              <DiffView
                lines={diff.lines}
                additions={diff.additions}
                deletions={diff.deletions}
              />
            ) : versions.length < 2 ? (
              <div
                style={{
                  color: theme.muted,
                  padding: 32,
                  textAlign: "center",
                  background: theme.surface,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                }}
              >
                Need at least 2 versions to show a diff.
              </div>
            ) : (
              <div
                style={{
                  color: theme.muted,
                  padding: 32,
                  textAlign: "center",
                  background: theme.surface,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                }}
              >
                Select two versions to compare.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
