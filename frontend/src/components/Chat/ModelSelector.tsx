import { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router';
import {
  ChevronDown,
  Sparkles,
  Check,
  ExternalLink,
  Cpu,
  Layers,
  AlertCircle,
  Plus,
  Loader2,
  KeyRound,
  Search,
  Sliders,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import {
  fetchModels,
  getCloudKeyStatus,
  saveCloudKey,
  type CloudKeyStatus,
} from '../../lib/api';
import { formatModelName } from '../../lib/model-pricing';

// Model metadata & badges
interface ModelMeta {
  badge?: string;
  recommended?: boolean;
  desc?: string;
}

const KNOWN_METAS: Record<string, ModelMeta> = {
  // Google Gemini
  'gemini-3.5-flash': { badge: 'Frontier', recommended: true, desc: 'Ultra-fast, state-of-the-art multimodal reasoning & tool use' },
  'gemini-3.8-flash': { badge: 'Frontier', desc: 'Next-gen flagship flash architecture' },
  'gemini-3.7-flash': { badge: 'Fast', desc: 'High-throughput reasoning and rapid task execution' },
  'gemini-3.6-flash': { badge: 'Speed', desc: 'Optimized high-speed agent execution' },
  'gemini-3-flash-preview': { badge: 'Preview', desc: 'Multimodal preview with advanced vision & tool integration' },
  'gemini-flash-latest': { badge: 'Latest', desc: 'Canonical latest production Flash model' },
  'gemini-flash-lite-latest': { badge: 'Ultra-Fast', desc: 'Minimal latency & lightweight token processing' },
  'gemini-3.1-pro-preview': { badge: 'Reasoning', desc: 'Deep complex architecture & multi-step coding' },
  'gemini-pro-latest': { badge: 'Pro', desc: 'Canonical latest production Pro model' },
  'gemini-1.5-flash': { badge: 'High Context', desc: 'Large 1M+ context window with stable output' },
  'gemini-1.5-pro': { badge: 'Complex', desc: 'Deep analytical context analysis' },
  'gemini-3.5-flash-lite': { badge: 'Ultra-Fast', desc: 'Minimal latency & lightweight token processing' },
  'gemini-3.1-flash-lite-preview': { badge: 'Fast', desc: 'Lightweight preview model for fast tool use' },
  'gemini-4-argon': { badge: 'Experimental', desc: 'Next-gen frontier reasoning prototype' },
  'antigravity-preview-latest': { badge: 'Specialized', desc: 'Autonomous system orchestration & execution' },
  'deep-research-preview-04-2026': { badge: 'Research', desc: 'Long-horizon iterative web search & report synthesis' },
  'deep-research-pro-preview-12-2025': { badge: 'Deep Reasoning', desc: 'Exhaustive verification and multi-step investigation' },
  'gemma-4-31b-it': { badge: 'Open Weights', desc: 'Instruction-tuned dense frontier architecture' },
  'gemma-4-26b-a4b-it': { badge: 'Open Weights', desc: 'Efficient quantized instruction-tuned model' },

  // Anthropic Claude
  'claude-3-7-sonnet': { badge: 'Frontier', recommended: true, desc: 'Hybrid reasoning and state-of-the-art agentic coding' },
  'claude-3-5-sonnet': { badge: 'Agentic', desc: 'Industry benchmark for code generation & tools' },
  'claude-3-5-haiku': { badge: 'Speed', desc: 'Rapid responses and high throughput execution' },
  'claude-3-opus': { badge: 'Reasoning', desc: 'Deep contextual analysis and philosophy' },

  // OpenAI
  'gpt-4o': { badge: 'Frontier', recommended: true, desc: 'Flagship multimodal model with high function reliability' },
  'gpt-4o-mini': { badge: 'Efficient', desc: 'Fast, cost-efficient model for general intelligence' },
  'o3-mini': { badge: 'Reasoning', desc: 'Specialized STEM, logic, and code reasoning' },
  'o1': { badge: 'Deep Thought', desc: 'Advanced deliberate reasoning model' },
};

function isGoogleModel(id: string, ownedBy?: string): boolean {
  const lower = id.toLowerCase();
  return (
    ownedBy === 'google' ||
    ownedBy === 'gemini' ||
    lower.startsWith('gemini') ||
    lower.startsWith('gemma') ||
    lower.startsWith('nano-banana') ||
    lower.startsWith('lyria') ||
    lower.startsWith('antigravity') ||
    lower.startsWith('deep-research')
  );
}

function isClaudeModel(id: string, ownedBy?: string): boolean {
  const lower = id.toLowerCase();
  return ownedBy === 'anthropic' || lower.startsWith('claude');
}

function isOpenAIModel(id: string, ownedBy?: string): boolean {
  const lower = id.toLowerCase();
  return (
    ownedBy === 'openai' ||
    lower.startsWith('gpt-') ||
    lower.startsWith('o1') ||
    lower.startsWith('o3') ||
    lower.startsWith('o4') ||
    lower.startsWith('chatgpt')
  );
}

function isLocalOllamaModel(id: string, ownedBy?: string): boolean {
  if (isGoogleModel(id, ownedBy)) return false;
  if (isClaudeModel(id, ownedBy)) return false;
  if (isOpenAIModel(id, ownedBy)) return false;
  if (id.startsWith('openrouter/') || id.startsWith('atlascloud/') || id.startsWith('MiniMax')) return false;
  return ownedBy === 'ollama' || ownedBy === 'local';
}

export function ModelSelector({ compact = false }: { compact?: boolean }) {
  const [isOpen, setIsOpen] = useState(false);
  const [keyStatus, setKeyStatus] = useState<CloudKeyStatus>({});
  const [activeKeyInput, setActiveKeyInput] = useState<string | null>(null);
  const [keyValue, setKeyValue] = useState('');
  const [savingKey, setSavingKey] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [customModelInput, setCustomModelInput] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');

  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const models = useAppStore((s) => s.models);
  const setModels = useAppStore((s) => s.setModels);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);

  const loadKeys = async () => {
    try {
      const status = await getCloudKeyStatus();
      setKeyStatus(status);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadKeys();
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setActiveKeyInput(null);
        setSaveError('');
        setShowCustomInput(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleSelectModel = (modelId: string) => {
    setSelectedModel(modelId);
    setIsOpen(false);
    setActiveKeyInput(null);
    setShowCustomInput(false);
  };

  const handleSaveKey = async (keyName: string) => {
    if (!keyValue.trim()) return;
    setSavingKey(true);
    setSaveError('');
    try {
      await saveCloudKey(keyName, keyValue.trim());
      setKeyValue('');
      setActiveKeyInput(null);
      await loadKeys();
      const refreshedModels = await fetchModels();
      setModels(refreshedModels);
    } catch (err: any) {
      setSaveError(err.message || 'Failed to save key');
    } finally {
      setSavingKey(false);
    }
  };

  const handleCustomModelSubmit = () => {
    const trimmed = customModelInput.trim();
    if (trimmed) {
      handleSelectModel(trimmed);
      setCustomModelInput('');
    }
  };

  // Group models with bulletproof provider discrimination
  const { googleModels, claudeModels, openaiModels, localModels } = useMemo(() => {
    const gList: string[] = [];
    const cList: string[] = [];
    const oList: string[] = [];
    const lList: string[] = [];

    // Fallback baseline lists if backend hasn't populated them yet
    const hasGoogleKey = Boolean(keyStatus['GEMINI_API_KEY'] || keyStatus['GOOGLE_API_KEY']);
    const hasClaudeKey = Boolean(keyStatus['ANTHROPIC_API_KEY']);
    const hasOpenAIKey = Boolean(keyStatus['OPENAI_API_KEY']);

    const defaultGoogle = [
      'gemini-3.5-flash',
      'gemini-3.8-flash',
      'gemini-3.7-flash',
      'gemini-3.6-flash',
      'gemini-3.5-flash-lite',
      'gemini-3-flash-preview',
      'gemini-3.1-pro-preview',
      'gemini-3.1-flash-lite-preview',
      'gemini-flash-latest',
      'gemini-flash-lite-latest',
      'gemini-pro-latest',
      'gemini-1.5-flash',
      'gemini-1.5-pro',
      'gemini-4-argon',
      'antigravity-preview-latest',
      'deep-research-preview-04-2026',
      'deep-research-pro-preview-12-2025',
      'gemma-4-31b-it',
      'gemma-4-26b-a4b-it',
    ];

    const defaultClaude = ['claude-3-7-sonnet', 'claude-3-5-sonnet', 'claude-3-5-haiku', 'claude-3-opus'];
    const defaultOpenAI = ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'o1', 'gpt-4-turbo'];

    for (const m of models) {
      if (isGoogleModel(m.id, m.owned_by)) {
        if (!gList.includes(m.id)) gList.push(m.id);
      } else if (isClaudeModel(m.id, m.owned_by)) {
        if (!cList.includes(m.id)) cList.push(m.id);
      } else if (isOpenAIModel(m.id, m.owned_by)) {
        if (!oList.includes(m.id)) oList.push(m.id);
      } else if (isLocalOllamaModel(m.id, m.owned_by)) {
        if (!lList.includes(m.id)) lList.push(m.id);
      }
    }

    if (hasGoogleKey) {
      for (const dg of defaultGoogle) {
        if (!gList.includes(dg)) gList.push(dg);
      }
    }
    if (hasClaudeKey) {
      for (const dc of defaultClaude) {
        if (!cList.includes(dc)) cList.push(dc);
      }
    }
    if (hasOpenAIKey) {
      for (const dop of defaultOpenAI) {
        if (!oList.includes(dop)) oList.push(dop);
      }
    }

    return {
      googleModels: gList,
      claudeModels: cList,
      openaiModels: oList,
      localModels: lList,
    };
  }, [models, keyStatus]);

  const activeDisplay = selectedModel ? formatModelName(selectedModel) : 'Select Model';
  const hasActiveModel = Boolean(selectedModel);

  const filterItem = (id: string) => {
    if (!searchFilter.trim()) return true;
    return id.toLowerCase().includes(searchFilter.trim().toLowerCase());
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => {
          setIsOpen(!isOpen);
          if (!isOpen) loadKeys();
        }}
        className={`
          flex items-center gap-2 rounded-lg transition-all cursor-pointer font-medium select-none
          ${compact ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-xs'}
        `}
        style={{
          background: hasActiveModel ? 'var(--color-bg-secondary)' : 'rgba(239, 68, 68, 0.08)',
          border: hasActiveModel ? '1px solid var(--color-border)' : '1px dashed rgba(239, 68, 68, 0.4)',
          color: hasActiveModel ? 'var(--color-text)' : 'var(--color-error)',
        }}
        title={hasActiveModel ? `Active Model: ${selectedModel}` : 'No model selected. Click to configure'}
      >
        <div className="flex items-center gap-1.5 shrink-0">
          {hasActiveModel ? (
            <Sparkles size={13} style={{ color: 'var(--color-accent)' }} />
          ) : (
            <AlertCircle size={13} className="text-red-400 animate-pulse" />
          )}
          <span className="truncate max-w-[170px] font-semibold">
            {activeDisplay}
          </span>
        </div>
        <ChevronDown
          size={13}
          className={`shrink-0 transition-transform duration-200 text-zinc-400 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          className="absolute left-0 mt-2 w-[370px] rounded-xl shadow-2xl z-50 overflow-hidden text-xs transition-all"
          style={{
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            boxShadow: '0 16px 40px -4px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.05)',
          }}
        >
          {/* Menu Header */}
          <div
            className="flex items-center justify-between px-3.5 py-2.5 border-b"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-secondary)' }}
          >
            <div className="flex items-center gap-2">
              <Layers size={14} style={{ color: 'var(--color-accent)' }} />
              <span className="font-semibold uppercase tracking-wider text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                Select Ultron Model
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCustomInput(!showCustomInput)}
                className="text-[10px] flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors cursor-pointer border"
                style={{
                  background: showCustomInput ? 'var(--color-accent-subtle)' : 'var(--color-bg-tertiary)',
                  borderColor: showCustomInput ? 'var(--color-accent)' : 'var(--color-border)',
                  color: showCustomInput ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                }}
                title="Enter any custom model ID"
              >
                <Sliders size={10} />
                <span>Custom</span>
              </button>
              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/settings');
                }}
                className="text-[10px] flex items-center gap-1 hover:underline cursor-pointer"
                style={{ color: 'var(--color-accent)' }}
              >
                <span>Keys</span>
                <ExternalLink size={10} />
              </button>
            </div>
          </div>

          {/* Quick Search & Custom Input */}
          <div
            className="p-2 space-y-1.5 border-b"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-tertiary)' }}
          >
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border"
              style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
            >
              <Search size={12} style={{ color: 'var(--color-text-tertiary)' }} />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Search models (e.g. 3.5, flash, claude)..."
                className="flex-1 bg-transparent text-xs outline-none"
                style={{ color: 'var(--color-text)', caretColor: 'var(--color-accent)' }}
              />
              {searchFilter && (
                <button
                  onClick={() => setSearchFilter('')}
                  className="text-xs cursor-pointer"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* Custom Model Input Option */}
            {showCustomInput && (
              <div
                className="p-2 rounded-lg border flex flex-col gap-1.5"
                style={{ background: 'var(--color-accent-subtle)', borderColor: 'var(--color-accent)' }}
              >
                <span className="text-[10.5px] font-medium" style={{ color: 'var(--color-accent)' }}>
                  Use Any Custom Model ID:
                </span>
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={customModelInput}
                    onChange={(e) => setCustomModelInput(e.target.value)}
                    placeholder="e.g. gemini-3.5-flash, gemini-4-argon..."
                    className="flex-1 px-2 py-1 text-xs rounded border outline-none"
                    style={{
                      background: 'var(--color-bg)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text)',
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCustomModelSubmit();
                      if (e.key === 'Escape') setShowCustomInput(false);
                    }}
                  />
                  <button
                    onClick={handleCustomModelSubmit}
                    disabled={!customModelInput.trim()}
                    className="px-2.5 py-1 text-xs rounded font-medium cursor-pointer disabled:opacity-50 text-white"
                    style={{ background: 'var(--color-accent)' }}
                  >
                    Select
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Scrollable Model Lists */}
          <div className="max-h-[420px] overflow-y-auto p-1" style={{ borderColor: 'var(--color-border)' }}>
            {/* 1. Google Gemini Section */}
            <div className="py-2 px-1 border-b" style={{ borderColor: 'var(--color-border)' }}>
              <div className="flex items-center justify-between px-2.5 py-1 mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>Google Gemini</span>
                  {Boolean(keyStatus['GEMINI_API_KEY'] || keyStatus['GOOGLE_API_KEY']) ? (
                    <span className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono flex items-center gap-1 bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
                      <span className="w-1 h-1 rounded-full bg-emerald-500"></span>
                      {googleModels.length} Models
                    </span>
                  ) : (
                    <span
                      className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono border"
                      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)' }}
                    >
                      Key Required
                    </span>
                  )}
                </div>

                {!Boolean(keyStatus['GEMINI_API_KEY'] || keyStatus['GOOGLE_API_KEY']) &&
                  activeKeyInput !== 'GEMINI_API_KEY' && (
                    <button
                      onClick={() => {
                        setActiveKeyInput('GEMINI_API_KEY');
                        setKeyValue('');
                        setSaveError('');
                      }}
                      className="text-[10px] font-semibold flex items-center gap-1 px-2 py-0.5 rounded transition-colors cursor-pointer border"
                      style={{
                        background: 'var(--color-accent-subtle)',
                        borderColor: 'var(--color-accent)',
                        color: 'var(--color-accent)',
                      }}
                    >
                      <Plus size={10} />
                      Add Key
                    </button>
                  )}
              </div>

              {/* Inline Key Entry */}
              {activeKeyInput === 'GEMINI_API_KEY' && (
                <div
                  className="mx-2 mb-2 p-2 rounded-lg border flex flex-col gap-1.5"
                  style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
                >
                  <div className="text-[10.5px]" style={{ color: 'var(--color-text-secondary)' }}>Paste Google Gemini API Key:</div>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="password"
                      value={keyValue}
                      onChange={(e) => setKeyValue(e.target.value)}
                      placeholder="AIzaSy... or AQ..."
                      className="flex-1 px-2 py-1 text-xs rounded border outline-none"
                      style={{
                        background: 'var(--color-bg-secondary)',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text)',
                      }}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSaveKey('GEMINI_API_KEY');
                        if (e.key === 'Escape') setActiveKeyInput(null);
                      }}
                    />
                    <button
                      onClick={() => handleSaveKey('GEMINI_API_KEY')}
                      disabled={savingKey || !keyValue.trim()}
                      className="px-2.5 py-1 text-xs rounded font-semibold cursor-pointer disabled:opacity-50 text-white"
                      style={{ background: 'var(--color-accent)' }}
                    >
                      {savingKey ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
                    </button>
                    <button
                      onClick={() => setActiveKeyInput(null)}
                      className="px-2 py-1 text-xs rounded cursor-pointer border"
                      style={{
                        color: 'var(--color-text-secondary)',
                        borderColor: 'var(--color-border)',
                        background: 'var(--color-bg-secondary)',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                  {saveError && <div className="text-[10px] text-red-500">{saveError}</div>}
                </div>
              )}

              {/* Gemini Models List */}
              {Boolean(keyStatus['GEMINI_API_KEY'] || keyStatus['GOOGLE_API_KEY']) ? (
                <div className="space-y-0.5">
                  {googleModels.filter(filterItem).map((mId) => {
                    const isSelected = selectedModel === mId;
                    const meta = KNOWN_METAS[mId] || {};
                    return (
                      <button
                        key={mId}
                        onClick={() => handleSelectModel(mId)}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg transition-all flex items-start justify-between cursor-pointer group border"
                        style={{
                          background: isSelected ? 'var(--color-accent-subtle)' : 'transparent',
                          borderColor: isSelected ? 'var(--color-accent)' : 'transparent',
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-secondary)';
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                        }}
                      >
                        <div className="flex-1 min-w-0 pr-2">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className="font-semibold text-xs truncate"
                              style={{ color: isSelected ? 'var(--color-accent)' : 'var(--color-text)' }}
                            >
                              {formatModelName(mId)}
                            </span>
                            {meta.badge && (
                              <span
                                className="text-[9px] px-1.5 py-0.5 rounded font-mono border"
                                style={{
                                  background: 'var(--color-bg-tertiary)',
                                  color: 'var(--color-text-secondary)',
                                  borderColor: 'var(--color-border)',
                                }}
                              >
                                {meta.badge}
                              </span>
                            )}
                            {meta.recommended && (
                              <span className="text-[8.5px] px-1 py-0.5 rounded font-mono bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
                                Recommended
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] leading-tight mt-0.5 font-mono truncate" style={{ color: 'var(--color-text-tertiary)' }}>
                            {meta.desc || mId}
                          </p>
                        </div>
                        {isSelected && <Check size={14} style={{ color: 'var(--color-accent)' }} className="shrink-0 mt-0.5" />}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="px-2.5 py-1.5 text-[11px] italic" style={{ color: 'var(--color-text-tertiary)' }}>
                  Add your Gemini API key to unlock Gemini 3.5 Flash and all frontier models.
                </div>
              )}
            </div>

            {/* 2. Anthropic Claude Section */}
            <div className="py-2 px-1 border-b" style={{ borderColor: 'var(--color-border)' }}>
              <div className="flex items-center justify-between px-2.5 py-1 mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>Anthropic Claude</span>
                  {Boolean(keyStatus['ANTHROPIC_API_KEY']) ? (
                    <span className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono flex items-center gap-1 bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
                      <span className="w-1 h-1 rounded-full bg-emerald-500"></span>
                      {claudeModels.length} Models
                    </span>
                  ) : (
                    <span
                      className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono border"
                      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)' }}
                    >
                      Key Required
                    </span>
                  )}
                </div>

                {!Boolean(keyStatus['ANTHROPIC_API_KEY']) && activeKeyInput !== 'ANTHROPIC_API_KEY' && (
                  <button
                    onClick={() => {
                      setActiveKeyInput('ANTHROPIC_API_KEY');
                      setKeyValue('');
                      setSaveError('');
                    }}
                    className="text-[10px] font-semibold flex items-center gap-1 px-2 py-0.5 rounded transition-colors cursor-pointer border"
                    style={{
                      background: 'var(--color-accent-amber-subtle)',
                      borderColor: 'var(--color-accent-amber)',
                      color: 'var(--color-accent-amber)',
                    }}
                  >
                    <Plus size={10} />
                    Add Key
                  </button>
                )}
              </div>

              {activeKeyInput === 'ANTHROPIC_API_KEY' && (
                <div
                  className="mx-2 mb-2 p-2 rounded-lg border flex flex-col gap-1.5"
                  style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
                >
                  <div className="text-[10.5px]" style={{ color: 'var(--color-text-secondary)' }}>Paste Anthropic API Key:</div>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="password"
                      value={keyValue}
                      onChange={(e) => setKeyValue(e.target.value)}
                      placeholder="sk-ant-..."
                      className="flex-1 px-2 py-1 text-xs rounded border outline-none"
                      style={{
                        background: 'var(--color-bg-secondary)',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text)',
                      }}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSaveKey('ANTHROPIC_API_KEY');
                        if (e.key === 'Escape') setActiveKeyInput(null);
                      }}
                    />
                    <button
                      onClick={() => handleSaveKey('ANTHROPIC_API_KEY')}
                      disabled={savingKey || !keyValue.trim()}
                      className="px-2.5 py-1 text-xs rounded font-semibold cursor-pointer disabled:opacity-50 text-white"
                      style={{ background: 'var(--color-accent-amber)' }}
                    >
                      {savingKey ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
                    </button>
                    <button
                      onClick={() => setActiveKeyInput(null)}
                      className="px-2 py-1 text-xs rounded cursor-pointer border"
                      style={{
                        color: 'var(--color-text-secondary)',
                        borderColor: 'var(--color-border)',
                        background: 'var(--color-bg-secondary)',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                  {saveError && <div className="text-[10px] text-red-500">{saveError}</div>}
                </div>
              )}

              {Boolean(keyStatus['ANTHROPIC_API_KEY']) && (
                <div className="space-y-0.5">
                  {claudeModels.filter(filterItem).map((mId) => {
                    const isSelected = selectedModel === mId;
                    const meta = KNOWN_METAS[mId] || {};
                    return (
                      <button
                        key={mId}
                        onClick={() => handleSelectModel(mId)}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg transition-all flex items-start justify-between cursor-pointer group border"
                        style={{
                          background: isSelected ? 'var(--color-accent-amber-subtle)' : 'transparent',
                          borderColor: isSelected ? 'var(--color-accent-amber)' : 'transparent',
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-secondary)';
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                        }}
                      >
                        <div className="flex-1 min-w-0 pr-2">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="font-semibold text-xs truncate"
                              style={{ color: isSelected ? 'var(--color-accent-amber)' : 'var(--color-text)' }}
                            >
                              {formatModelName(mId)}
                            </span>
                            {meta.badge && (
                              <span
                                className="text-[9px] px-1.5 py-0.5 rounded font-mono border"
                                style={{
                                  background: 'var(--color-bg-tertiary)',
                                  color: 'var(--color-text-secondary)',
                                  borderColor: 'var(--color-border)',
                                }}
                              >
                                {meta.badge}
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] leading-tight mt-0.5 font-mono truncate" style={{ color: 'var(--color-text-tertiary)' }}>
                            {meta.desc || mId}
                          </p>
                        </div>
                        {isSelected && <Check size={14} style={{ color: 'var(--color-accent-amber)' }} className="shrink-0 mt-0.5" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 3. OpenAI Section */}
            <div className="py-2 px-1 border-b" style={{ borderColor: 'var(--color-border)' }}>
              <div className="flex items-center justify-between px-2.5 py-1 mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>OpenAI</span>
                  {Boolean(keyStatus['OPENAI_API_KEY']) ? (
                    <span className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono flex items-center gap-1 bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
                      <span className="w-1 h-1 rounded-full bg-emerald-500"></span>
                      {openaiModels.length} Models
                    </span>
                  ) : (
                    <span
                      className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono border"
                      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)' }}
                    >
                      Key Required
                    </span>
                  )}
                </div>

                {!Boolean(keyStatus['OPENAI_API_KEY']) && activeKeyInput !== 'OPENAI_API_KEY' && (
                  <button
                    onClick={() => {
                      setActiveKeyInput('OPENAI_API_KEY');
                      setKeyValue('');
                      setSaveError('');
                    }}
                    className="text-[10px] font-semibold flex items-center gap-1 px-2 py-0.5 rounded transition-colors cursor-pointer border"
                    style={{
                      background: 'rgba(16,185,129,0.1)',
                      borderColor: 'rgb(16,185,129)',
                      color: 'rgb(16,185,129)',
                    }}
                  >
                    <Plus size={10} />
                    Add Key
                  </button>
                )}
              </div>

              {activeKeyInput === 'OPENAI_API_KEY' && (
                <div
                  className="mx-2 mb-2 p-2 rounded-lg border flex flex-col gap-1.5"
                  style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
                >
                  <div className="text-[10.5px]" style={{ color: 'var(--color-text-secondary)' }}>Paste OpenAI API Key:</div>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="password"
                      value={keyValue}
                      onChange={(e) => setKeyValue(e.target.value)}
                      placeholder="sk-..."
                      className="flex-1 px-2 py-1 text-xs rounded border outline-none"
                      style={{
                        background: 'var(--color-bg-secondary)',
                        borderColor: 'var(--color-border)',
                        color: 'var(--color-text)',
                      }}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSaveKey('OPENAI_API_KEY');
                        if (e.key === 'Escape') setActiveKeyInput(null);
                      }}
                    />
                    <button
                      onClick={() => handleSaveKey('OPENAI_API_KEY')}
                      disabled={savingKey || !keyValue.trim()}
                      className="px-2.5 py-1 text-xs rounded font-semibold cursor-pointer disabled:opacity-50 text-white"
                      style={{ background: 'rgb(16,185,129)' }}
                    >
                      {savingKey ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
                    </button>
                    <button
                      onClick={() => setActiveKeyInput(null)}
                      className="px-2 py-1 text-xs rounded cursor-pointer border"
                      style={{
                        color: 'var(--color-text-secondary)',
                        borderColor: 'var(--color-border)',
                        background: 'var(--color-bg-secondary)',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                  {saveError && <div className="text-[10px] text-red-500">{saveError}</div>}
                </div>
              )}

              {Boolean(keyStatus['OPENAI_API_KEY']) && (
                <div className="space-y-0.5">
                  {openaiModels.filter(filterItem).map((mId) => {
                    const isSelected = selectedModel === mId;
                    const meta = KNOWN_METAS[mId] || {};
                    return (
                      <button
                        key={mId}
                        onClick={() => handleSelectModel(mId)}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg transition-all flex items-start justify-between cursor-pointer group border"
                        style={{
                          background: isSelected ? 'rgba(16,185,129,0.1)' : 'transparent',
                          borderColor: isSelected ? 'rgb(16,185,129)' : 'transparent',
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-secondary)';
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                        }}
                      >
                        <div className="flex-1 min-w-0 pr-2">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="font-semibold text-xs truncate"
                              style={{ color: isSelected ? 'rgb(16,185,129)' : 'var(--color-text)' }}
                            >
                              {formatModelName(mId)}
                            </span>
                            {meta.badge && (
                              <span
                                className="text-[9px] px-1.5 py-0.5 rounded font-mono border"
                                style={{
                                  background: 'var(--color-bg-tertiary)',
                                  color: 'var(--color-text-secondary)',
                                  borderColor: 'var(--color-border)',
                                }}
                              >
                                {meta.badge}
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] leading-tight mt-0.5 font-mono truncate" style={{ color: 'var(--color-text-tertiary)' }}>
                            {meta.desc || mId}
                          </p>
                        </div>
                        {isSelected && <Check size={14} style={{ color: 'rgb(16,185,129)' }} className="shrink-0 mt-0.5" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 4. Local Models (Ollama) Section */}
            <div className="py-2 px-1">
              <div className="flex items-center justify-between px-2.5 py-1 mb-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>Local Models (Ollama)</span>
                  {localModels.length > 0 ? (
                    <span className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono bg-indigo-500/15 text-indigo-500 border border-indigo-500/30">
                      {localModels.length} Installed
                    </span>
                  ) : (
                    <span
                      className="text-[9.5px] px-1.5 py-0.5 rounded-full font-mono border"
                      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)' }}
                    >
                      None
                    </span>
                  )}
                </div>
              </div>

              {localModels.length > 0 ? (
                <div className="space-y-0.5">
                  {localModels.filter(filterItem).map((mId) => {
                    const isSelected = selectedModel === mId;
                    return (
                      <button
                        key={mId}
                        onClick={() => handleSelectModel(mId)}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg transition-all flex items-center justify-between cursor-pointer group border"
                        style={{
                          background: isSelected ? 'rgba(99,102,241,0.1)' : 'transparent',
                          borderColor: isSelected ? 'rgb(99,102,241)' : 'transparent',
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-secondary)';
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                        }}
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          <Cpu size={12} style={{ color: 'rgb(99,102,241)', flexShrink: 0 }} />
                          <span
                            className="font-semibold text-xs truncate"
                            style={{ color: isSelected ? 'rgb(99,102,241)' : 'var(--color-text)' }}
                          >
                            {mId}
                          </span>
                        </div>
                        {isSelected && <Check size={14} style={{ color: 'rgb(99,102,241)' }} className="shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="px-2.5 py-1.5 text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  No local models found in Ollama. Run <code style={{ color: 'var(--color-text-secondary)' }}>ollama run llama3.3</code> on localhost:11434 to run on-device models.
                </div>
              )}
            </div>
          </div>

          {/* Menu Footer */}
          <div
            className="px-3.5 py-2 border-t flex items-center justify-between text-[11px]"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-secondary)' }}
          >
            <span className="truncate max-w-[200px]" style={{ color: 'var(--color-text-secondary)' }}>Active: {activeDisplay}</span>
            <button
              onClick={() => {
                setIsOpen(false);
                navigate('/settings');
              }}
              className="flex items-center gap-1 cursor-pointer transition-colors"
              style={{ color: 'var(--color-text-secondary)' }}
              onMouseEnter={(e) => (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text)'}
              onMouseLeave={(e) => (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-secondary)'}
            >
              <KeyRound size={11} />
              <span>Settings</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
