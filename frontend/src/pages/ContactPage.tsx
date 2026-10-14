import { useState } from "react";
import NavBar from "../components/NavBar";
import { API_BASE } from "../api";
import "./ContactPage.css";

const TOPICS = ["General question", "Partnership or press", "Bug or data issue", "Feature request", "Waitlist / access"];

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", topic: TOPICS[0], message: "", website: "" });
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [err, setErr] = useState("");
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setState("sending");
    try {
      const r = await fetch(`${API_BASE}/api/contact`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Something went wrong. Please try again.");
      setState("sent");
    } catch (x: any) {
      setErr(x?.message || "Something went wrong. Please try again.");
      setState("idle");
    }
  }

  return (
    <div className="ct-root">
      <NavBar activeTab="contact" />
      <main className="ct-wrap">
        <div className="ct-kicker">Contact us</div>
        <h1>Talk to the Big Proppa team</h1>
        <p className="ct-lead">Questions, press, data issues, ideas for the BETTER-VERSE: send it here and it goes straight to the team.</p>

        {state === "sent" ? (
          <div className="ct-done" role="status">
            <h2>Message received.</h2>
            <p>Thanks, {form.name || "friend"}. We'll reply to {form.email}.</p>
            <button onClick={() => { setForm({ name: "", email: "", topic: TOPICS[0], message: "", website: "" }); setState("idle"); }}>Send another</button>
          </div>
        ) : (
          <form className="ct-form" onSubmit={submit}>
            <div className="ct-row">
              <label>Name<input value={form.name} onChange={set("name")} maxLength={100} autoComplete="name" /></label>
              <label>Email<input type="email" required value={form.email} onChange={set("email")} maxLength={200} autoComplete="email" /></label>
            </div>
            <label>Topic
              <select value={form.topic} onChange={set("topic")}>{TOPICS.map((t) => <option key={t}>{t}</option>)}</select>
            </label>
            <label>Message
              <textarea required minLength={5} rows={7} value={form.message} onChange={set("message")} maxLength={4000} />
            </label>
            <label className="ct-hp" aria-hidden="true">Website<input tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} /></label>
            {err && <div className="ct-err" role="alert">{err}</div>}
            <button className="ct-send" disabled={state === "sending"}>{state === "sending" ? "Sending…" : "Send message"}</button>
          </form>
        )}
      </main>
    </div>
  );
}
