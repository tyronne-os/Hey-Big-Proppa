import { useEffect, useState } from "react";
import { api } from "../api";
import type { NewsArticle } from "../types";

const CORR_COLOR: Record<string, string> = {
  COACHES_SON: "#d9b45a",
  IB_CASCADE: "#ef4444",
  VOLUME_STACK: "#2ee6a6",
  SINGLE_HERO: "#a78bfa",
};

const CORR_LABEL: Record<string, string> = {
  COACHES_SON: "COACHES SON",
  IB_CASCADE: "IB CASCADE",
  VOLUME_STACK: "VOLUME STACK",
  SINGLE_HERO: "SINGLE HERO",
};

function InitialsAvatar({ name, size = 44 }: { name: string; size?: number }) {
  const initials = name
    .split(" ")
    .map((w) => w[0] ?? "")
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div
      style={{
        width: size, height: size, borderRadius: "50%",
        background: "linear-gradient(135deg, #3a2a52, #6a3a6a)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: size * 0.35, fontWeight: 800, color: "#d9b45a",
        flexShrink: 0, border: "1px solid #4a3a62",
        fontFamily: "var(--font-mono, monospace)",
      }}
    >
      {initials}
    </div>
  );
}

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? "#2ee6a6" : pct >= 80 ? "#d9b45a" : "#ef4444";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontFamily: "var(--font-mono, monospace)", fontSize: 10, fontWeight: 800,
      color, border: `1px solid ${color}33`, borderRadius: 4, padding: "2px 7px",
    }}>
      {pct}% <span style={{ fontSize: 8, opacity: 0.7 }}>JIMMY</span>
    </span>
  );
}

function ArticleCard({ article }: { article: NewsArticle }) {
  const [expanded, setExpanded] = useState(false);
  const color = CORR_COLOR[article.correlationType] ?? "#888";
  const label = CORR_LABEL[article.correlationType] ?? article.correlationType;
  const paragraphs = article.body.split("\n\n");

  return (
    <article style={{
      background: "var(--bp-card-bg)",
      border: `1px solid ${color}33`,
      borderRadius: 16,
      overflow: "hidden",
    }}>
      {/* masthead strip */}
      <div style={{
        background: `linear-gradient(90deg, ${color}18, transparent)`,
        borderBottom: `1px solid ${color}22`,
        padding: "8px 16px",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <span style={{
          fontFamily: "var(--font-mono, monospace)", fontSize: 8, fontWeight: 800,
          letterSpacing: "0.18em", color: color,
          border: `1px solid ${color}55`, borderRadius: 3, padding: "2px 6px",
        }}>
          {label}
        </span>
        <span style={{
          fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 800,
          letterSpacing: "0.14em", color: "var(--bp-muted)",
        }}>
          FRONTAL LOBE SPORTS
        </span>
        <span style={{ flex: 1 }} />
        <ConfidenceMeter value={article.confidence} />
        <span style={{ fontSize: 10, color: "var(--bp-muted)", fontFamily: "var(--font-mono, monospace)" }}>
          {article.legCount}-LEG
        </span>
      </div>

      {/* article header */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{ cursor: "pointer", padding: "14px 16px 12px" }}
      >
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          <InitialsAvatar name={article.awayTeam + " " + article.homeTeam} size={40} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{
              margin: "0 0 5px",
              fontSize: 14, fontWeight: 900, lineHeight: 1.25,
              background: "var(--bp-wordmark-gradient)",
              WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
              letterSpacing: "0.02em",
            }}>
              {article.headline}
            </h2>
            <p style={{ margin: "0 0 4px", fontSize: 11, color: "var(--bp-muted)", lineHeight: 1.4 }}>
              {article.deck}
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 10, color: "#d9b45a", fontStyle: "italic" }}>{article.byline}</span>
              <span style={{ fontSize: 10, color: "var(--bp-muted)" }}>
                {article.awayTeam} @ {article.homeTeam} · {article.gameDate} {article.gameTime}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* body -- expanded */}
      {expanded && (
        <div style={{ borderTop: `1px solid ${color}22`, padding: "14px 16px" }}>
          <p style={{
            margin: "0 0 6px",
            fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
            color: "var(--bp-muted)", fontFamily: "var(--font-mono, monospace)",
          }}>
            {article.dateline}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {paragraphs.map((p, i) => (
              <p key={i} style={{
                margin: 0, fontSize: 13, lineHeight: 1.7,
                color: "var(--bp-fg)",
                fontFamily: "'Georgia', 'Times New Roman', serif",
              }}>
                {p}
              </p>
            ))}
          </div>

          <div style={{
            marginTop: 16,
            padding: "10px 14px",
            background: `${color}11`,
            border: `1px solid ${color}44`,
            borderRadius: 8,
          }}>
            <p style={{
              margin: 0,
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 10, fontWeight: 800, letterSpacing: "0.1em",
              color: color,
            }}>
              {article.verdict}
            </p>
          </div>
        </div>
      )}
    </article>
  );
}

function PassedCard({ article }: { article: NewsArticle }) {
  return (
    <div style={{
      background: "var(--bp-card-bg)",
      border: "1px solid var(--bp-border)",
      borderRadius: 12, padding: "12px 16px",
      display: "flex", gap: 10, alignItems: "center",
      opacity: 0.55,
    }}>
      <span style={{
        fontFamily: "var(--font-mono, monospace)", fontSize: 9, fontWeight: 800,
        color: "var(--bp-muted)", border: "1px solid var(--bp-border)",
        borderRadius: 3, padding: "2px 6px", flexShrink: 0,
      }}>
        BIG PROPPA PASSES
      </span>
      <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>{article.passReason}</span>
    </div>
  );
}

export default function NewsTab() {
  const [articles, setArticles] = useState<NewsArticle[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.newsArticles()
      .then((r: { articles: NewsArticle[] }) => setArticles(r.articles))
      .catch(() => setError(true));
  }, []);

  const published = articles?.filter((a) => !a.passed) ?? [];
  const passed = articles?.filter((a) => a.passed) ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 900 }}>
      {/* FB NEWS masthead */}
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 18, fontWeight: 900, letterSpacing: "0.18em",
            background: "var(--bp-wordmark-gradient)",
            WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
          }}>
            FB NEWS
          </span>
          <span style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 9, fontWeight: 700, letterSpacing: "0.14em",
            color: "var(--bp-muted)",
          }}>
            FRONTAL LOBE SPORTS · BUDDY COSELL REPORTING
          </span>
        </div>
        <span style={{ fontSize: 11, color: "var(--bp-muted)" }}>
          Jimmy the Greek's lake-only scoops · FanDuel prices · HEURISTIC, NOT BACKTESTED
        </span>
      </div>

      {error && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          Buddy is unavailable — backend may be offline or no parlay slips generated this week.
        </div>
      )}

      {!error && !articles && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>Buddy is writing his column...</div>
      )}

      {published.map((a) => <ArticleCard key={a.slipId} article={a} />)}

      {passed.length > 0 && (
        <>
          <div style={{
            borderTop: "1px solid var(--bp-border)",
            paddingTop: 10,
            fontSize: 10, fontWeight: 800, letterSpacing: "0.12em",
            color: "var(--bp-muted)", fontFamily: "var(--font-mono, monospace)",
          }}>
            BIG PROPPA PASSES — INSUFFICIENT DATA FOR A CONVINCING COLUMN
          </div>
          {passed.map((a) => <PassedCard key={a.slipId} article={a} />)}
        </>
      )}

      {articles && published.length === 0 && passed.length === 0 && (
        <div style={{ color: "var(--bp-muted)", fontSize: 13 }}>
          No articles this week — no parlay slips cleared the publication threshold.
        </div>
      )}
    </div>
  );
}
