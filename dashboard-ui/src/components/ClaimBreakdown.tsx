import { theme } from "../theme";

interface Claim {
  claim: string;
  supported: boolean;
  source?: string;
}

interface ClaimBreakdownProps {
  details: Record<string, unknown>;
}

export default function ClaimBreakdown({ details }: ClaimBreakdownProps) {
  const claims = (details.claims ?? details.results ?? []) as Claim[];

  if (!Array.isArray(claims) || claims.length === 0) {
    return (
      <div style={{ color: theme.muted, fontSize: 12, padding: 8, fontFamily: theme.fontUI }}>
        No claim data available.
      </div>
    );
  }

  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontSize: 12,
      }}
    >
      <thead>
        <tr style={{ borderBottom: `1px solid ${theme.border}` }}>
          <th
            style={{
              textAlign: "left",
              padding: "6px 8px",
              color: theme.secondary,
              fontWeight: 500,
              fontFamily: theme.fontUI,
            }}
          >
            Status
          </th>
          <th
            style={{
              textAlign: "left",
              padding: "6px 8px",
              color: theme.secondary,
              fontWeight: 500,
              fontFamily: theme.fontUI,
            }}
          >
            Claim
          </th>
          <th
            style={{
              textAlign: "left",
              padding: "6px 8px",
              color: theme.secondary,
              fontWeight: 500,
              fontFamily: theme.fontUI,
            }}
          >
            Source
          </th>
        </tr>
      </thead>
      <tbody>
        {claims.map((c, i) => (
          <tr
            key={i}
            style={{
              borderBottom: `1px solid ${theme.border}`,
            }}
          >
            <td style={{ padding: "6px 8px", width: 60 }}>
              <span
                style={{
                  color: c.supported ? theme.success : theme.error,
                  fontWeight: 600,
                  fontFamily: theme.fontUI,
                }}
              >
                {c.supported ? "PASS" : "FAIL"}
              </span>
            </td>
            <td style={{ padding: "6px 8px", color: theme.text, fontFamily: theme.fontUI }}>
              {c.claim}
            </td>
            <td style={{ padding: "6px 8px", color: theme.muted, fontFamily: theme.fontMono }}>
              {c.source ?? "--"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
