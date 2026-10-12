import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

const TOP_TABS = [
  { id: "leaders", label: "LEADERS · TARGETS", href: "/leaders?cat=targets" },
  { id: "parlay",  label: "PARLAY",             href: "/parlay" },
  { id: "myboo",   label: "MY BOO",             href: "/myboo" },
] as const;

// Everything else lives under THE ODDS as a dropdown.
const ODDS_MENU = [
  { id: "odds",         label: "THE ODDS",           href: "/odds" },
  { id: "matchups",     label: "MATCHUPS",           href: "/matchups" },
  { id: "ramp",         label: "RAMP",               href: "/ramp" },
  { id: "college",      label: "COLLEGE",            href: "/college" },
  { id: "throwdown",    label: "THROWDOWN THURSDAY", href: "/throwdown" },
  { id: "sunday-night", label: "SUNDAY NIGHT",       href: "/sunday-night" },
  { id: "sunday",       label: "SUNDAY SLIPS",       href: "/parlays" },
  { id: "engine",       label: "ENGINE",             href: "/engine" },
  { id: "news",         label: "NEWS",               href: "/news" },
  { id: "queries",      label: "QUERIES",            href: "/queries" },
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
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Detect active tab from URL
  const currentTab = activeTab ?? (() => {
    if (location.pathname === "/throwdown")    return "throwdown";
    if (location.pathname === "/parlay")       return "parlay";
    if (location.pathname === "/monday")       return "monday";
    if (location.pathname === "/sunday-night") return "sunday-night";
    if (location.pathname === "/parlays")      return "sunday";
    const seg = location.pathname.replace(/^\//, "");
    if (seg && (["leaders","matchups","ramp","college","engine","news","queries","myboo","odds"] as string[]).includes(seg)) return seg;
    return "parlay";
  })();

  const oddsActive = ODDS_MENU.some((m) => m.id === currentTab);

  useEffect(() => { setOpen(false); }, [location.pathname, location.search]);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div style={{
      display: "flex", gap: 6, padding: "8px 20px 10px", flexWrap: "wrap", flex: "0 0 auto",
      justifyContent: "center", borderBottom: "1px solid var(--bp-border)",
    }}>
      <a
        href="/home/index.html"
        style={{
          ...pill(true),
          fontWeight: 800,
        }}
      >
        HOME
      </a>
      {TOP_TABS.map(({ id, label, href }) => (
        <Link key={id} to={href} style={pill(id === currentTab, id === "myboo")}>
          {label}
        </Link>
      ))}
      <div ref={menuRef} style={{ position: "relative" }}>
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          style={{ ...pill(oddsActive || open), font: "inherit", fontSize: 12, fontWeight: 700, letterSpacing: "0.1em" }}
        >
          THE ODDS <span style={{ marginLeft: 6, fontSize: 10 }}>{open ? "▴" : "▾"}</span>
        </button>
        {open && (
          <div
            role="menu"
            style={{
              position: "absolute", top: 38, left: "50%", transform: "translateX(-50%)", zIndex: 50,
              minWidth: 220, display: "flex", flexDirection: "column", gap: 2, padding: 6,
              background: "var(--bp-card-bg)", border: "1px solid #c9a54e", borderRadius: 12,
              boxShadow: "0 12px 32px rgba(0,0,0,0.5)",
            }}
          >
            {ODDS_MENU.map(({ id, label, href }) => {
              const isActive = id === currentTab;
              return (
                <Link
                  key={id}
                  to={href}
                  role="menuitem"
                  style={{
                    padding: "8px 12px", borderRadius: 8, fontSize: 12, fontWeight: 700, letterSpacing: "0.1em",
                    textDecoration: "none", whiteSpace: "nowrap",
                    color: isActive ? "#f1dc92" : "var(--bp-fg)",
                    background: isActive ? "rgba(201,165,78,0.14)" : "transparent",
                  }}
                >
                  {label}
                </Link>
              );
            })}
          </div>
        )}
      </div>
      <Link to="/monday" style={pill(currentTab === "monday")}>
        MONDAY NIGHT
      </Link>
    </div>
  );
}
