import { Link, useLocation } from "react-router-dom";

const TOP_TABS = [
  { id: "leaders", label: "LEADERS", href: "/leaders?cat=targets" },
  { id: "parlay",  label: "PARLAY",  href: "/parlay" },
  { id: "jimmy",   label: "JIMMY",   href: "/jimmy" },
  { id: "betterverse", label: "BETTER-VERSE", href: "/betterverse" },
  { id: "myboo",   label: "MY BOO",  href: "/myboo" },
] as const;

type NavBarProps = { activeTab?: string };

const pill = (isActive: boolean, isBoo = false) => ({
  display: "inline-flex", alignItems: "center",
  height: 32, padding: "0 14px", borderRadius: 999,
  border: `1px solid ${isActive ? (isBoo ? "#a78bfa" : "#c9a54e") : (isBoo ? "#3a2060" : "var(--bp-border)")}`,
  background: isActive
    ? (isBoo ? "rgba(139,92,246,0.18)" : "rgba(201,165,78,0.14)")
    : (isBoo ? "rgba(139,92,246,0.06)" : "var(--bp-card-bg)"),
  color: isActive ? (isBoo ? "#c4b5fd" : "#f1dc92") : (isBoo ? "#9d72ff" : "var(--bp-fg)"),
  fontSize: 12, fontWeight: 700, letterSpacing: "0.1em",
  textDecoration: "none", cursor: "pointer",
  transition: "background 0.15s, border-color 0.15s",
} as const);

export default function NavBar({ activeTab }: NavBarProps) {
  const location = useLocation();
  const p = location.pathname;
  const currentTab = activeTab ?? (p.startsWith("/leaders") || p.startsWith("/player") ? "leaders"
    : p === "/parlay" || p === "/throwdown" || p === "/monday" || p === "/sunday-night" || p === "/parlays" ? "parlay"
    : p.startsWith("/jimmy") ? "jimmy"
    : p.startsWith("/betterverse") ? "betterverse"
    : p.startsWith("/myboo") ? "myboo" : "");

  return (
    <div style={{
      display: "flex", gap: 6, padding: "8px 20px 10px", flexWrap: "wrap", flex: "0 0 auto",
      justifyContent: "center", borderBottom: "1px solid var(--bp-border)",
    }}>
      <a href="/home/index.html" style={{ ...pill(false), fontWeight: 800 }}>HOME</a>
      {TOP_TABS.map(({ id, label, href }) => (
        <Link key={id} to={href} style={pill(id === currentTab, id === "myboo")}>{label}</Link>
      ))}
    </div>
  );
}
