import { NavLink, Outlet } from "react-router-dom";
import { theme } from "../theme";

const navItems = [
  { to: "/", label: "Overview" },
  { to: "/prompts", label: "Prompts" },
  { to: "/models", label: "Models" },
  { to: "/cost", label: "Cost" },
  { to: "/playground", label: "Playground" },
];

export default function Layout() {
  const port =
    new URLSearchParams(window.location.search).get("port") || "8420";

  return (
    <div style={{ minHeight: "100vh", background: theme.bg, fontFamily: theme.fontUI }}>
      {/* Top bar */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 24px",
          height: 44,
          borderBottom: `1px solid ${theme.border}`,
          background: theme.surface,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <NavLink
            to="/"
            style={{
              color: theme.text,
              textDecoration: "none",
              fontWeight: 700,
              fontSize: 15,
              fontFamily: theme.fontUI,
            }}
          >
            <span>prompt</span>
            <span style={{ color: theme.accent }}>ry</span>
          </NavLink>
          <nav style={{ display: "flex", gap: 16 }}>
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                style={({ isActive }) => ({
                  color: isActive ? theme.accent : theme.secondary,
                  textDecoration: "none",
                  fontSize: 13,
                  fontFamily: theme.fontUI,
                  padding: "4px 0",
                  borderBottom: isActive
                    ? `2px solid ${theme.accent}`
                    : "2px solid transparent",
                })}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <span style={{ color: theme.muted, fontSize: 12, fontFamily: theme.fontMono }}>
          localhost:{port}
        </span>
      </header>

      {/* Main content */}
      <main style={{ padding: 24, maxWidth: 1200, margin: "0 auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
