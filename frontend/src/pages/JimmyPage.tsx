/**
 * JIMMY: NFL Prop Betting Backtester & Video Game
 *
 * Time-travel simulator: user selects 1-5 slips, locks them for entire season,
 * then watches the season play out from Friday of Week 1 through Super Bowl.
 * Features: achievements, leaderboards, hot/cold indicators, risk scoring, MY BOO analysis.
 *
 * Video Game Mechanics:
 * - Football field background with ambient animation
 * - Slip building with pop/glow animations
 * - Win streaks unlock special slip types (underdog meta, spread ticks, etc.)
 * - Jimmy discovers patterns the player can then use
 * - Ticket editing unlocks at 3+ win streaks
 */
import React, { useState, useEffect } from "react";
import JimmyWeeklyRecap from "../components/JimmyWeeklyRecap";
import "./JimmyPage.css";

interface SeasonState {
  year: number;
  slips_per_week: number;
  current_week: number;
  bankroll: number;
  total_wagered: number;
  total_won: number;
  win_streak: number;
  loss_streak: number;
  achievements: string[];
  slips: any[];
  jimmy_discovered_patterns?: {
    underdog_meta?: boolean;
    sharp_tick?: boolean;
    prop_correlation?: boolean;
  };
}

function getCSTTime(): string {
  const now = new Date();
  const cstTime = now.toLocaleString("en-US", { timeZone: "America/Chicago" });
  return cstTime;
}

export default function JimmyPage() {
  const [page, setPage] = useState<"select" | "dashboard" | "builder" | "ticker" | "end">("select");
  const [season, setSeason] = useState<number | null>(null);
  const [slipsPerWeek, setSlipsPerWeek] = useState(1);
  const [state, setState] = useState<SeasonState | null>(null);
  const [loading, setLoading] = useState(false);
  const [cstTime, setCSTTime] = useState(getCSTTime());
  const [showRecap, setShowRecap] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => setCSTTime(getCSTTime()), 1000);
    return () => clearInterval(interval);
  }, []);

  const startSeason = async () => {
    if (!season) return;
    setLoading(true);
    try {
      const resp = await fetch(`/api/jimmy/start?year=${season}&slips_per_week=${slipsPerWeek}`, {
        method: "POST",
      });
      const data = await resp.json();
      setState(data);
      setPage("dashboard");
    } catch (err) {
      console.error("Failed to start season:", err);
    }
    setLoading(false);
  };

  if (page === "select") {
    return (
      <>
        <div className="field-bg"></div>
        <div className="jimmy-select">
        <div className="jimmy-hero">
          <h1>🎮 JIMMY</h1>
          <p>Time-travel NFL prop betting backtester</p>
        </div>

        <div className="jimmy-card">
          <h2>Start Your Season</h2>

          <div className="select-group">
            <label>Choose Season</label>
            <div className="season-buttons">
              {[2024, 2025].map(yr => (
                <button
                  key={yr}
                  className={`season-btn ${season === yr ? "active" : ""}`}
                  onClick={() => setSeason(yr)}
                >
                  {yr}
                </button>
              ))}
            </div>
          </div>

          <div className="select-group">
            <label>Slips Per Week (1-5)</label>
            <input
              type="range"
              min="1"
              max="5"
              value={slipsPerWeek}
              onChange={(e) => setSlipsPerWeek(Number(e.target.value))}
              className="slip-slider"
            />
            <div className="slip-value">{slipsPerWeek} slip{slipsPerWeek !== 1 ? "s" : ""}</div>
          </div>

          <button
            onClick={startSeason}
            disabled={!season || loading}
            className="btn-primary"
          >
            {loading ? "Starting..." : "Begin Season"}
          </button>

          <div className="jimmy-info">
            <h3>How it Works</h3>
            <ul>
              <li><strong>Lock your slip count</strong> for the entire 17-week season</li>
              <li><strong>Build slips Friday</strong> of each week with Jimmy's prop recommendations</li>
              <li><strong>Watch outcomes</strong> unfold AM/PM as games play out</li>
              <li><strong>Bankroll grows</strong> dynamically: $5 base → $10 at $500 → $15 at $1000</li>
              <li><strong>Unlock achievements</strong> and compete on the leaderboard</li>
              <li><strong>Season ends</strong> when bankroll hits $0 or Week 17 finishes</li>
            </ul>
          </div>
        </div>
      </div>
      </>
    );
  }

  if (page === "dashboard" && state) {
    return (
      <>
        <div className="field-bg"></div>
        <JimmyDashboard
          state={state}
          cstTime={cstTime}
          onBuilderClick={() => setPage("builder")}
          onGameflowClick={() => setPage("ticker")}
          onEndClick={() => setPage("end")}
          onRecapClick={() => setShowRecap(true)}
        />
        {showRecap && (
          <JimmyWeeklyRecap
            state={state}
            week={state.current_week}
            onClose={() => setShowRecap(false)}
          />
        )}
      </>
    );
  }

  if (page === "builder" && state) {
    return (
      <>
        <div className="field-bg"></div>
        <JimmySlipBuilder state={state} cstTime={cstTime} onBack={() => setPage("dashboard")} />
      </>
    );
  }

  if (page === "ticker" && state) {
    return (
      <>
        <div className="field-bg"></div>
        <JimmyGameflowTicker state={state} cstTime={cstTime} onBack={() => setPage("dashboard")} />
      </>
    );
  }

  if (page === "end" && state) {
    return (
      <>
        <div className="field-bg"></div>
        <JimmySeasonEnd state={state} onRestart={() => setPage("select")} />
      </>
    );
  }

  return null;
}

const SPECIAL_TICKETS = [
  {
    type: "underdog_meta",
    name: "🐕 Underdog Rush",
    description: "Jimmy discovered: underdogs with 3+ game domination win 67% of the time",
    bonus: 1.25,
    unlock_streak: 3,
  },
  {
    type: "sharp_tick",
    name: "📍 Sharp Tick",
    description: "Spread movements on underdog 2-4 hours before kickoff signal sharp money",
    bonus: 1.4,
    unlock_streak: 5,
  },
  {
    type: "prop_correlation",
    name: "🔗 Correlated Pairs",
    description: "Receiving yards + TD on same player when defense allows both",
    bonus: 1.15,
    unlock_streak: 2,
  },
];

function JimmyDashboard({ state, cstTime, onBuilderClick, onGameflowClick, onEndClick, onRecapClick }: any) {
  const roi = ((state.bankroll - 100) / 100 * 100).toFixed(1);
  const cashRate = state.slips.length > 0
    ? (state.slips.filter((s: any) => s.result).length / state.slips.length * 100).toFixed(0)
    : 0;

  const unlockedSpecialTickets = SPECIAL_TICKETS.filter(t => state.win_streak >= t.unlock_streak);

  return (
    <div className="jimmy-dashboard">
      <div className="dashboard-header">
        <div>
          <h1>JIMMY {state.year}</h1>
          <div className="cst-time">CST: {cstTime}</div>
        </div>
        <div className="week-badge">Week {state.current_week}</div>
      </div>

      <div className="dashboard-grid">
        {/* Bankroll Card */}
        <div className="stat-card bankroll-card">
          <div className="stat-label">Bankroll</div>
          <div className="stat-value">${state.bankroll.toFixed(2)}</div>
          <div className="stat-meta">
            ROI: <span className={state.bankroll >= 100 ? "positive" : "negative"}>{roi}%</span>
          </div>
        </div>

        {/* Streak Card */}
        <div className="stat-card streak-card">
          <div className="stat-label">Streak</div>
          <div className="stat-value">
            {state.win_streak > 0 ? `🔥 ${state.win_streak}W` : `🧊 ${state.loss_streak}L`}
          </div>
          <div className="stat-meta">Current</div>
        </div>

        {/* Cash Rate Card */}
        <div className="stat-card cashrate-card">
          <div className="stat-label">Cash Rate</div>
          <div className="stat-value">{cashRate}%</div>
          <div className="stat-meta">{state.slips.length} slips</div>
        </div>

        {/* Wager Info */}
        <div className="stat-card wager-card">
          <div className="stat-label">Wagered</div>
          <div className="stat-value">${state.total_wagered.toFixed(2)}</div>
          <div className="stat-meta">Won: ${state.total_won.toFixed(2)}</div>
        </div>
      </div>

      {/* Special Tickets Unlocked by Win Streaks */}
      {unlockedSpecialTickets.length > 0 && (
        <div className="special-tickets-section">
          <h2>🎯 Jimmy's Discovered Patterns</h2>
          <p className="pattern-intro">These bet types have historically crushed it. Build them this week.</p>
          <div className="special-tickets-grid">
            {unlockedSpecialTickets.map((ticket) => (
              <div key={ticket.type} className="special-ticket-card special-ticket-unlock">
                <div className="ticket-name">{ticket.name}</div>
                <div className="ticket-desc">{ticket.description}</div>
                <div className="ticket-bonus">+{Math.round((ticket.bonus - 1) * 100)}% bonus</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Ticket Editing Unlocks at 3+ Win Streak */}
      {state.win_streak >= 3 && (
        <div className="ticket-edit-unlock">
          <p className="edit-hint">🔓 Unlock: Edit Previous Slips — Your {state.win_streak} win streak qualifies you</p>
        </div>
      )}

      {/* Achievements */}
      <div className="achievements-section">
        <h2>🏆 Achievements</h2>
        <div className="achievements-list">
          {state.achievements.length > 0 ? (
            state.achievements.map((ach: string) => (
              <div key={ach} className="achievement-badge">
                {ach}
              </div>
            ))
          ) : (
            <p className="no-achievements">Build and cash slips to unlock achievements</p>
          )}
        </div>
      </div>

      {/* Recent Slips */}
      <div className="recent-slips">
        <h2>Recent Slips</h2>
        <div className="slips-table">
          {state.slips.slice(-5).reverse().map((slip: any, idx: number) => (
            <div
              key={slip.slip_id}
              className={`slip-row ${slip.result ? "hit" : "miss"}`}
              style={{
                animation: slip.result ? `slipHit 0.8s ease-out ${idx * 0.1}s` : `slipMiss 0.6s ease-in-out ${idx * 0.1}s`,
              }}
            >
              <div className="slip-week">W{slip.week}</div>
              <div className="slip-legs">{slip.legs} legs</div>
              <div className="slip-wager">${slip.wager}</div>
              <div className={`slip-roi ${slip.roi >= 0 ? "positive" : "negative"}`}>
                {slip.roi >= 0 ? "+" : ""}{slip.roi?.toFixed(0)}%
              </div>
              <div className="slip-result">
                {slip.result ? "✅ Cash" : "❌ Miss"}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="dashboard-actions">
        <button onClick={onBuilderClick} className="btn-primary">
          Build This Week's Slip
        </button>
        <button onClick={onGameflowClick} className="btn-secondary">
          Gameflow Ticker
        </button>
        {state.current_week > 1 && (
          <button onClick={onRecapClick} className="btn-recap">
            🎙️ Watch Weekly Recap
          </button>
        )}
        {state.current_week >= 17 && (
          <button onClick={onEndClick} className="btn-success">
            View Season Summary
          </button>
        )}
      </div>
    </div>
  );
}

function JimmySlipBuilder({ state, cstTime, onBack }: any) {
  const [selectedLegs, setSelectedLegs] = useState<any[]>([]);
  const [animatingLeg, setAnimatingLeg] = useState<string | null>(null);
  const unlockedSpecialTickets = SPECIAL_TICKETS.filter(t => state.win_streak >= t.unlock_streak);

  const handleAddLeg = (prop: any) => {
    if (selectedLegs.length < 5) {
      setAnimatingLeg(prop.name);
      setTimeout(() => setAnimatingLeg(null), 600);
      setSelectedLegs([...selectedLegs, prop]);
    }
  };

  return (
    <div className="jimmy-builder">
      <div className="builder-header">
        <button onClick={onBack} className="btn-back">← Back</button>
        <div>
          <h1>Build Week {state.current_week} Slip</h1>
          <div className="builder-cst">CST: {cstTime}</div>
        </div>
      </div>

      <div className="builder-container">
        <div className="builder-info">
          <p>Current Bankroll: <strong>${state.bankroll.toFixed(2)}</strong></p>
          <p>Base Wager: <strong>${state.slips.length > 0 ? state.slips[0].wager : 5}</strong></p>
          <p>Slips This Week: 1/{state.slips_per_week}</p>
          {state.win_streak > 0 && (
            <div className="builder-streak">
              <div className="streak-indicator">🔥 {state.win_streak} Win Streak</div>
              {state.win_streak >= 2 && <p className="streak-hint">Special tickets unlocked</p>}
            </div>
          )}
        </div>

        {/* Special Tickets Available */}
        {unlockedSpecialTickets.length > 0 && (
          <div className="special-builder-tickets">
            <h3>Jimmy's Meta Strategies</h3>
            <div className="meta-tickets">
              {unlockedSpecialTickets.map((ticket) => (
                <div key={ticket.type} className="meta-ticket-option">
                  <div className="meta-name">{ticket.name}</div>
                  <div className="meta-desc">{ticket.description}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="prop-selector">
          <h2>Select Legs (1-5)</h2>
          <p className="prop-hint">
            🔹 Use Jimmy's recommendations (high confidence highlighted)
          </p>
          <div className="props-grid">
            {/* Placeholder: real implementation would fetch props from backend */}
            {[
              { name: "Travis Kelce", type: "REC YARDS", line: "Over 5.5 yards", conf: 72 },
              { name: "Josh Allen", type: "PASS YARDS", line: "Over 245.5 yards", conf: 65 },
              { name: "Najee Harris", type: "RUSH YARDS", line: "Over 49.5 yards", conf: 58 },
              { name: "Lamarr Jackson", type: "PASS YARDS", line: "Over 268.5 yards", conf: 70 },
              { name: "Mark Andrews", type: "REC YARDS", line: "Over 64.5 yards", conf: 68 },
            ].map((prop) => (
              <div
                key={prop.name}
                className={`prop-card ${animatingLeg === prop.name ? "slip-building-active" : ""}`}
              >
                <div className="prop-header">{prop.name}</div>
                <div className="prop-type">{prop.type}</div>
                <div className="prop-line">{prop.line}</div>
                <div className="prop-confidence">
                  <div className="confidence-bar" style={{ width: `${prop.conf}%` }}></div>
                  <span className="confidence-pct">{prop.conf}%</span>
                </div>
                <button
                  className="btn-add-leg"
                  onClick={() => handleAddLeg(prop)}
                  disabled={selectedLegs.length >= 5}
                >
                  {selectedLegs.some(l => l.name === prop.name) ? "✓ Added" : "+ Add"}
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="slip-preview">
          <h2>Slip Preview</h2>
          <div className="preview-legs">
            {selectedLegs.length === 0 ? (
              <p className="no-legs">No legs selected yet</p>
            ) : (
              selectedLegs.map((leg, idx) => (
                <div key={idx} className="preview-leg leg-adding" style={{ animation: `legGlow 1s ease-in-out ${idx * 0.1}s` }}>
                  <span className="leg-name">{leg.name}</span>
                  <span className="leg-prop">{leg.type}</span>
                  <span className="leg-conf">{leg.conf}%</span>
                </div>
              ))
            )}
          </div>
          <div className="preview-risk">
            {selectedLegs.length > 0 && (
              <>
                <div className="risk-score">Risk: <strong>{Math.min(10, Math.round(5 + selectedLegs.length))}/10</strong></div>
                <div className="projected-payout">
                  If all hit: <strong>${(5 * Math.pow(2, selectedLegs.length)).toFixed(2)}</strong>
                </div>
              </>
            )}
          </div>
          <button className="btn-submit-slip" disabled={selectedLegs.length === 0}>
            {selectedLegs.length === 0 ? "Select Legs to Submit" : "Submit Slip"}
          </button>
        </div>
      </div>
    </div>
  );
}

function JimmyGameflowTicker({ state, cstTime, onBack }: any) {
  return (
    <div className="jimmy-ticker">
      <div className="ticker-header">
        <button onClick={onBack} className="btn-back">← Back</button>
        <h1>Gameflow Ticker — Week {state.current_week}</h1>
        <div className="ticker-cst">CST: {cstTime}</div>
      </div>

      <div className="ticker-container">
        <div className="ticker-legend">
          <span>✅ Leg hit</span>
          <span>❌ Leg miss</span>
          <span>⏳ In progress</span>
        </div>

        <div className="game-timeline">
          <div className="game-block">
            <div className="game-time">1:00 PM CST</div>
            <div className="game-matchup">KC @ BUF</div>
            <div className="legs-progress">
              <div className="leg-ticker leg-hit-animation">✅ Travis Kelce O 5.5 REC YDS</div>
              <div className="leg-ticker">⏳ Josh Allen O 245 PASS YDS (189/245)</div>
            </div>
          </div>

          <div className="game-block">
            <div className="game-time">4:00 PM CST</div>
            <div className="game-matchup">DAL @ TB</div>
            <div className="legs-progress">
              <div className="leg-ticker leg-miss-animation">❌ Najee Harris O 49.5 RUSH YDS (38 yards)</div>
            </div>
          </div>

          <div className="game-block">
            <div className="game-time">8:20 PM CST</div>
            <div className="game-matchup">SF @ LAR (Sunday Night)</div>
            <div className="legs-progress">
              <div className="leg-ticker">⏳ Lamarr Jackson O 268 PASS YDS</div>
            </div>
          </div>
        </div>

        <div className="weekly-summary">
          <h2>This Week Summary</h2>
          <div className="summary-stats">
            <div>Slips Submitted: 1/{state.slips_per_week}</div>
            <div>Legs Hit: 1/3</div>
            <div>Slip Result: ❌ Miss</div>
            <div>Current Bankroll: ${state.bankroll.toFixed(2)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function JimmySeasonEnd({ state, onRestart }: any) {
  const roi = ((state.bankroll - 100) / 100 * 100).toFixed(1);
  const cashRate = state.slips.length > 0
    ? (state.slips.filter((s: any) => s.result).length / state.slips.length * 100).toFixed(0)
    : 0;

  return (
    <div className="jimmy-end">
      <div className="end-header">
        <h1>🏁 Season Complete</h1>
        <p>{state.year} Season Summary</p>
      </div>

      <div className="end-stats">
        <div className="stat-box">
          <div className="stat-label">Final Bankroll</div>
          <div className={`stat-big ${state.bankroll >= 100 ? "positive" : "negative"}`}>
            ${state.bankroll.toFixed(2)}
          </div>
        </div>

        <div className="stat-box">
          <div className="stat-label">ROI</div>
          <div className={`stat-big ${state.bankroll >= 100 ? "positive" : "negative"}`}>
            {roi}%
          </div>
        </div>

        <div className="stat-box">
          <div className="stat-label">Slips Cashed</div>
          <div className="stat-big">{cashRate}%</div>
        </div>

        <div className="stat-box">
          <div className="stat-label">Total Wagered</div>
          <div className="stat-big">${state.total_wagered.toFixed(2)}</div>
        </div>
      </div>

      <div className="achievements-final">
        <h2>🏆 Unlocked</h2>
        <div className="achievements-list">
          {state.achievements.map((ach: string) => (
            <div key={ach} className="achievement-badge-large">{ach}</div>
          ))}
        </div>
      </div>

      <button onClick={onRestart} className="btn-restart">Start New Season</button>
    </div>
  );
}
