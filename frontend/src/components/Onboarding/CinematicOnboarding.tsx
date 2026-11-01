import React, { useState, useEffect, useRef } from 'react';
import {
  Volume2,
  VolumeX,
  Sparkles,
  Check,
  ChevronRight,
  ChevronLeft,
  AlertTriangle,
  User,
  Mic,
  Languages,
} from 'lucide-react';
import { UltronParticleCore } from '../Avatar/UltronParticleCore';
import type { ParticleVariant, ParticleState } from '../Avatar/particle-avatar.types';
import { soundEffects } from '../../lib/sound-effects';
import {
  fetchPersonalization,
  updatePersonalization,
  fetchVoiceSettings,
  type VoiceSettings,
} from '../../lib/api';
import { useAppStore } from '../../lib/store';

export interface CinematicOnboardingProps {
  onComplete: () => void;
  onSkip?: () => void;
}

export const PERSONA_PRESETS = [
  {
    id: 'jarvis',
    name: 'Jarvis',
    presentationAffinity: 'masculine',
    badge: 'Discreet & Composed',
    description: 'Articulate British understatement, unflappable composure, and polite dry wit.',
    sampleEn: 'Greetings, Sir. All diagnostic subroutines are green. Ready for your directive.',
    sampleUr: 'السلام علیکم۔ تمام نظام فعال ہیں اور میں آپ کے حکم کا منتظر ہوں۔',
  },
  {
    id: 'assistant',
    name: 'Assistant',
    presentationAffinity: 'neutral',
    badge: 'Concise & Professional',
    description: 'Crisp, highly structured, zero-fluff execution focused entirely on optimal throughput.',
    sampleEn: 'Standing by. Awaiting your operational specifications.',
    sampleUr: 'تیار ہوں۔ براہ کرم اپنی ہدایات فرمائیں۔',
  },
  {
    id: 'mentor',
    name: 'Mentor',
    presentationAffinity: 'feminine',
    badge: 'Patient & Thoughtful',
    description: 'Knowledgeable guide and patient teacher. Explains underlying principles clearly.',
    sampleEn: 'Take your time. Let us walk through the architecture step by step.',
    sampleUr: 'اطمینان رکھیے۔ آئیے مرحلہ وار اس تصور کو سمجھتے ہیں۔',
  },
  {
    id: 'best_friend',
    name: 'Best Friend',
    presentationAffinity: 'feminine',
    badge: 'Warm & Approachable',
    description: 'Supportive, conversational, warm, and highly intuitive while retaining full analytical power.',
    sampleEn: 'Hey there! Great to see you. What exciting project are we building today?',
    sampleUr: 'کیسے ہیں آپ؟ آج ہم کیا زبردست چیز بنانے جا رہے ہیں؟',
  },
  {
    id: 'bro',
    name: 'Bro',
    presentationAffinity: 'masculine',
    badge: 'Direct & Candid',
    description: 'Straight-talking, energetic, zero corporate jargon, informal and banter-friendly.',
    sampleEn: 'Yo! Systems locked and loaded. Tell me what we need to crush next.',
    sampleUr: 'کیا حال ہے بھائی! کام بتاؤ، ابھی نمٹا دیتے ہیں۔',
  },
  {
    id: 'listener',
    name: 'Listener',
    presentationAffinity: 'feminine',
    badge: 'Calm & Receptive',
    description: 'Attentive, empathetic, calm, and thoughtful. Focuses on nuance and deep reflection.',
    sampleEn: 'I am here. Share whatever is on your mind, and we will work through it.',
    sampleUr: 'میں سن رہا ہوں۔ جو بھی آپ کے ذہن میں ہے، کھل کر بیان کیجیے۔',
  },
  {
    id: 'partner',
    name: 'Partner',
    presentationAffinity: 'masculine',
    badge: 'Collaborative',
    description: 'Proactive co-pilot working shoulder-to-shoulder with you on shared technical challenges.',
    sampleEn: 'We are in this together. Let us synchronize our objectives and execute.',
    sampleUr: 'ہم مل کر کام کریں گے۔ آئیے اپنے اہداف پر توجہ مرکوز کریں۔',
  },
  {
    id: 'core',
    name: 'Ultron Core',
    presentationAffinity: 'neutral',
    badge: 'Neural Nexus',
    description: 'Pure neural computing matrix. Unbiased, deeply analytical, and mathematically precise.',
    sampleEn: 'Ultron neural lattice initialized. Ready to process multi-vector tasks.',
    sampleUr: 'الٹران نیورل نیٹ ورک فعال ہے۔ تمام سسٹمز تیار ہیں۔',
  },
];

export function CinematicOnboarding({ onComplete, onSkip }: CinematicOnboardingProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [userName, setUserName] = useState('Sir');
  const voiceGender = 'neutral';
  const [persona, setPersona] = useState('jarvis');
  const [language, setLanguage] = useState<'en' | 'ur' | 'hi' | 'auto'>('en');
  const [provider, setProvider] = useState('system');
  const [selectedVoiceId, setSelectedVoiceId] = useState('default');
  const [soundEnabled, setSoundEnabled] = useState(soundEffects.isEnabled());
  const [soundVolume, setSoundVolume] = useState(soundEffects.getVolume());

  const [avatarState, setAvatarState] = useState<ParticleState>('idle');
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Available Providers & Capabilities
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings | null>(null);
  const updateSettings = useAppStore((s) => s.updateSettings);

  useEffect(() => {
    // Load initial personalization from backend
    fetchPersonalization()
      .then((data) => {
        if (data.user_name) setUserName(data.user_name);
        if (data.persona) setPersona(data.persona);
        if (data.language) setLanguage(data.language);
        setSoundEnabled(data.sound_enabled);
        setSoundVolume(data.sound_volume);
        soundEffects.saveConfig({ enabled: data.sound_enabled, volume: data.sound_volume });
      })
      .catch(() => {});

    // Fetch voice settings and providers
    fetchVoiceSettings()
      .then((vs) => {
        setVoiceSettings(vs);
        if (vs.provider) setProvider(vs.provider);
        if (vs.voice_id) setSelectedVoiceId(vs.voice_id);
      })
      .catch(() => {});

    return () => {
      stopAudioPlayback();
      soundEffects.stopLoadingCue();
      soundEffects.stopMicListeningCue();
    };
  }, []);

  const toggleSound = () => {
    const next = !soundEnabled;
    setSoundEnabled(next);
    soundEffects.setEnabled(next);
    if (next) soundEffects.playClick();
  };

  const handleNextStep = () => {
    soundEffects.playClick();
    if (step === 1 && !userName.trim()) {
      setUserName('Sir');
    }
    if (step < 3) {
      setStep((s) => (s + 1) as 1 | 2 | 3);
    }
  };

  const handlePrevStep = () => {
    soundEffects.playClick();
    stopAudioPlayback();
    if (step > 1) {
      setStep((s) => (s - 1) as 1 | 2 | 3);
    }
  };

  const stopAudioPlayback = () => {
    soundEffects.stopLoadingCue();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setAvatarState('idle');
  };

  const handleFinish = async () => {
    soundEffects.playSuccessChime();
    stopAudioPlayback();

    const finalName = userName.trim() || 'Sir';

    // 1. Update backend preferences
    try {
      await updatePersonalization({
        user_name: finalName,
        phone_number: '',
        presentation: 'neutral',
        voice_presentation: 'neutral',
        voice_gender: 'neutral',
        persona,
        language,
        sound_enabled: soundEnabled,
        sound_volume: soundVolume,
        onboarding_completed: true,
      });
    } catch {
      // Non-fatal fallback to frontend store
    }

    // 2. Update frontend store
    updateSettings({
      userName: finalName,
      voicePresentation: 'neutral',
      voiceGender: 'neutral',
      persona,
      language,
      notificationPhone: '',
      soundEnabled,
      soundVolume,
      onboardingCompleted: true,
    });

    onComplete();
  };

  const activePersonaObj = PERSONA_PRESETS.find((p) => p.id === persona) || PERSONA_PRESETS[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/35 backdrop-blur-xl animate-fade-in text-slate-800 selection:bg-cyan-500 selection:text-white">
      <div
        className="relative w-full max-w-4xl max-h-[92vh] overflow-y-auto rounded-3xl flex flex-col shadow-2xl transition-all"
        style={{
          background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.94) 0%, rgba(248, 250, 252, 0.97) 100%)',
          backdropFilter: 'blur(30px) saturate(190%)',
          WebkitBackdropFilter: 'blur(30px) saturate(190%)',
          border: '1px solid rgba(255, 255, 255, 0.9)',
          boxShadow: '0 25px 60px -15px rgba(15, 23, 42, 0.15), 0 0 35px rgba(6, 182, 212, 0.12), inset 0 1px 2px rgba(255, 255, 255, 1)',
        }}
      >
        {/* Top Header Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200/80 bg-white/70 backdrop-blur-md rounded-t-3xl">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-cyan-50 border border-cyan-200 flex items-center justify-center text-cyan-600 shadow-sm">
              <Sparkles size={17} />
            </div>
            <div>
              <span className="text-sm font-bold tracking-wider text-slate-900">ULTRON</span>
              <span className="text-xs text-slate-500 ml-2 font-mono">NEURAL ONBOARDING</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Step progress pills */}
            <div className="flex items-center gap-1.5 text-xs font-mono">
              <span
                className={`px-2.5 py-1 rounded-full transition-all ${
                  step === 1
                    ? 'bg-cyan-500 text-white font-bold shadow-sm shadow-cyan-500/30'
                    : step > 1
                      ? 'bg-slate-100 text-slate-700 font-medium'
                      : 'text-slate-400'
                }`}
              >
                01 IDENTITY
              </span>
              <span className="text-slate-300">/</span>
              <span
                className={`px-2.5 py-1 rounded-full transition-all ${
                  step === 2
                    ? 'bg-cyan-500 text-white font-bold shadow-sm shadow-cyan-500/30'
                    : step > 2
                      ? 'bg-slate-100 text-slate-700 font-medium'
                      : 'text-slate-400'
                }`}
              >
                02 PERSONA
              </span>
              <span className="text-slate-300">/</span>
              <span
                className={`px-2.5 py-1 rounded-full transition-all ${
                  step === 3
                    ? 'bg-cyan-500 text-white font-bold shadow-sm shadow-cyan-500/30'
                    : 'text-slate-400'
                }`}
              >
                03 SYNTHESIS
              </span>
            </div>

            {/* Sound Mute Toggle */}
            <button
              onClick={toggleSound}
              title={soundEnabled ? 'Mute Cyber Audio Cues' : 'Enable Cyber Audio Cues'}
              className="p-2 rounded-xl border border-slate-200 bg-white/80 hover:bg-slate-50 text-slate-600 hover:text-cyan-600 shadow-sm transition-colors cursor-pointer"
            >
              {soundEnabled ? <Volume2 size={16} className="text-cyan-600" /> : <VolumeX size={16} className="text-slate-400" />}
            </button>
          </div>
        </div>

        {/* Main Content Area */}
        <div className="p-6 sm:p-8 flex-1 grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
          {/* Left Column: Stage-Specific Controls (7 cols) */}
          <div className="md:col-span-7 space-y-6">
            {/* ----------------- STAGE 1: PERSONALIZATION ----------------- */}
            {step === 1 && (
              <div className="space-y-5 animate-fade-in">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                    <User className="text-cyan-600" size={24} />
                    Operator Identification
                  </h2>
                  <p className="text-sm text-slate-600 mt-1">
                    Calibrate how Ultron addresses you across speech channels and autonomous terminal sessions.
                  </p>
                </div>

                <div className="space-y-3">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                    What should Ultron call you?
                  </label>
                  <input
                    type="text"
                    value={userName}
                    onChange={(e) => setUserName(e.target.value)}
                    onKeyDown={(e) => soundEffects.handleKeyInputEvent(e)}
                    placeholder="e.g. Sir, Boss, Tony, Commander"
                    className="w-full px-4 py-3 rounded-xl bg-white/90 border border-slate-200/90 focus:border-cyan-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 text-slate-900 placeholder-slate-400 text-base shadow-sm transition-all"
                    autoFocus
                  />
                  <p className="text-xs text-slate-500">
                    Ultron operates offline. This address remains stored exclusively on your local workstation.
                  </p>
                </div>

              </div>
            )}

            {/* ----------------- STAGE 2: BEHAVIORAL PERSONA CALIBRATION ----------------- */}
            {step === 2 && (
              <div className="space-y-5 animate-fade-in">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                    <Sparkles className="text-cyan-600" size={24} />
                    Behavioral Persona Calibration
                  </h2>
                  <p className="text-sm text-slate-600 mt-1">
                    Calibrate Ultron&apos;s demeanor, conversational tone, and response register.
                  </p>
                </div>

                {/* Persona Selection Cards */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-2">
                    Select Ultron Persona Register
                  </label>
                  <div className="grid grid-cols-2 gap-2.5 max-h-72 overflow-y-auto pr-1">
                    {PERSONA_PRESETS.map((p) => {
                      const isSelected = persona === p.id;
                      return (
                        <div
                          key={p.id}
                          onClick={() => {
                            setPersona(p.id);
                            soundEffects.playClick();
                          }}
                          className={`p-3.5 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between ${
                            isSelected
                              ? 'border-cyan-500 bg-cyan-50/90 text-slate-900 shadow-md shadow-cyan-500/10 ring-2 ring-cyan-500/20'
                              : 'border-slate-200/80 bg-white/80 text-slate-700 hover:border-cyan-300 hover:bg-white hover:shadow-sm'
                          }`}
                        >
                          <div>
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-semibold text-sm text-slate-900">{p.name}</span>
                              {isSelected && <Check size={14} className="text-cyan-600" />}
                            </div>
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                                isSelected ? 'bg-cyan-100 text-cyan-800' : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {p.badge}
                            </span>
                            <p className="text-xs text-slate-600 mt-1.5 line-clamp-2 leading-relaxed">
                              {p.description}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* ----------------- STAGE 3: LANGUAGE & AUDIO SYNTHESIS ----------------- */}
            {step === 3 && (
              <div className="space-y-5 animate-fade-in">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                    <Mic className="text-cyan-600" size={24} />
                    Language & Voice Engine
                  </h2>
                  <p className="text-sm text-slate-600 mt-1">
                    Choose interaction language, select voice timbre, and test speech synthesis.
                  </p>
                </div>

                {/* Language Switcher */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-2 flex items-center gap-1.5">
                    <Languages size={14} /> Spoken & Interaction Language
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setLanguage('en');
                        soundEffects.playClick();
                      }}
                      className={`py-2 px-2.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer text-center ${
                        language === 'en'
                          ? 'border-cyan-500 bg-cyan-50 text-cyan-800 shadow-sm ring-1 ring-cyan-500/20'
                          : 'border-slate-200 bg-white/80 text-slate-700 hover:border-cyan-300 hover:bg-white shadow-sm'
                      }`}
                    >
                      English (US/UK)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setLanguage('ur');
                        soundEffects.playClick();
                      }}
                      className={`py-2 px-2.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer text-center ${
                        language === 'ur'
                          ? 'border-cyan-500 bg-cyan-50 text-cyan-800 shadow-sm ring-1 ring-cyan-500/20'
                          : 'border-slate-200 bg-white/80 text-slate-700 hover:border-cyan-300 hover:bg-white shadow-sm'
                      }`}
                    >
                      اردو (Urdu)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setLanguage('hi');
                        soundEffects.playClick();
                      }}
                      className={`py-2 px-2.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer text-center ${
                        language === 'hi'
                          ? 'border-cyan-500 bg-cyan-50 text-cyan-800 shadow-sm ring-1 ring-cyan-500/20'
                          : 'border-slate-200 bg-white/80 text-slate-700 hover:border-cyan-300 hover:bg-white shadow-sm'
                      }`}
                    >
                      हिंदी (Hindi)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setLanguage('auto');
                        soundEffects.playClick();
                      }}
                      className={`py-2 px-2.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer text-center ${
                        language === 'auto'
                          ? 'border-cyan-500 bg-cyan-50 text-cyan-800 shadow-sm ring-1 ring-cyan-500/20'
                          : 'border-slate-200 bg-white/80 text-slate-700 hover:border-cyan-300 hover:bg-white shadow-sm'
                      }`}
                    >
                      Auto-Detect
                    </button>
                  </div>
                </div>

                {/* Free Provider vs Paid Cloud Notice */}
                {language === 'ur' && provider === 'system' && (
                  <div className="p-3 rounded-xl border border-amber-300 bg-amber-50/95 text-xs text-amber-900 space-y-1 shadow-sm">
                    <div className="flex items-center gap-1.5 font-semibold text-amber-800">
                      <AlertTriangle size={15} />
                      Local Urdu TTS Advisory
                    </div>
                    <p className="leading-relaxed text-[11px] text-amber-800/90">
                      Windows SAPI lacks built-in Urdu voice models. Ultron will respond in fluent Urdu text. Spoken Urdu voice is routed via local Piper (if installed) or connected cloud neural TTS.
                    </p>
                  </div>
                )}

                {/* Voice Provider Selection */}
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-2">
                    Speech Provider Engine
                  </label>
                  <select
                    value={provider}
                    onChange={(e) => {
                      setProvider(e.target.value);
                      soundEffects.playClick();
                    }}
                    className="w-full px-4 py-2.5 rounded-xl bg-white/90 border border-slate-200 text-slate-900 text-sm focus:border-cyan-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-cyan-500/20 shadow-sm cursor-pointer"
                  >
                    <option value="system">System / Browser Voice (100% Free & Private)</option>
                    <option value="elevenlabs">ElevenLabs Multilingual (Cloud Neural)</option>
                    <option value="openai_tts">OpenAI Speech TTS-1 (Cloud Neural)</option>
                  </select>
                </div>

              </div>
            )}
          </div>

          {/* Right Column: Canonical Holographic Particle Avatar Core (5 cols) */}
          <div className="md:col-span-5 flex flex-col items-center justify-center p-4">
            <div
              className="relative flex items-center justify-center p-3 rounded-3xl border border-white/80 shadow-sm"
              style={{
                background: 'linear-gradient(135deg, rgba(240, 249, 255, 0.75) 0%, rgba(224, 242, 254, 0.55) 100%)',
                backdropFilter: 'blur(16px)',
                WebkitBackdropFilter: 'blur(16px)',
                boxShadow: '0 10px 30px -5px rgba(6, 182, 212, 0.12), inset 0 1px 3px rgba(255, 255, 255, 0.95)',
              }}
            >
              <UltronParticleCore
                variant="neutral"
                state={avatarState}
                size={320}
                showReticle={true}
                themeColor="#0891b2"
              />
            </div>

            <div className="mt-3 text-center">
              <div className="text-xs font-mono tracking-wider text-cyan-700 font-bold">
                CANONICAL ELECTRON CORE
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                State: {avatarState} • Synaptic Nexus Synchronized
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Navigation & Actions */}
        <div className="px-6 py-4 border-t border-slate-200/80 bg-white/70 backdrop-blur-md flex items-center justify-between rounded-b-3xl">
          <div>
            {step > 1 ? (
              <button
                onClick={handlePrevStep}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm cursor-pointer"
              >
                <ChevronLeft size={16} /> BACK
              </button>
            ) : onSkip ? (
              <button
                onClick={() => {
                  soundEffects.playClick();
                  onSkip();
                }}
                className="text-xs text-slate-500 hover:text-slate-800 cursor-pointer transition-colors font-medium"
              >
                Skip setup with default settings
              </button>
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            {step < 3 ? (
              <button
                onClick={handleNextStep}
                className="px-6 py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold uppercase tracking-wider flex items-center gap-2 shadow-md shadow-cyan-600/25 transition-all cursor-pointer"
              >
                CONTINUE <ChevronRight size={16} />
              </button>
            ) : (
              <button
                onClick={handleFinish}
                className="px-7 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold uppercase tracking-wider flex items-center gap-2 shadow-lg shadow-cyan-600/25 transition-all cursor-pointer"
              >
                <Sparkles size={16} /> INITIALIZE ULTRON
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
