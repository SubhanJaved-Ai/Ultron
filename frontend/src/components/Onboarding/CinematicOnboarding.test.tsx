import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { CinematicOnboarding, PERSONA_PRESETS } from './CinematicOnboarding';

// Mock sound effects
vi.mock('../../lib/sound-effects', () => ({
  soundEffects: {
    isEnabled: () => true,
    getVolume: () => 0.6,
    setEnabled: vi.fn(),
    saveConfig: vi.fn(),
    playClick: vi.fn(),
    playPreviewStart: vi.fn(),
    playPreviewStop: vi.fn(),
    playSuccessChime: vi.fn(),
    playErrorTone: vi.fn(),
    handleKeyInputEvent: vi.fn(),
  },
}));

// Mock API
vi.mock('../../lib/api', () => ({
  fetchPersonalization: vi.fn().mockResolvedValue({
    user_name: 'Sir',
    presentation: 'neutral',
    persona: 'jarvis',
    language: 'en',
    sound_enabled: true,
    sound_volume: 0.6,
    onboarding_completed: false,
  }),
  updatePersonalization: vi.fn().mockResolvedValue({}),
  fetchVoiceSettings: vi.fn().mockResolvedValue({
    provider: 'system',
    voice_id: 'default',
  }),
  previewVoiceUtterance: vi.fn().mockResolvedValue({
    status: 'client_synthesis',
    text: 'Greetings, Sir. All diagnostic subroutines are green.',
  }),
}));

// Mock store
const mockUpdateSettings = vi.fn();
vi.mock('../../lib/store', () => ({
  useAppStore: (selector: any) =>
    selector({
      updateSettings: mockUpdateSettings,
    }),
}));

describe('CinematicOnboarding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('window', {
      devicePixelRatio: 2,
      requestAnimationFrame: (cb: any) => setTimeout(cb, 16),
      cancelAnimationFrame: vi.fn(),
      speechSynthesis: {
        speak: vi.fn(),
        cancel: vi.fn(),
        getVoices: vi.fn().mockReturnValue([]),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders Stage 1 with operator identification and particle core canvas', () => {
    const html = renderToStaticMarkup(
      <CinematicOnboarding onComplete={vi.fn()} onSkip={vi.fn()} />
    );

    expect(html).toContain('Operator Identification');
    expect(html).toContain('What should Ultron call you?');
    expect(html).toContain('01 IDENTITY');
    expect(html).toContain('Skip setup with default settings');
    expect(html).toContain('<canvas');
    expect(html).toContain('Ultron Electron — canonical particle core');
  });

  it('contains all 8 defined persona presets with valid English and Urdu samples', () => {
    expect(PERSONA_PRESETS.length).toBeGreaterThanOrEqual(8);
    const personaIds = PERSONA_PRESETS.map((p) => p.id);
    expect(personaIds).toContain('jarvis');
    expect(personaIds).toContain('assistant');
    expect(personaIds).toContain('mentor');
    expect(personaIds).toContain('best_friend');
    expect(personaIds).toContain('bro');
    expect(personaIds).toContain('listener');
    expect(personaIds).toContain('partner');
    expect(personaIds).toContain('core');

    for (const preset of PERSONA_PRESETS) {
      expect(preset.name.length).toBeGreaterThan(0);
      expect(preset.description.length).toBeGreaterThan(0);
      expect(preset.sampleEn.length).toBeGreaterThan(0);
      expect(preset.sampleUr.length).toBeGreaterThan(0);
      expect(preset.badge.length).toBeGreaterThan(0);
    }
  });

  it('renders skip button when onSkip is provided', () => {
    const htmlWithSkip = renderToStaticMarkup(
      <CinematicOnboarding onComplete={vi.fn()} onSkip={vi.fn()} />
    );
    expect(htmlWithSkip).toContain('Skip setup with default settings');

    const htmlWithoutSkip = renderToStaticMarkup(
      <CinematicOnboarding onComplete={vi.fn()} />
    );
    expect(htmlWithoutSkip).not.toContain('Skip setup with default settings');
  });

  it('includes interactive controls for cyber audio mute and canonical Electron column', () => {
    const html = renderToStaticMarkup(
      <CinematicOnboarding onComplete={vi.fn()} onSkip={vi.fn()} />
    );

    expect(html).toContain('Mute Cyber Audio Cues');
    expect(html).toContain('CANONICAL ELECTRON CORE');
  });

  it('applies premium white glassmorphism styling and eliminates dark container panels', () => {
    const html = renderToStaticMarkup(
      <CinematicOnboarding onComplete={vi.fn()} onSkip={vi.fn()} />
    );

    // Verify translucent white surface background
    expect(html).toContain('rgba(255, 255, 255, 0.94)');
    expect(html).toContain('rgba(248, 250, 252, 0.97)');
    expect(html).toContain('backdrop-blur');

    // Verify absence of old dark card container background
    expect(html).not.toContain('rgba(15, 23, 42, 0.94)');
    expect(html).not.toContain('bg-black/85');

    // Verify crisp dark readable typography
    expect(html).toContain('text-slate-900');
    expect(html).toContain('text-slate-700');
  });
});
