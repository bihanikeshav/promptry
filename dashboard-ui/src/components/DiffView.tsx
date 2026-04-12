import { theme } from "../theme";
import type { DiffLine } from "../api/types";

interface DiffViewProps {
  lines: DiffLine[];
  additions: number;
  deletions: number;
}

export default function DiffView({ lines, additions, deletions }: DiffViewProps) {
  return (
    <div>
      <div
        style={{
          padding: "8px 12px",
          background: theme.surface,
          border: `1px solid ${theme.border}`,
          borderRadius: "6px 6px 0 0",
          fontSize: 12,
          color: theme.secondary,
          display: "flex",
          gap: 12,
        }}
      >
        <span style={{ color: theme.success }}>+{additions}</span>
        <span style={{ color: theme.error }}>-{deletions}</span>
      </div>
      <div
        style={{
          border: `1px solid ${theme.border}`,
          borderTop: "none",
          borderRadius: "0 0 6px 6px",
          overflow: "auto",
          fontSize: 12,
          lineHeight: "20px",
        }}
      >
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: theme.fontMono,
          }}
        >
          <tbody>
            {lines.map((line, i) => {
              let bg: string = "transparent";
              let prefix: string = " ";
              let textColor: string = theme.text;

              if (line.type === "added") {
                bg = "rgba(74, 222, 128, 0.1)";
                prefix = "+";
                textColor = theme.success;
              } else if (line.type === "deleted") {
                bg = "rgba(248, 113, 113, 0.1)";
                prefix = "-";
                textColor = theme.error;
              }

              return (
                <tr key={i} style={{ background: bg }}>
                  <td
                    style={{
                      width: 40,
                      textAlign: "right",
                      padding: "0 8px",
                      color: theme.muted,
                      userSelect: "none",
                      borderRight: `1px solid ${theme.border}`,
                    }}
                  >
                    {line.old_num ?? ""}
                  </td>
                  <td
                    style={{
                      width: 40,
                      textAlign: "right",
                      padding: "0 8px",
                      color: theme.muted,
                      userSelect: "none",
                      borderRight: `1px solid ${theme.border}`,
                    }}
                  >
                    {line.new_num ?? ""}
                  </td>
                  <td
                    style={{
                      padding: "0 12px",
                      whiteSpace: "pre",
                      color: textColor,
                    }}
                  >
                    {prefix} {line.content}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
