import { Link, useLocation } from "react-router-dom";

const TABS = [
  { id: "leaders",  label: "LEADERS · TARGETS", href: "/leaders?cat=targets" },
  { id: "matchups", label: "MATCHUPS",           href: "/matchups" },
  { id: "ramp",     label: "RAMP",               href: "/ramp" },
  { id: "college",  label: "COLLEGE",            href: "/college" },
  { id: "parlay",   label: "THROWDOWN THURSDAY", href: "/throwdown" },
  { id: "monday",       label: "MONDAY NIGHT",       href: "/monday" },
  { id: "sunday-night", label: "SUNDAY NIGHT",      href: "/sunday-night" },
  { id: "sunday",       label: "SUNDAY SLIPS",       href: "/parlays" },
  { id: "engine",   label: "ENGINE",             href: "/engine" },
  { id: "news",     label: "NEWS",               href: "/news" },
  { id: "queries",  label: "QUERIES",            href: "/queries" },
  { id: "myboo",    label: "MY BOO",             href: "/myboo" },
  { id: "odds",     label: "THE ODDS",           href: "/odds" },
] as const;

type NavBarProps = { activeTab?: string };

export default function NavBar({ activeTab }: NavBarProps) {
  const location = useLocation();

  // Detect active tab from URL
  const currentTab = activeTab ?? (() => {
    if (location.pathname === "/throwdown")    return "parlay";
    if (location.pathname === "/monday")       return "monday";
    if (location.pathname === "/sunday-night") return "sunday-night";
    if (location.pathname === "/parlays")      return "sunday";
    const seg = location.pathname.replace(/^\//, "");
    if (seg && (["leaders","matchups","ramp","college","engine","news","queries","myboo","odds"] as string[]).includes(seg)) return seg;
    return "parlay";
  })();

  return (
    <div style={{
      display: "flex", gap: 6, padding: "8px 20px 10px", flexWrap: "wrap", flex: "0 0 auto",
      borderBottom: "1px solid var(--bp-border)",
    }}>
      <a
        href="/home/index.html"
        style={{
          display: "inline-flex", alignItems: "center",
          height: 32, padding: "0 14px", borderRadius: 999,
          border: "1px solid #c9a54e", background: "rgba(201,165,78,0.14)",
          color: "#f1dc92", fontSize: 12, fontWeight: 800, letterSpacing: "0.1em",
          textDecoration: "none", cursor: "pointer",
        }}
      >
        HOME
      </a>
      {TABS.map(({ id, label, href }) => {
        const isBoo = id === "myboo";
        const isActive = id === currentTab;
        return (
          <Link
            key={id}
            to={href}
            style={{
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
            }}
          >
            {label}
          </Link>
        );
      })}
    </div>
  );
}
