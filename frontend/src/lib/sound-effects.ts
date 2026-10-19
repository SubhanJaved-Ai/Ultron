/**
 * Ultron Cyber UI Sound Effects Service
 *
 * Implements lightweight procedural synthesized audio cues using the Web Audio API.
 * - Zero external sound files or audio assets required.
 * - Sub-millisecond instant synthesis with dynamic frequency shaping.
 * - Throttled typing ticks (ignoring composition/IME, programmatic input, and paste bursts).
 * - Full mute, volume control, and persistence.
 * - Accessibility-conscious: sound is never required to understand UI state.
 */

export interface SoundConfig {
  enabled: boolean;
  volume: number; // 0.0 to 1.0
}

export const SOUND_ASSET_PATHS = {
  mic: '/audio/mic.wav',
  loading: '/audio/loading.wav',
  listening: '/audio/07_voice_ai_listening.wav',
  processingLoop: '/audio/08_ai_processing_LOOP.wav',
} as const;

function resolveAssetUrl(relPath: string): string {
  if (typeof window === 'undefined') return relPath;
  const base = (import.meta as any).env?.BASE_URL || '/';
  const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
  const cleanRel = relPath.startsWith('/') ? relPath : '/' + relPath;
  return `${cleanBase}${cleanRel}`;
}

const SETTINGS_SOUND_KEY = 'ultron-sound-settings';

class SoundEffectsService {
  private ctx: AudioContext | null = null;
  private currentMicAudio: HTMLAudioElement | null = null;
  private currentLoadingAudio: HTMLAudioElement | null = null;
  private config: SoundConfig = {
    enabled: true,
    volume: 0.35,
  };
  private lastTypingTickMs = 0;
  private readonly TYPING_THROTTLE_MS = 65; // Prevent overwhelming audio bursts while typing fast

  constructor() {
    this.loadPersistedConfig();
  }

  private loadPersistedConfig(): void {
    if (typeof window === 'undefined') return;
    try {
      const raw = localStorage.getItem(SETTINGS_SOUND_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (typeof parsed.enabled === 'boolean') this.config.enabled = parsed.enabled;
        if (typeof parsed.volume === 'number') {
          this.config.volume = Math.max(0, Math.min(1, parsed.volume));
        }
      }
    } catch {
      // Fallback to defaults
    }
  }

  public saveConfig(updates: Partial<SoundConfig>): SoundConfig {
    this.config = { ...this.config, ...updates };
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(SETTINGS_SOUND_KEY, JSON.stringify(this.config));
      } catch {
        // LocalStorage fallback
      }
    }
    return { ...this.config };
  }

  public getConfig(): SoundConfig {
    return { ...this.config };
  }

  public setEnabled(enabled: boolean): void {
    this.saveConfig({ enabled });
  }

  public isEnabled(): boolean {
    return this.config.enabled;
  }

  public setVolume(volume: number): void {
    this.saveConfig({ volume: Math.max(0, Math.min(1, volume)) });
  }

  public getVolume(): number {
    return this.config.volume;
  }

  /**
   * Lazily acquire or resume the AudioContext on user interaction to comply
   * with browser autoplay policies.
   */
  private getContext(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return null;

    if (!this.ctx) {
      try {
        this.ctx = new AudioContextClass();
      } catch {
        return null;
      }
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }

  /**
   * 1. UI Click & Option Selection
   * Crisp, subtle futuristic digital click with pitch-drop envelope.
   */
  public playClick(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      // Fast drop from 1400Hz to 360Hz over 32ms
      osc.frequency.setValueAtTime(1400, now);
      osc.frequency.exponentialRampToValueAtTime(360, now + 0.032);

      const peakVol = 0.15 * this.config.volume;
      gain.gain.setValueAtTime(peakVol, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.035);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.036);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 2. Text Entry Tick
   * Micro-tick for user typing events.
   * Throttled to avoid auditory fatigue.
   */
  public playTypingTick(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const nowMs = Date.now();
    if (nowMs - this.lastTypingTickMs < this.TYPING_THROTTLE_MS) {
      return;
    }
    this.lastTypingTickMs = nowMs;

    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const filter = ctx.createBiquadFilter();
      const gain = ctx.createGain();

      osc.type = 'triangle';
      // Subtle micro high pitch tick
      osc.frequency.setValueAtTime(2200, now);
      osc.frequency.exponentialRampToValueAtTime(1100, now + 0.012);

      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(1800, now);
      filter.Q.setValueAtTime(3.0, now);

      const peakVol = 0.07 * this.config.volume;
      gain.gain.setValueAtTime(peakVol, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.015);

      osc.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.016);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 3. Loading / Processing Tone
   * Resonant futuristic data-scan pulse.
   */
  public playProcessingPulse(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = 'sine';
      osc2.type = 'sine';

      // Harmonic interval (520Hz & 780Hz)
      osc1.frequency.setValueAtTime(520, now);
      osc2.frequency.setValueAtTime(780, now);

      const peakVol = 0.12 * this.config.volume;
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(peakVol, now + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 0.19);
      osc2.stop(now + 0.19);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 4. Successful Completion / Confirmation
   * Ascending harmonic chime with warm cyber resonance.
   */
  public playSuccessChime(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = 'sine';
      osc2.type = 'sine';

      // Ascending major fifth sequence (E5 659.25Hz -> B5 987.77Hz)
      osc1.frequency.setValueAtTime(659.25, now);
      osc1.frequency.setValueAtTime(987.77, now + 0.08);

      osc2.frequency.setValueAtTime(1318.5, now + 0.08);

      const peakVol = 0.16 * this.config.volume;
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(peakVol, now + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(now);
      osc2.start(now + 0.08);
      osc1.stop(now + 0.29);
      osc2.stop(now + 0.29);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 5. Error or Blocked Action Alert
   * Low digital error buzz / downward warning glitch.
   */
  public playErrorTone(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sawtooth';
      // Low downward glitch buzz 280Hz -> 140Hz
      osc.frequency.setValueAtTime(280, now);
      osc.frequency.exponentialRampToValueAtTime(140, now + 0.16);

      const peakVol = 0.12 * this.config.volume;
      gain.gain.setValueAtTime(peakVol, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.17);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.18);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 6. Voice Preview Start
   * Ascending frequency sweep when speech channel activates.
   */
  public playPreviewStart(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.09);

      const peakVol = 0.12 * this.config.volume;
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.linearRampToValueAtTime(peakVol, now + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.12);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 7. Voice Preview Stop
   * Descending chirp when speech channel halts.
   */
  public playPreviewStop(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    const ctx = this.getContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(320, now + 0.07);

      const peakVol = 0.1 * this.config.volume;
      gain.gain.setValueAtTime(peakVol, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.09);
    } catch {
      // Audio node failure recovery
    }
  }

  /**
   * 8. Named Asset: Microphone / Listening Cue
   * Triggers the authentic 'mic.wav' asset when voice capture is activated.
   * Deduplicated, volume-scaled, non-blocking, and safely degraded if Audio fails.
   */
  public playMicListeningCue(): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    if (typeof window === 'undefined') return;

    if (this.currentMicAudio && !this.currentMicAudio.paused) {
      return; // Already playing, avoid duplicate overlapping
    }

    try {
      if (typeof Audio !== 'undefined') {
        const audio = new Audio(resolveAssetUrl(SOUND_ASSET_PATHS.mic));
        audio.volume = Math.max(0, Math.min(1, this.config.volume));
        this.currentMicAudio = audio;

        audio.onended = () => {
          if (this.currentMicAudio === audio) {
            this.currentMicAudio = null;
          }
        };

        audio.onerror = () => {
          if (this.currentMicAudio === audio) {
            this.currentMicAudio = null;
          }
          // Fallback to synthetic click blip so user still receives audio cue
          this.playClick();
        };

        const promise = audio.play();
        if (promise && typeof promise.catch === 'function') {
          promise.catch(() => {
            if (this.currentMicAudio === audio) {
              this.currentMicAudio = null;
            }
          });
        }
      } else {
        this.playClick();
      }
    } catch {
      this.currentMicAudio = null;
    }
  }

  /**
   * Stop active microphone listening audio cue.
   */
  public stopMicListeningCue(): void {
    if (this.currentMicAudio) {
      try {
        this.currentMicAudio.pause();
        this.currentMicAudio.currentTime = 0;
      } catch {}
      this.currentMicAudio = null;
    }
  }

  /**
   * 9. Named Asset: Loading & Processing Cue
   * Triggers authentic 'loading.wav' asset during model inference, tool execution,
   * research, or audio synthesis loading.
   * Non-blocking, volume-controlled (calibrated so as not to overpower UI), deduplicated.
   */
  public playLoadingCue(loop = false): void {
    if (!this.config.enabled || this.config.volume <= 0) return;
    if (typeof window === 'undefined') return;

    if (this.currentLoadingAudio && !this.currentLoadingAudio.paused) {
      return; // Already active, avoid duplicate overlapping
    }

    try {
      if (typeof Audio !== 'undefined') {
        const audio = new Audio(resolveAssetUrl(SOUND_ASSET_PATHS.loading));
        // Calibrated at 60% of master volume for subtle background ambience
        audio.volume = Math.max(0, Math.min(1, this.config.volume * 0.6));
        audio.loop = loop;
        this.currentLoadingAudio = audio;

        audio.onended = () => {
          if (this.currentLoadingAudio === audio) {
            this.currentLoadingAudio = null;
          }
        };

        audio.onerror = () => {
          if (this.currentLoadingAudio === audio) {
            this.currentLoadingAudio = null;
          }
          // Fallback to synthetic processing pulse
          this.playProcessingPulse();
        };

        const promise = audio.play();
        if (promise && typeof promise.catch === 'function') {
          promise.catch(() => {
            if (this.currentLoadingAudio === audio) {
              this.currentLoadingAudio = null;
            }
          });
        }
      } else {
        this.playProcessingPulse();
      }
    } catch {
      this.currentLoadingAudio = null;
    }
  }

  /**
   * Stop and clean up any active loading or processing audio playback.
   */
  public stopLoadingCue(): void {
    if (this.currentLoadingAudio) {
      try {
        this.currentLoadingAudio.pause();
        this.currentLoadingAudio.currentTime = 0;
      } catch {}
      this.currentLoadingAudio = null;
    }
  }

  /**
   * Helper hook for input elements: filters out non-character keystrokes,
   * clipboard paste events, and active IME composition.
   */
  public handleKeyInputEvent(e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>): void {
    if (e.nativeEvent.isComposing) return;
    // Don't play for control/modifier/navigation keys
    if (
      e.key.length > 1 &&
      e.key !== 'Backspace' &&
      e.key !== 'Delete' &&
      e.key !== 'Enter'
    ) {
      return;
    }
    // Don't play for shortcuts like Ctrl+C, Ctrl+V, etc.
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    this.playTypingTick();
  }
}

export const soundEffects = new SoundEffectsService();
