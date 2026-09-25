import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import ParlaysPage from "./pages/ParlaysPage";
import "reactflow/dist/style.css";
import "./theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/parlays" element={<ParlaysPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
