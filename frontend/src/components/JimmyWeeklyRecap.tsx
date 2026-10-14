import React, { useState, useEffect, useRef } from "react";

interface RecapSegment {
  speaker: string;
  role: string;
  text: string;
  word_count: number;
}

interface WeeklyRecap {
  week: number;
  title: string;
  segments: RecapSegment[];
  total_words: number;
  bankroll_delta: number;
  slips_cashed: number;
  cashed_pct: number;
  key_stat: string;
}

interface JimmyWeeklyRecapProps {
  state: any;
  week: number;
  onClose: () => void;
}

const SPEAKER_COLORS = {
  "MY BOO": "#ef4444",
  "Jonah Jacques": "#3b82f6",
  "Julian Feltus": "#f59e0b",
};

const SPEAKER_PHOTOS: Record<string, string> = {
  "MY BOO": "📊",
  "Jonah Jacques": "🎤",
  "Julian Feltus": "🧠",
};

async function generateSpeech(text: string, speaker: string): Promise<string> {
  try {
    const response = await fetch("https://api-inference.huggingface.co/models/espnet/hindi_male_fgl/v1", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${import.meta.env.VITE_HF_TOKEN || ""}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        inputs: text,
        options: { use_cache: false },
      }),
    });

    if (!response.ok) {
      console.warn(`TTS failed for ${speaker}, using silent placeholder`);
      return "";
    }

    const blob = await response.blob();
    return URL.createObjectURL(blob);
  } catch (error) {
    console.warn("TTS error:", error);
    return "";
  }
}

export default function JimmyWeeklyRecap({ state, week, onClose }: JimmyWeeklyRecapProps) {
  const [recap, setRecap] = useState<WeeklyRecap | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSegment, setActiveSegment] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [audioUrls, setAudioUrls] = useState<Record<string, string>>({});
  const [musicVolume, setMusicVolume] = useState(0.4);
  const audioRef = useRef<HTMLAudioElement>(null);
  const musicRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    fetchRecap();
  }, [state, week]);

  async function fetchRecap() {
    try {
      setLoading(true);
      const resp = await fetch("/api/jimmy/recap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state, week }),
      });
      const result = await resp.json();
      setRecap(result);

      const urls: Record<string, string> = {};
      for (const segment of result.segments) {
        const speaker = segment.speaker;
        const url = await generateSpeech(segment.text, speaker);
        if (url) urls[speaker] = url;
      }
      setAudioUrls(urls);
    } catch (error) {
      console.error("Failed to load recap:", error);
    } finally {
      setLoading(false);
    }
  }

  function handlePlaySegment(idx: number) {
    if (!recap) return;
    const segment = recap.segments[idx];
    const audioUrl = audioUrls[segment.speaker];

    if (audioRef.current && audioUrl) {
      audioRef.current.src = audioUrl;
      setActiveSegment(idx);
      setPlaying(true);
      audioRef.current.play();
      if (musicRef.current) musicRef.current.play();
    }
  }

  function handleStop() {
    setPlaying(false);
    if (audioRef.current) audioRef.current.pause();
    if (musicRef.current) musicRef.current.pause();
  }

  if (loading) {
    return (
      <div
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.8)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 999,
        }}
      >
        <div style={{ color: "#ece6f2", fontSize: 18, fontFamily: "monospace" }}>
          🎙️ Generating recap...
        </div>
      </div>
    );
  }

  if (!recap) {
    return (
      <div
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.8)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 999,
        }}
        onClick={onClose}
      >
        <div style={{ color: "#ef4444", fontSize: 18, fontFamily: "monospace" }}>
          Failed to load recap
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.95)",
        zIndex: 999,
        overflow: "auto",
        padding: "20px",
      }}
      onClick={(e) => {
        if ((e.target as HTMLElement).getAttribute("data-modal-bg")) onClose();
      }}
      data-modal-bg="true"
    >
      <audio ref={audioRef} />
      <audio
        ref={musicRef}
        loop
        src="https://assets.mixkit.co/active_storage/sfx/2449/2449-preview.mp3"
        style={{ display: "none" }}
      />

      <div
        style={{
          maxWidth: 900,
          margin: "0 auto",
          background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
          border: "3px solid #ffb81c",
          borderRadius: 12,
          padding: 30,
          boxShadow: "0 0 40px rgba(255, 184, 28, 0.3)",
          color: "#ece6f2",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: 20,
            right: 20,
            background: "transparent",
            border: "1px solid #6b4a1c",
            color: "#d9b45a",
            padding: "8px 16px",
            borderRadius: 4,
            cursor: "pointer",
            fontFamily: "monospace",
            fontWeight: 700,
          }}
        >
          CLOSE ✕
        </button>

        <h1
          style={{
            fontSize: 28,
            fontWeight: 800,
            marginBottom: 10,
            color: "#ffb81c",
            textAlign: "center",
          }}
        >
          {recap.title}
        </h1>

        <div
          style={{
            display: "flex",
            gap: 30,
            justifyContent: "center",
            marginBottom: 30,
            flexWrap: "wrap",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "#d9b45a" }}>BANKROLL DELTA</div>
            <div
              style={{
                fontSize: 24,
                fontWeight: 700,
                color: recap.bankroll_delta >= 0 ? "#10b981" : "#ef4444",
              }}
            >
              ${recap.bankroll_delta > 0 ? "+" : ""}
              {recap.bankroll_delta.toFixed(2)}
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "#d9b45a" }}>SLIPS CASHED</div>
            <div style={{ fontSize: 24, fontWeight: 700 }}>
              {recap.slips_cashed} ({recap.cashed_pct}%)
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 12, color: "#d9b45a" }}>KEY STAT</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{recap.key_stat}</div>
          </div>
        </div>

        <div
          style={{
            background: "rgba(11,5,18,0.6)",
            border: "2px solid #6b4a1c",
            borderRadius: 8,
            padding: 20,
            marginBottom: 30,
          }}
        >
          <div style={{ display: "flex", gap: 20, marginBottom: 20, overflowX: "auto" }}>
            {recap.segments.map((segment, idx) => (
              <button
                key={idx}
                onClick={() => handlePlaySegment(idx)}
                style={{
                  flex: "0 0 auto",
                  background:
                    activeSegment === idx && playing
                      ? (SPEAKER_COLORS as any)[segment.speaker]
                      : "rgba(255,184,28,0.1)",
                  border: `2px solid ${(SPEAKER_COLORS as any)[segment.speaker] || "#fff"}`,
                  color: "#ece6f2",
                  padding: "12px 20px",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontWeight: 700,
                  whiteSpace: "nowrap",
                  animation:
                    activeSegment === idx && playing ? "pulse 1s infinite" : "none",
                }}
              >
                {(SPEAKER_PHOTOS as any)[segment.speaker]} {segment.speaker.split(" ")[0]}
              </button>
            ))}
          </div>

          <div style={{ marginBottom: 20 }}>
            <div
              style={{
                fontSize: 16,
                fontWeight: 700,
                color: "#ffb81c",
                marginBottom: 10,
              }}
            >
              {recap.segments[activeSegment]?.speaker} · {recap.segments[activeSegment]?.role}
            </div>
            <p
              style={{
                fontSize: 15,
                lineHeight: 1.6,
                color: "#ece6f2",
                margin: 0,
                fontFamily: "system-ui, -apple-system, sans-serif",
              }}
            >
              {recap.segments[activeSegment]?.text}
            </p>
            <div style={{ fontSize: 12, color: "#999", marginTop: 10 }}>
              ~{recap.segments[activeSegment]?.word_count} words
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            {!playing ? (
              <button
                onClick={() => handlePlaySegment(activeSegment)}
                style={{
                  background: "#10b981",
                  border: "none",
                  color: "#fff",
                  padding: "10px 20px",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontWeight: 700,
                }}
              >
                ▶ PLAY SEGMENT
              </button>
            ) : (
              <button
                onClick={handleStop}
                style={{
                  background: "#ef4444",
                  border: "none",
                  color: "#fff",
                  padding: "10px 20px",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontFamily: "monospace",
                  fontWeight: 700,
                }}
              >
                ⏹ STOP
              </button>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
              <label style={{ fontSize: 12, color: "#999" }}>MUSIC</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={musicVolume}
                onChange={(e) => {
                  const vol = parseFloat(e.target.value);
                  setMusicVolume(vol);
                  if (musicRef.current) musicRef.current.volume = vol;
                }}
                style={{ width: 100, cursor: "pointer" }}
              />
            </div>
          </div>
        </div>

        <div
          style={{
            fontSize: 12,
            color: "#999",
            textAlign: "center",
            borderTop: "1px solid #6b4a1c",
            paddingTop: 15,
          }}
        >
          Week {recap.week} Recap • {recap.total_words} total words • 3 voices
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
}
