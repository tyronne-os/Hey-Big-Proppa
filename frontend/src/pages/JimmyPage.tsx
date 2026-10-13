/**
 * JIMMY: NFL Prop Betting Backtester & Video Game
 *
 * Time-travel simulator: user selects 1-5 slips, locks them for entire season,
 * then watches the season play out from Friday of Week 1 through Super Bowl.
 * Features: achievements, leaderboards, hot/cold indicators, risk scoring, MY BOO analysis.
 */
import React, { useState, useEffect } from "react";
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
}

export default function JimmyPage() {
  const [page, setPage] = useState<"select" | "dashboard" | "builder" | "ticker" | "end">("select");
  const [season, setSeason] = useState<number | null>(null);
  const [slipsPerWeek, setSlipsPerWeek] = useState(1);
  const [state, setState] = useState<SeasonState | null>(null);
  const [loading, setLoading] = useState(false);

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
    );
  }

  if (page === "dashboard" && state) {
    return (
      <JimmyDashboard
        state={state}
        onBuilderClick={() => setPage("builder")}
        onGameflowClick={() => setPage("ticker")}
        onEndClick={() => setPage("end")}
      />
    );
  }

  if (page === "builder" && state) {
    return <JimmySlipBuilder state={state} onBack={() => setPage("dashboard")} />;
  }

  if (page === "ticker" && state) {
    return <JimmyGameflowTicker state={state} onBack={() => setPage("dashboard")} />;
  }

  if (page === "end" && state) {
    return <JimmySeasonEnd state={state} onRestart={() => setPage("select")} />;
  }

  return null;
}

function JimmyDashboard({ state, onBuilderClick, onGameflowClick, onEndClick }: any) {
  const roi = ((state.bankroll - 100) / 100 * 100).toFixed(1);
  const cashRate = state.slips.length > 0
    ? (state.slips.filter((s: any) => s.result).length / state.slips.length * 100).toFixed(0)
    : 0;

  return (
    <div className="jimmy-dashboard">
      <div className="dashboard-header">
        <h1>JIMMY {state.year}</h1>
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
          {state.slips.slice(-5).reverse().map((slip: any) => (
            <div key={slip.slip_id} className={`slip-row ${slip.result ? "hit" : "miss"}`}>
              <div className="slip-week">W{slip.week}</div>
              <div className="slip-legs">{slip.legs} legs</div>
              <div className="slip-wager">${slip.wager}</div>
              <div className="slip-roi">{slip.roi >= 0 ? "+" : ""}{slip.roi?.toFixed(0)}%</div>
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
        {state.current_week >= 17 && (
          <button onClick={onEndClick} className="btn-success">
            View Season Summary
          </button>
        )}
      </div>
    </div>
  );
}

function JimmySlipBuilder({ state, onBack }: any) {
  return (
    <div className="jimmy-builder">
      <div className="builder-header">
        <button onClick={onBack} className="btn-back">← Back</button>
        <h1>Build Week {state.current_week} Slip</h1>
      </div>

      <div className="builder-container">
        <div className="builder-info">
          <p>Current Bankroll: <strong>${state.bankroll.toFixed(2)}</strong></p>
          <p>Base Wager: <strong>${state.slips.length > 0 ? state.slips[0].wager : 5}</strong></p>
          <p>Slips This Week: 1/{state.slips_per_week}</p>
        </div>

        <div className="prop-selector">
          <h2>Select Legs (1-5)</h2>
          <p className="prop-hint">
            🔹 Use Jimmy's recommendations (high confidence highlighted)
          </p>
          <div className="props-grid">
            {/* Placeholder: real implementation would fetch props from backend */}
            <div className="prop-card">
              <div className="prop-header">Travis Kelce</div>
              <div className="prop-type">REC YARDS</div>
              <div className="prop-line">Over 5.5 yards</div>
              <div className="prop-confidence">
                <div className="confidence-bar" style={{ width: "72%" }}></div>
                <span className="confidence-pct">72%</span>
              </div>
              <button className="btn-add-leg">+ Add</button>
            </div>

            <div className="prop-card">
              <div className="prop-header">Josh Allen</div>
              <div className="prop-type">PASS YARDS</div>
              <div className="prop-line">Over 245.5 yards</div>
              <div className="prop-confidence">
                <div className="confidence-bar" style={{ width: "65%" }}></div>
                <span className="confidence-pct">65%</span>
              </div>
              <button className="btn-add-leg">+ Add</button>
            </div>

            <div className="prop-card">
              <div className="prop-header">Najee Harris</div>
              <div className="prop-type">RUSH YARDS</div>
              <div className="prop-line">Over 49.5 yards</div>
              <div className="prop-confidence">
                <div className="confidence-bar" style={{ width: "58%" }}></div>
                <span className="confidence-pct">58%</span>
              </div>
              <button className="btn-add-leg">+ Add</button>
            </div>
          </div>
        </div>

        <div className="slip-preview">
          <h2>Slip Preview</h2>
          <div className="preview-legs">
            <p className="no-legs">No legs selected yet</p>
          </div>
          <div className="preview-risk">
            <div className="risk-score">Risk: <strong>—</strong></div>
            <div className="projected-payout">If all hit: <strong>—</strong></div>
          </div>
          <button className="btn-submit-slip" disabled>Submit Slip</button>
        </div>
      </div>
    </div>
  );
}

function JimmyGameflowTicker({ state, onBack }: any) {
  return (
    <div className="jimmy-ticker">
      <button onClick={onBack} className="btn-back">← Back</button>
      <h1>Gameflow Ticker</h1>

      <div className="ticker-container">
        <div className="ticker-legend">
          <span>✅ Leg hit</span>
          <span>❌ Leg miss</span>
          <span>⏳ In progress</span>
        </div>

        <div className="game-timeline">
          <div className="game-block">
            <div className="game-time">1:00 PM</div>
            <div className="game-matchup">KC @ BUF</div>
            <div className="legs-progress">
              <div className="leg-ticker">✅ Travis Kelce O 5.5 REC YDS</div>
              <div className="leg-ticker">⏳ Josh Allen O 245 PASS YDS</div>
            </div>
          </div>

          <div className="game-block">
            <div className="game-time">4:00 PM</div>
            <div className="game-matchup">DAL @ TB</div>
            <div className="legs-progress">
              <div className="leg-ticker">❌ Najee Harris O 49.5 RUSH YDS</div>
            </div>
          </div>
        </div>

        <div className="weekly-summary">
          <h2>This Week Summary</h2>
          <div className="summary-stats">
            <div>Slips: 1/1</div>
            <div>Legs Hit: 1/3</div>
            <div>Result: Miss</div>
            <div>Bankroll: $95.00</div>
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
