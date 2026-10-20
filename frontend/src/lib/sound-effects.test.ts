import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

class MemoryStorage {
  private store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }

  clear(): void {
    this.store.clear();
  }
}

describe('SoundEffectsService', () => {
  let mockOscillator: any;
  let mockGain: any;
  let mockFilter: any;
  let mockAudioContext: any;
  let soundEffects: any;

  beforeEach(async () => {
    (globalThis as any).localStorage = new MemoryStorage();
    (globalThis as any).window = globalThis;

    mockOscillator = {
      type: 'sine',
      frequency: {
        setValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn(),
      },
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    };

    mockGain = {
      gain: {
        setValueAtTime: vi.fn(),
        linearRampToValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn(),
      },
      connect: vi.fn(),
    };

    mockFilter = {
      type: 'bandpass',
      frequency: { setValueAtTime: vi.fn() },
      Q: { setValueAtTime: vi.fn() },
      connect: vi.fn(),
    };

    mockAudioContext = {
      state: 'running',
      currentTime: 10,
      destination: {},
      createOscillator: vi.fn(() => mockOscillator),
      createGain: vi.fn(() => mockGain),
      createBiquadFilter: vi.fn(() => mockFilter),
      resume: vi.fn().mockResolvedValue(undefined),
    };

    function MockAudioContextClass() {
      return mockAudioContext;
    }
    (globalThis as any).AudioContext = MockAudioContextClass;

    const mod = await import('./sound-effects');
    soundEffects = mod.soundEffects;
    soundEffects.saveConfig({ enabled: true, volume: 0.5 });
    (soundEffects as any).ctx = null;
  });

  afterEach(() => {
    delete (globalThis as any).localStorage;
    delete (globalThis as any).AudioContext;
  });

  it('manages enabled and volume configurations with persistence', () => {
    soundEffects.setEnabled(false);
    expect(soundEffects.isEnabled()).toBe(false);

    soundEffects.setVolume(0.8);
    expect(soundEffects.getVolume()).toBe(0.8);

    // Caps bounds between 0 and 1
    soundEffects.setVolume(1.5);
    expect(soundEffects.getVolume()).toBe(1.0);
    soundEffects.setVolume(-0.5);
    expect(soundEffects.getVolume()).toBe(0.0);

    soundEffects.setEnabled(true);
    expect(soundEffects.isEnabled()).toBe(true);
  });

  it('plays click sound when enabled', () => {
    soundEffects.setEnabled(true);
    soundEffects.setVolume(0.5);

    soundEffects.playClick();

    expect(mockAudioContext.createOscillator).toHaveBeenCalled();
    expect(mockAudioContext.createGain).toHaveBeenCalled();
    expect(mockOscillator.start).toHaveBeenCalled();
    expect(mockOscillator.stop).toHaveBeenCalled();
  });

  it('silently ignores sounds when disabled or volume is 0', () => {
    soundEffects.setEnabled(false);
    soundEffects.playClick();
    expect(mockAudioContext.createOscillator).not.toHaveBeenCalled();

    soundEffects.setEnabled(true);
    soundEffects.setVolume(0);
    soundEffects.playSuccessChime();
    expect(mockAudioContext.createOscillator).not.toHaveBeenCalled();
  });

  it('throttles rapid typing ticks within threshold', () => {
    soundEffects.setEnabled(true);
    soundEffects.setVolume(0.5);

    soundEffects.playTypingTick();
    expect(mockAudioContext.createOscillator).toHaveBeenCalledTimes(1);

    // Call immediately again — should be throttled
    soundEffects.playTypingTick();
    expect(mockAudioContext.createOscillator).toHaveBeenCalledTimes(1);
  });

  it('safely filters non-typing events, paste events, and active IME composition', () => {
    soundEffects.setEnabled(true);
    soundEffects.setVolume(0.5);

    // Active composition (Urdu/Chinese IME)
    const imeEvent: any = {
      nativeEvent: { isComposing: true },
      key: 'a',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    };
    soundEffects.handleKeyInputEvent(imeEvent);
    expect(mockAudioContext.createOscillator).not.toHaveBeenCalled();

    // Modifier key (Shift, ArrowLeft, Escape)
    const modEvent: any = {
      nativeEvent: { isComposing: false },
      key: 'ArrowLeft',
      ctrlKey: false,
      metaKey: false,
      altKey: false,
    };
    soundEffects.handleKeyInputEvent(modEvent);
    expect(mockAudioContext.createOscillator).not.toHaveBeenCalled();

    // Ctrl+V paste
    const pasteEvent: any = {
      nativeEvent: { isComposing: false },
      key: 'v',
      ctrlKey: true,
      metaKey: false,
      altKey: false,
    };
    soundEffects.handleKeyInputEvent(pasteEvent);
    expect(mockAudioContext.createOscillator).not.toHaveBeenCalled();
  });

  it('plays success, error, and preview audio cues', () => {
    soundEffects.setEnabled(true);
    soundEffects.setVolume(0.5);

    soundEffects.playSuccessChime();
    expect(mockAudioContext.createOscillator).toHaveBeenCalled();

    soundEffects.playErrorTone();
    expect(mockOscillator.type).toBe('sawtooth');

    soundEffects.playPreviewStart();
    soundEffects.playPreviewStop();
  });

  it('handles playMicListeningCue and stopMicListeningCue with Audio element tracking', () => {
    const mockAudioInstances: any[] = [];
    class MockAudio {
      src: string;
      volume = 1;
      paused = false;
      currentTime = 0;
      onended: any = null;
      onerror: any = null;
      play = vi.fn().mockResolvedValue(undefined);
      pause = vi.fn().mockImplementation(() => { this.paused = true; });

      constructor(src: string) {
        this.src = src;
        mockAudioInstances.push(this);
      }
    }

    vi.stubGlobal('Audio', MockAudio);

    soundEffects.setEnabled(true);
    soundEffects.setVolume(0.7);

    soundEffects.playMicListeningCue();
    expect(mockAudioInstances.length).toBe(1);
    expect(mockAudioInstances[0].src).toContain('mic.wav');
    expect(mockAudioInstances[0].volume).toBeCloseTo(0.7);
    expect(mockAudioInstances[0].play).toHaveBeenCalled();

    // Deduplication: calling again while playing avoids creating duplicate
    soundEffects.playMicListeningCue();
    expect(mockAudioInstances.length).toBe(1);

    // Stop cue pauses and resets
    soundEffects.stopMicListeningCue();
    expect(mockAudioInstances[0].pause).toHaveBeenCalled();
    expect(mockAudioInstances[0].currentTime).toBe(0);

    vi.unstubAllGlobals();
  });

  it('handles playLoadingCue and stopLoadingCue with volume scaling and loop support', () => {
    const mockAudioInstances: any[] = [];
    class MockAudio {
      src: string;
      volume = 1;
      loop = false;
      paused = false;
      currentTime = 0;
      onended: any = null;
      onerror: any = null;
      play = vi.fn().mockResolvedValue(undefined);
      pause = vi.fn().mockImplementation(() => { this.paused = true; });

      constructor(src: string) {
        this.src = src;
        mockAudioInstances.push(this);
      }
    }

    vi.stubGlobal('Audio', MockAudio);

    soundEffects.setEnabled(true);
    soundEffects.setVolume(0.8);

    soundEffects.playLoadingCue(true);
    expect(mockAudioInstances.length).toBe(1);
    expect(mockAudioInstances[0].src).toContain('loading.wav');
    expect(mockAudioInstances[0].volume).toBeCloseTo(0.8 * 0.6);
    expect(mockAudioInstances[0].loop).toBe(true);
    expect(mockAudioInstances[0].play).toHaveBeenCalled();

    // Deduplication: second call while playing is ignored
    soundEffects.playLoadingCue(true);
    expect(mockAudioInstances.length).toBe(1);

    // Stopping cleans up element
    soundEffects.stopLoadingCue();
    expect(mockAudioInstances[0].pause).toHaveBeenCalled();
    expect(mockAudioInstances[0].currentTime).toBe(0);

    vi.unstubAllGlobals();
  });
});
