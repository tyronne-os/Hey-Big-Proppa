import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import App from "./App";
import ParlaysPage from "./pages/ParlaysPage";
import MondayPage from "./pages/MondayPage";
import SundayParlaysPage from "./pages/SundayParlaysPage";
import "reactflow/dist/style.css";
import "./theme.css";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ background: "#0b0512", color: "#ece6f2", padding: 40, fontFamily: "monospace", minHeight: "100vh" }}>
          <h2 style={{ color: "#ef4444" }}>HEY BIG PROPPA! — render error</h2>
          <pre style={{ color: "#d9b45a", whiteSpace: "pre-wrap" }}>{String(this.state.error)}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/throwdown" element={<ParlaysPage variant="thursday" />} />
          <Route path="/monday"    element={<MondayPage />} />
          <Route path="/parlays"   element={<SundayParlaysPage />} />
          <Route path="/targets"   element={<Navigate to="/leaders?cat=targets" replace />} />
          {(["player", "leaders", "matchups", "ramp", "engine", "news", "queries", "myboo", "odds"] as const).map((t) => (
            <Route key={t} path={`/${t}`} element={<App initialTab={t} />} />
          ))}
          <Route path="*" element={<Navigate to="/throwdown" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
);
