// Voice playback through Web Audio so the host orbs can react to what is actually being said.

export class VoiceEngine {
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private samples: Uint8Array<ArrayBuffer> | null = null;
  private source: AudioBufferSourceNode | null = null;
  private finish: (() => void) | null = null;
  rate = 1;

  /** Create and resume the audio context. Call from a click or tap so browsers allow sound. */
  unlock(): boolean {
    if (!this.ctx) {
      const AC = window.AudioContext || (window as any).webkitAudioContext;
      if (!AC) return false;
      this.ctx = new AC();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 512;
      this.analyser.smoothingTimeConstant = 0.6;
      this.samples = new Uint8Array(new ArrayBuffer(this.analyser.fftSize));
      this.analyser.connect(this.ctx.destination);
    }
    void this.ctx.resume();
    return this.ctx.state !== "closed";
  }

  get running(): boolean {
    return this.ctx?.state === "running";
  }

  /** Play one clip. Resolves true when it played through Web Audio, false if it could not. */
  async play(url: string): Promise<boolean> {
    if (!this.ctx || !this.analyser) return false;
    try {
      const raw = await (await fetch(url)).arrayBuffer();
      const buffer = await this.ctx.decodeAudioData(raw);
      return await new Promise<boolean>((resolve) => {
        const src = this.ctx!.createBufferSource();
        src.buffer = buffer;
        src.playbackRate.value = this.rate;
        src.connect(this.analyser!);
        this.source = src;
        this.finish = () => resolve(true);
        src.onended = () => {
          this.source = null;
          this.finish = null;
          resolve(true);
        };
        src.start();
      });
    } catch {
      return false;
    }
  }

  setRate(rate: number) {
    this.rate = rate;
    if (this.source) this.source.playbackRate.value = rate;
  }

  stop() {
    const done = this.finish;
    this.finish = null;
    try { this.source?.stop(); } catch { /* already stopped */ }
    this.source = null;
    done?.();
  }

  /** Current output loudness, 0 to 1. */
  level(): number {
    if (!this.analyser || !this.samples || !this.source) return 0;
    this.analyser.getByteTimeDomainData(this.samples);
    let sum = 0;
    for (let i = 0; i < this.samples.length; i++) {
      const v = (this.samples[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / this.samples.length) * 5.5);
  }

  dispose() {
    this.stop();
    void this.ctx?.close();
    this.ctx = null;
    this.analyser = null;
  }
}
