import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  MessageSquare,
  ArrowLeft,
  Radio,
  ExternalLink,
  Settings,
  X,
  Volume2,
  Cpu,
  Key,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Server,
  Zap,
} from 'lucide-react';
import { getBase } from '../lib/api';
import { useAppStore } from '../lib/store';

interface ConfigState {
  voice_provider: string;
  voice_id: string;
  model_id: string;
  elevenlabs_key_configured: boolean;
  elevenlabs_key_masked: string;
  llm_provider?: 'gemini' | 'ollama' | 'openai';
  ollama_url?: string;
  ollama_model?: string;
  ollama_connected?: boolean;
  gemini_key_configured: boolean;
  gemini_key_masked: string;
  openai_key_configured?: boolean;
  openai_key_masked?: string;
  active_engine?: string;
  brain_engine?: string;
}

export function HologramPage() {
  const navigate = useNavigate();
  const apiBase = getBase();
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const themeSetting = useAppStore((s) => s.settings.theme);

  // Compute active theme mode ('dark' or 'light')
  const [currentMode, setCurrentMode] = useState<'dark' | 'light'>(() => {
    if (themeSetting === 'dark') return 'dark';
    if (themeSetting === 'light') return 'light';
    if (
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: light)').matches
    ) {
      return 'light';
    }
    return 'dark';
  });

  // Drawer & Config state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [config, setConfig] = useState<ConfigState | null>(null);
  const [elevenKey, setElevenKey] = useState('');
  const [voiceId, setVoiceId] = useState('');

  // Multi-Provider Brain settings
  const [provider, setProvider] = useState<'gemini' | 'ollama' | 'openai'>('gemini');
  const [geminiKey, setGeminiKey] = useState('');
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState('llama3.2');
  const [openaiKey, setOpenaiKey] = useState('');
  const [openaiModel, setOpenaiModel] = useState('gpt-4o-mini');

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [activeSessionUntil, setActiveSessionUntil] = useState<number>(() => Date.now() + 5 * 60 * 1000);

  useEffect(() => {
    loadConfig();

    // Auto-unlock Web Audio on first user interaction
    const unlockAudio = () => {
      try {
        const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
        if (AudioCtx) {
          const ctx = new AudioCtx();
          if (ctx.state === 'suspended') void ctx.resume();
        }
      } catch {}
      window.removeEventListener('click', unlockAudio);
      window.removeEventListener('keydown', unlockAudio);
    };
    window.addEventListener('click', unlockAudio);
    window.addEventListener('keydown', unlockAudio);

    // Listen to iframe session messages
    const handleMsg = (e: MessageEvent) => {
      if (e.data && e.data.type === 'EXTEND_SESSION') {
        setActiveSessionUntil(Date.now() + 5 * 60 * 1000);
      }
    };
    window.addEventListener('message', handleMsg);

    return () => {
      window.removeEventListener('click', unlockAudio);
      window.removeEventListener('keydown', unlockAudio);
      window.removeEventListener('message', handleMsg);
    };
  }, []);

  useEffect(() => {
    let mode: 'dark' | 'light' = 'dark';
    if (themeSetting === 'dark') {
      mode = 'dark';
    } else if (themeSetting === 'light') {
      mode = 'light';
    } else if (
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: light)').matches
    ) {
      mode = 'light';
    } else {
      mode = 'dark';
    }
    setCurrentMode(mode);

    if (iframeRef.current && iframeRef.current.contentWindow) {
      try {
        iframeRef.current.contentWindow.postMessage({ type: 'SET_THEME_MODE', mode }, '*');
      } catch (e) {}
    }
  }, [themeSetting]);

  const loadConfig = async () => {
    try {
      const res = await fetch(`${apiBase}/api/hologram/config`);
      if (res.ok) {
        const data: ConfigState = await res.json();
        setConfig(data);
        if (data.voice_id) setVoiceId(data.voice_id);
        if (data.llm_provider) setProvider(data.llm_provider);
        if (data.ollama_url) setOllamaUrl(data.ollama_url);
        if (data.ollama_model) setOllamaModel(data.ollama_model);
      }
    } catch (e) {}
  };

  const handleOpenDrawer = () => {
    setDrawerOpen(true);
    setSaveSuccess(null);
    setSaveError(null);
    loadConfig();
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    setSaveSuccess(null);
    setSaveError(null);
    try {
      const payload: Record<string, string> = {
        llm_provider: provider,
        ollama_url: ollamaUrl.trim(),
        ollama_model: ollamaModel.trim(),
        openai_model: openaiModel.trim(),
      };
      if (elevenKey.trim()) payload.elevenlabs_api_key = elevenKey.trim();
      if (voiceId.trim()) payload.elevenlabs_voice_id = voiceId.trim();
      if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim();
      if (openaiKey.trim()) payload.openai_api_key = openaiKey.trim();

      const res = await fetch(`${apiBase}/api/hologram/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setSaveSuccess('Universal Brain configuration saved & active provider hot-reloaded.');
        setElevenKey('');
        setGeminiKey('');
        setOpenaiKey('');
        await loadConfig();
      } else {
        setSaveError('Failed to save configuration. Please try again.');
      }
    } catch (e: any) {
      setSaveError(e.message || 'Connection error.');
    } finally {
      setSaving(false);
    }
  };

  const handleIframeLoad = () => {
    if (iframeRef.current && iframeRef.current.contentWindow) {
      try {
        iframeRef.current.contentWindow.postMessage({ type: 'SET_THEME_MODE', mode: currentMode }, '*');
      } catch (e) {}
    }
  };

  const hologramUrl = `${apiBase}/hologram.html?mode=${currentMode}`;

  // Compute live provider status badge
  const renderProviderBadge = () => {
    const activeProv = config?.llm_provider || 'gemini';
    if (activeProv === 'ollama') {
      const isOk = config?.ollama_connected;
      return (
        <div
          onClick={handleOpenDrawer}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono cursor-pointer transition-all border ${
            isOk
              ? 'bg-sky-500/10 border-sky-500/30 text-sky-600 dark:text-sky-400 hover:bg-sky-500/20 shadow-[0_0_8px_rgba(56,189,248,0.15)]'
              : 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 shadow-[0_0_8px_rgba(245,158,11,0.15)]'
          }`}
          title={
            isOk
              ? `Local Ollama Active (${config?.ollama_model || 'llama3.2'}). Click to configure.`
              : 'Ollama Unreachable; Resilient Local Fallback Active. Click to configure.'
          }
        >
          <span className={`w-1.5 h-1.5 rounded-full ${isOk ? 'bg-sky-400 animate-pulse' : 'bg-amber-400'}`} />
          <span>{isOk ? `Ollama (${config?.ollama_model || 'llama3.2'})` : 'Ollama (Offline Fallback)'}</span>
        </div>
      );
    }

    if (activeProv === 'openai') {
      const isOk = config?.openai_key_configured;
      return (
        <div
          onClick={handleOpenDrawer}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono cursor-pointer transition-all border ${
            isOk
              ? 'bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 shadow-[0_0_8px_rgba(168,85,247,0.15)]'
              : 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 shadow-[0_0_8px_rgba(245,158,11,0.15)]'
          }`}
          title={
            isOk
              ? 'OpenAI API Active. Click to configure.'
              : 'OpenAI Key Missing; Local Heuristic Fallback Active. Click to configure.'
          }
        >
          <span className={`w-1.5 h-1.5 rounded-full ${isOk ? 'bg-purple-400 animate-pulse' : 'bg-amber-400'}`} />
          <span>{isOk ? 'OpenAI GPT-4o' : 'OpenAI (No Key)'}</span>
        </div>
      );
    }

    // Default: Gemini
    const isOk = config?.gemini_key_configured;
    return (
      <div
        onClick={handleOpenDrawer}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono cursor-pointer transition-all border ${
          isOk
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 shadow-[0_0_8px_rgba(16,185,129,0.15)]'
            : 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 shadow-[0_0_8px_rgba(245,158,11,0.15)]'
        }`}
        title={
          isOk
            ? 'Gemini 3.8 Flash Cloud LLM Active. Click to configure.'
            : 'Local Heuristics Fallback Active (No Gemini API Key). Click to connect Gemini.'
        }
      >
        <span className={`w-1.5 h-1.5 rounded-full ${isOk ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
        <span>{isOk ? 'Gemini 3.8 Flash' : 'Local Fallback'}</span>
      </div>
    );
  };

  const commonModels = ['llama3.2', 'qwen2.5', 'deepseek-r1', 'mistral', 'phi3'];

  return (
    <div className="flex flex-col h-full w-full bg-slate-100 dark:bg-[#060b13] text-slate-800 dark:text-slate-100 overflow-hidden relative">
      {/* Top Floating Glassmorphic Nav */}
      <header className="flex items-center justify-between px-4 py-2.5 z-20 shrink-0 bg-white/95 dark:bg-zinc-950/90 backdrop-blur-md border-b border-slate-200 dark:border-cyan-500/20 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer bg-slate-100 hover:bg-white text-slate-700 hover:text-slate-900 border border-slate-300 dark:bg-zinc-900 dark:hover:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-200 dark:hover:text-white shadow-sm"
            title="Return to standard chat interface"
          >
            <ArrowLeft size={13} />
            <span>Chat</span>
          </button>

          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full animate-ping bg-cyan-400" />
            <span
              className="text-xs font-semibold uppercase tracking-wider font-mono text-cyan-600 dark:text-cyan-400"
              style={{ letterSpacing: '0.1em' }}
            >
              Ultron 3D Matrix
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Live Dynamic Multi-Provider Brain Status Indicator */}
          {renderProviderBadge()}

          {/* 5-Minute Continuous Session Status Indicator */}
          {Date.now() < activeSessionUntil && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>5M Continuous Voice Active</span>
            </div>
          )}

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono bg-cyan-500/10 border border-cyan-500/40 text-cyan-700 dark:text-cyan-300 shadow-[0_0_10px_rgba(0,229,255,0.15)]">
            <Radio size={11} className="animate-pulse text-cyan-400" />
            <span>Voice & Audio Reactive</span>
          </div>

          <a
            href={hologramUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 dark:bg-zinc-900/90 dark:hover:bg-cyan-950/60 dark:border-cyan-500/40 dark:hover:border-cyan-400 dark:text-cyan-300 dark:hover:text-cyan-200 shadow-sm dark:shadow-[0_0_12px_rgba(0,229,255,0.15)]"
            title="Open 3D Hologram in full browser window"
          >
            <ExternalLink size={13} />
            <span>Open Fullscreen</span>
          </a>

          {/* ⚙ Config Button */}
          <button
            onClick={handleOpenDrawer}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 dark:bg-zinc-900/90 dark:hover:bg-cyan-950/60 dark:border-cyan-500/40 dark:hover:border-cyan-400 dark:text-cyan-300 dark:hover:text-cyan-200 shadow-sm dark:shadow-[0_0_12px_rgba(0,229,255,0.15)]"
            title="Configure LLM Provider (Gemini / Ollama / OpenAI) & Voice"
          >
            <Settings size={13} className="text-cyan-400" />
            <span>Config</span>
          </button>

          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer bg-cyan-600/10 hover:bg-cyan-600/20 text-cyan-800 border border-cyan-600/30 dark:bg-cyan-500/15 dark:hover:bg-cyan-500/25 dark:border-cyan-400/50 dark:hover:border-cyan-300 dark:text-cyan-300 dark:hover:text-cyan-100 dark:shadow-[0_0_15px_rgba(0,229,255,0.2)]"
            title="Switch back to Chat interface"
          >
            <MessageSquare size={13} />
            <span>Switch to Chat</span>
          </button>
        </div>
      </header>

      {/* Hologram Matrix Canvas Viewport */}
      <div className="flex-1 w-full h-full relative overflow-hidden bg-slate-100 dark:bg-[#060b13]">
        <iframe
          ref={iframeRef}
          onLoad={handleIframeLoad}
          src={hologramUrl}
          title="Ultron 3D Quantum Hologram"
          className="w-full h-full border-0 absolute inset-0"
          allow="microphone; camera; display-capture; autoplay"
          style={{ width: '100%', height: '100%' }}
        />
      </div>

      {/* Slide-over Config Drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity">
          <div className="w-full max-w-md h-full bg-white dark:bg-zinc-950 border-l border-slate-200 dark:border-cyan-500/30 shadow-2xl flex flex-col p-5 overflow-y-auto">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <Settings size={16} className="text-cyan-500" />
                <h3 className="font-semibold text-sm tracking-tight text-slate-900 dark:text-zinc-100">
                  Ultron Intelligence & Brain Config
                </h3>
              </div>
              <button
                onClick={() => setDrawerOpen(false)}
                className="p-1 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            {/* Notification Messages */}
            {saveSuccess && (
              <div className="mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-2">
                <CheckCircle2 size={14} className="shrink-0" />
                <span>{saveSuccess}</span>
              </div>
            )}
            {saveError && (
              <div className="mt-3 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs flex items-center gap-2">
                <AlertCircle size={14} className="shrink-0" />
                <span>{saveError}</span>
              </div>
            )}

            {/* Configuration Sections */}
            <div className="mt-5 space-y-6 flex-1 text-xs">

              {/* Frontier LLM Brain Multi-Provider Section */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-zinc-300">
                    <Cpu size={14} className="text-cyan-500" />
                    <span className="uppercase tracking-wider font-mono text-[11px]">
                      Reasoning Brain Architecture
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-cyan-600 dark:text-cyan-400">
                    {config?.active_engine || 'offline_local_rules'}
                  </span>
                </div>

                {/* 3-Tab Segmented Provider Selector */}
                <div className="grid grid-cols-3 gap-1 p-1 bg-slate-100 dark:bg-zinc-900 rounded-lg border border-slate-200 dark:border-zinc-800">
                  <button
                    type="button"
                    onClick={() => setProvider('gemini')}
                    className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md font-medium text-xs transition-all ${
                      provider === 'gemini'
                        ? 'bg-white dark:bg-zinc-800 text-cyan-600 dark:text-cyan-300 shadow-sm font-semibold'
                        : 'text-slate-500 dark:text-zinc-400 hover:text-slate-800 dark:hover:text-zinc-200'
                    }`}
                  >
                    <Sparkles size={12} className={provider === 'gemini' ? 'text-cyan-400' : ''} />
                    <span>Gemini</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setProvider('ollama')}
                    className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md font-medium text-xs transition-all ${
                      provider === 'ollama'
                        ? 'bg-white dark:bg-zinc-800 text-sky-600 dark:text-sky-300 shadow-sm font-semibold'
                        : 'text-slate-500 dark:text-zinc-400 hover:text-slate-800 dark:hover:text-zinc-200'
                    }`}
                  >
                    <Server size={12} className={provider === 'ollama' ? 'text-sky-400' : ''} />
                    <span>Ollama (Local)</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setProvider('openai')}
                    className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md font-medium text-xs transition-all ${
                      provider === 'openai'
                        ? 'bg-white dark:bg-zinc-800 text-purple-600 dark:text-purple-300 shadow-sm font-semibold'
                        : 'text-slate-500 dark:text-zinc-400 hover:text-slate-800 dark:hover:text-zinc-200'
                    }`}
                  >
                    <Zap size={12} className={provider === 'openai' ? 'text-purple-400' : ''} />
                    <span>OpenAI</span>
                  </button>
                </div>

                {/* Sub-panel: Gemini */}
                {provider === 'gemini' && (
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-zinc-900/60 border border-slate-200 dark:border-zinc-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500 dark:text-zinc-400">Gemini Status:</span>
                      <span
                        className={`font-mono text-[11px] ${
                          config?.gemini_key_configured
                            ? 'text-emerald-500 font-semibold'
                            : 'text-amber-500 dark:text-amber-400'
                        }`}
                      >
                        {config?.gemini_key_configured
                          ? config.gemini_key_masked || 'Configured (3.8 Flash)'
                          : 'Key Missing (Smart Local Fallback Active)'}
                      </span>
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                        Google Gemini API Key
                      </label>
                      <input
                        type="password"
                        value={geminiKey}
                        onChange={(e) => setGeminiKey(e.target.value)}
                        placeholder={config?.gemini_key_configured ? 'Enter new key to replace' : 'AIzaSy...'}
                        className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                      />
                      <p className="text-[10px] text-slate-400 dark:text-zinc-500 mt-1">
                        Key starts with <code className="font-mono">AIzaSy</code> from Google AI Studio.
                      </p>
                    </div>
                  </div>
                )}

                {/* Sub-panel: Ollama (Local LLM) */}
                {provider === 'ollama' && (
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-zinc-900/60 border border-slate-200 dark:border-zinc-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500 dark:text-zinc-400">Local Connection:</span>
                      <span
                        className={`font-mono text-[11px] flex items-center gap-1 ${
                          config?.ollama_connected
                            ? 'text-emerald-500 font-semibold'
                            : 'text-amber-500 dark:text-amber-400'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${config?.ollama_connected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                        {config?.ollama_connected ? 'Connected (Port 11434)' : 'Unreachable (Start Ollama locally)'}
                      </span>
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                        Ollama Base URL
                      </label>
                      <input
                        type="text"
                        value={ollamaUrl}
                        onChange={(e) => setOllamaUrl(e.target.value)}
                        placeholder="http://localhost:11434"
                        className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                        Model Name
                      </label>
                      <input
                        type="text"
                        value={ollamaModel}
                        onChange={(e) => setOllamaModel(e.target.value)}
                        placeholder="llama3.2"
                        className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                      />

                      {/* Model Quick Chips */}
                      <div className="flex flex-wrap gap-1 mt-2">
                        {commonModels.map((m) => (
                          <button
                            key={m}
                            type="button"
                            onClick={() => setOllamaModel(m)}
                            className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-all ${
                              ollamaModel === m
                                ? 'bg-sky-500/20 border-sky-400 text-sky-600 dark:text-sky-300 font-semibold'
                                : 'bg-slate-100 dark:bg-zinc-800 border-slate-300 dark:border-zinc-700 text-slate-600 dark:text-zinc-400 hover:text-slate-900 dark:hover:text-zinc-200'
                            }`}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                      <p className="text-[10px] text-slate-400 dark:text-zinc-500 mt-1.5">
                        Run <code className="font-mono">ollama run {ollamaModel || 'llama3.2'}</code> in terminal to pull model.
                      </p>
                    </div>
                  </div>
                )}

                {/* Sub-panel: OpenAI */}
                {provider === 'openai' && (
                  <div className="p-3 rounded-lg bg-slate-50 dark:bg-zinc-900/60 border border-slate-200 dark:border-zinc-800 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500 dark:text-zinc-400">OpenAI Key Status:</span>
                      <span
                        className={`font-mono text-[11px] ${
                          config?.openai_key_configured
                            ? 'text-emerald-500 font-semibold'
                            : 'text-amber-500 dark:text-amber-400'
                        }`}
                      >
                        {config?.openai_key_configured
                          ? config.openai_key_masked || 'Configured'
                          : 'No API Key Configured'}
                      </span>
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                        OpenAI API Key
                      </label>
                      <input
                        type="password"
                        value={openaiKey}
                        onChange={(e) => setOpenaiKey(e.target.value)}
                        placeholder={config?.openai_key_configured ? 'Enter new key to replace' : 'sk-...'}
                        className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                        OpenAI Model
                      </label>
                      <input
                        type="text"
                        value={openaiModel}
                        onChange={(e) => setOpenaiModel(e.target.value)}
                        placeholder="gpt-4o-mini"
                        className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Voice Synthesizer Section */}
              <div className="space-y-3 pt-2 border-t border-slate-200 dark:border-zinc-800/80">
                <div className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-zinc-300">
                  <Volume2 size={14} className="text-cyan-500" />
                  <span className="uppercase tracking-wider font-mono text-[11px]">
                    Speech Synthesizer (TTS)
                  </span>
                </div>

                <div className="p-3 rounded-lg bg-slate-50 dark:bg-zinc-900/60 border border-slate-200 dark:border-zinc-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 dark:text-zinc-400">Current Provider:</span>
                    <span className="font-mono text-cyan-600 dark:text-cyan-400 font-semibold">
                      {config?.voice_provider === 'elevenlabs'
                        ? 'ElevenLabs'
                        : 'edge-tts (Neural Streaming)'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 dark:text-zinc-400">ElevenLabs Key:</span>
                    <span
                      className={`font-mono ${
                        config?.elevenlabs_key_configured
                          ? 'text-emerald-500'
                          : 'text-amber-500 dark:text-amber-400'
                      }`}
                    >
                      {config?.elevenlabs_key_configured
                        ? config.elevenlabs_key_masked || 'Configured'
                        : 'Fallback (edge-tts)'}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                    ElevenLabs API Key (Optional)
                  </label>
                  <input
                    type="password"
                    value={elevenKey}
                    onChange={(e) => setElevenKey(e.target.value)}
                    placeholder={
                      config?.elevenlabs_key_configured
                        ? 'Enter new key to replace'
                        : 'sk_...'
                    }
                    className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-slate-600 dark:text-zinc-400 mb-1">
                    Voice ID (Optional)
                  </label>
                  <input
                    type="text"
                    value={voiceId}
                    onChange={(e) => setVoiceId(e.target.value)}
                    placeholder="e.g. JBFqnCBsd6RMkjVDRZzb (George)"
                    className="w-full px-3 py-2 rounded-lg bg-white dark:bg-zinc-900 border border-slate-300 dark:border-zinc-700 focus:outline-none focus:border-cyan-500 text-slate-800 dark:text-zinc-200 font-mono text-xs"
                  />
                </div>
              </div>

            </div>

            {/* Drawer Footer Actions */}
            <div className="pt-4 border-t border-slate-200 dark:border-zinc-800 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 dark:text-zinc-400 hover:text-slate-900 dark:hover:text-zinc-200 transition-colors"
              >
                Close
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={handleSaveConfig}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 transition-all cursor-pointer shadow-[0_0_12px_rgba(0,229,255,0.25)]"
              >
                {saving ? (
                  <>
                    <Loader2 size={13} className="animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Key size={13} />
                    <span>Save & Hot-Reload</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
