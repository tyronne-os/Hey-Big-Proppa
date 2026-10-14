// Big Proppa booth audio: a procedural sports-show theme bed and the three host voices.

type Ctx = AudioContext;

const BPM = 116;
const STEP = 60 / BPM / 2; // eighth notes
// D - C - Bb - C, the classic Sunday-afternoon brass loop
const ROOTS = [38, 36, 34, 36];
const CHORDS = [[62, 66, 69], [60, 64, 67], [58, 62, 65], [60, 64, 67]];
const mtof = (m: number) => 440 * Math.pow(2, (m - 69) / 12);

export class ThemeMusic {
  private ctx: Ctx | null = null;
  private bus: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private timer: number | null = null;
  private step = 0;
  private nextAt = 0;
  private volume = 0.35;
  private ducked = false;

  start(volume = this.volume) {
    this.volume = volume;
    if (!this.ctx) {
      const AC = window.AudioContext || (window as any).webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      const comp = this.ctx.createDynamicsCompressor();
      comp.threshold.value = -18;
      comp.ratio.value = 4;
      this.bus = this.ctx.createGain();
      this.bus.gain.value = 0;
      this.bus.connect(comp).connect(this.ctx.destination);
      const len = this.ctx.sampleRate;
      this.noise = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
      const d = this.noise.getChannelData(0);
      for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    }
    const ctx = this.ctx;
    ctx.resume();
    if (this.timer == null) {
      this.nextAt = ctx.currentTime + 0.05;
      this.timer = window.setInterval(() => this.schedule(), 40);
    }
    this.applyGain(0.6);
  }

  stop() {
    if (this.timer != null) window.clearInterval(this.timer);
    this.timer = null;
    if (this.ctx && this.bus) this.bus.gain.setTargetAtTime(0, this.ctx.currentTime, 0.3);
  }

  setVolume(v: number) {
    this.volume = v;
    this.applyGain(0.2);
  }

  duck(on: boolean) {
    this.ducked = on;
    this.applyGain(on ? 0.25 : 0.6);
  }

  stinger() {
    if (!this.ctx || !this.bus) return;
    const t = this.ctx.currentTime + 0.02;
    [50, 62, 66, 69, 74].forEach((m) => this.brass(t, m, 1.1, 0.16));
    this.crash(t);
  }

  private applyGain(tc: number) {
    if (!this.ctx || !this.bus) return;
    const target = this.timer == null ? 0 : this.volume * (this.ducked ? 0.22 : 1);
    this.bus.gain.setTargetAtTime(target, this.ctx.currentTime, tc);
  }

  private schedule() {
    const ctx = this.ctx!;
    while (this.nextAt < ctx.currentTime + 0.15) {
      this.playStep(this.step, this.nextAt);
      this.nextAt += STEP;
      this.step = (this.step + 1) % 32;
    }
  }

  private playStep(s: number, t: number) {
    const bar = Math.floor(s / 8);
    const beat = s % 8;
    if (beat === 0 || beat === 4 || (beat === 7 && bar % 2 === 1)) this.kick(t);
    if (beat === 2 || beat === 6) this.snare(t);
    this.hat(t, beat % 2 === 0 ? 0.05 : 0.025);
    this.bass(t, mtof(ROOTS[bar] + (beat === 6 ? 7 : 0)));
    if (beat === 0 || beat === 3) CHORDS[bar].forEach((m) => this.brass(t, m, beat === 0 ? 0.35 : 0.18, 0.07));
  }

  private env(t: number, peak: number, decay: number) {
    const g = this.ctx!.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + decay);
    g.connect(this.bus!);
    return g;
  }

  private kick(t: number) {
    const o = this.ctx!.createOscillator();
    o.frequency.setValueAtTime(140, t);
    o.frequency.exponentialRampToValueAtTime(42, t + 0.12);
    o.connect(this.env(t, 0.9, 0.22));
    o.start(t);
    o.stop(t + 0.25);
  }

  private noiseHit(t: number, hp: number, peak: number, decay: number) {
    const src = this.ctx!.createBufferSource();
    src.buffer = this.noise;
    const f = this.ctx!.createBiquadFilter();
    f.type = "highpass";
    f.frequency.value = hp;
    src.connect(f).connect(this.env(t, peak, decay));
    src.start(t);
    src.stop(t + decay + 0.05);
  }

  private snare(t: number) {
    this.noiseHit(t, 1800, 0.4, 0.16);
  }

  private hat(t: number, peak: number) {
    this.noiseHit(t, 8000, peak, 0.04);
  }

  private crash(t: number) {
    this.noiseHit(t, 5000, 0.25, 1.4);
  }

  private bass(t: number, f: number) {
    const o = this.ctx!.createOscillator();
    o.type = "sawtooth";
    o.frequency.value = f;
    const lp = this.ctx!.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 380;
    o.connect(lp).connect(this.env(t, 0.22, STEP * 0.9));
    o.start(t);
    o.stop(t + STEP);
  }

  private brass(t: number, m: number, dur: number, peak: number) {
    const lp = this.ctx!.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.setValueAtTime(900, t);
    lp.frequency.exponentialRampToValueAtTime(2600, t + 0.06);
    lp.frequency.exponentialRampToValueAtTime(1200, t + dur);
    const g = this.env(t, peak, dur);
    lp.connect(g);
    [-6, 6].forEach((det) => {
      const o = this.ctx!.createOscillator();
      o.type = "sawtooth";
      o.frequency.value = mtof(m);
      o.detune.value = det;
      o.connect(lp);
      o.start(t);
      o.stop(t + dur + 0.05);
    });
  }
}

// ------------------------------------------------------------------ host voices

export const HOST_STYLE: Record<string, { pitch: number; rate: number; prefer: RegExp }> = {
  "Jonah Jacques": { pitch: 1.0, rate: 1.1, prefer: /(daniel|alex|guy|davis|google us english|male)/i },
  "MY BOO": { pitch: 1.12, rate: 1.0, prefer: /(samantha|victoria|zira|aria|jenny|female|google uk english female|karen|moira)/i },
  "Julian Feltus": { pitch: 0.82, rate: 0.95, prefer: /(fred|tom|ryan|david|mark|google uk english male|arthur)/i },
};

export function speechAvailable() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

function voicesNow(): SpeechSynthesisVoice[] {
  return speechAvailable() ? window.speechSynthesis.getVoices().filter((v) => /^en/i.test(v.lang)) : [];
}

export function loadVoices(): Promise<void> {
  if (!speechAvailable()) return Promise.resolve();
  if (voicesNow().length) return Promise.resolve();
  return new Promise((res) => {
    const done = () => res();
    window.speechSynthesis.addEventListener("voiceschanged", done, { once: true });
    setTimeout(done, 1200);
  });
}

export function voiceFor(host: string): SpeechSynthesisVoice | undefined {
  const all = voicesNow();
  if (!all.length) return undefined;
  const hosts = Object.keys(HOST_STYLE);
  const want = all.find((v) => HOST_STYLE[host]?.prefer.test(v.name));
  if (want) return want;
  return all[hosts.indexOf(host) % all.length];
}

export function splitSentences(text: string): string[] {
  // split only where punctuation is followed by whitespace, so "88.5" and "$4.50" stay whole
  return text.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
}

/** Speak one sentence; resolves when done. Without speech, waits a reading-speed beat so the show still runs. */
const readMs = (text: string) => Math.max(1400, (text.split(/\s+/).length / 3.1) * 1000);

export function say(text: string, host: string, useVoice: boolean): { done: Promise<void>; cancel: () => void } {
  let cancelled = false;
  let timer: number | undefined;
  if (!useVoice || !speechAvailable()) {
    const ms = readMs(text);
    return {
      done: new Promise((res) => { timer = window.setTimeout(res, ms); }),
      cancel: () => { cancelled = true; window.clearTimeout(timer); },
    };
  }
  const u = new SpeechSynthesisUtterance(text);
  const style = HOST_STYLE[host];
  u.voice = voiceFor(host) ?? null;
  u.pitch = style?.pitch ?? 1;
  u.rate = style?.rate ?? 1;
  const began = Date.now();
  const done = new Promise<void>((res) => {
    u.onend = () => res();
    // An engine that refuses to speak still gets the sentence its reading time on screen.
    u.onerror = () => {
      if (cancelled) return res();
      window.clearTimeout(timer);
      timer = window.setTimeout(res, Math.max(0, readMs(text) - (Date.now() - began)));
    };
    // Some engines drop onend; never let the show hang.
    timer = window.setTimeout(res, Math.max(4000, text.length * 120));
  });
  window.speechSynthesis.speak(u);
  return {
    done: done.then(() => window.clearTimeout(timer)),
    cancel: () => {
      if (!cancelled) window.speechSynthesis.cancel();
      cancelled = true;
      window.clearTimeout(timer);
    },
  };
}
