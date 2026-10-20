import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Palette,
  Globe,
  Cpu,
  Database,
  Info,
  Check,
  Sun,
  Moon,
  Monitor,
  Download,
  Upload,
  Trash2,
  Mic,
  Key,
  Search,
  Brain,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Plus,
  Volume2,
  VolumeX,
  Sparkles,
  Languages,
} from 'lucide-react';
import { useAppStore, type ThemeMode } from '../lib/store';
import {
  checkHealth,
  fetchSpeechHealth,
  fetchTtsHealth,
  fetchPersonalization,
  updatePersonalization,
  getMemoryStats,
  getInferenceSource,
  setInferenceSource,
  getCloudKeyStatus,
  saveCloudKey,
  fetchToolCredentialStatus,
  saveToolCredentials,
  deleteToolCredential,
  fetchMCPServers,
  testMCPServer,
  validateMCPServer,
  saveMCPServer,
  deleteMCPServer,
  isTauri,
  fetchVoiceSettings,
  updateVoiceSettings,
  testElevenLabsConnection,
  fetchElevenLabsVoices,
  fetchElevenLabsModels,
  previewElevenLabsVoice,
  type InferenceSource,
  type MemoryStats,
  type MCPServerInfo,
  type MCPTestResult,
  type VoiceSettings,
  type VoiceSettingsUpdate,
  type ElevenLabsVoice,
  type ElevenLabsModel,
} from '../lib/api';
import { LocalModelWizard } from '../components/Settings/LocalModelWizard';
import { RuntimeLimitsSection } from '../components/Settings/RuntimeLimitsSection';
import { isAutoUpdateDisabled, setAutoUpdateDisabled } from '../components/Desktop/UpdateChecker';
import { UltronParticleCore } from '../components/Avatar/UltronParticleCore';
import { soundEffects } from '../lib/sound-effects';
import { PERSONA_PRESETS } from '../components/Onboarding/CinematicOnboarding';

const CLOUD_KEY_STATUS_CHANGED = 'openjarvis-cloud-key-status-changed';

function OllamaModelList() {
  const [models, setModels] = useState<Array<{ name: string; size: number }>>([]);
  useEffect(() => {
    fetch('http://localhost:11434/api/tags')
      .then(r => r.json())
      .then(data => setModels((data.models || []).map((m: any) => ({ name: m.name, size: m.size }))))
      .catch(() => setModels([]));
  }, []);
  if (models.length === 0) return <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>No models loaded</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {models.map(m => (
        <span key={m.name} className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px]"
          style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-success)', display: 'inline-block' }} />
          {m.name} ({(m.size / 1e9).toFixed(1)} GB)
        </span>
      ))}
    </div>
  );
}

function ApiKeyInput({
  keyName,
  placeholder,
  toolName,
}: {
  keyName: string;
  placeholder: string;
  toolName?: string;
}) {
  const [value, setValue] = useState('');
  const [saved, setSaved] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [error, setError] = useState('');
  const canManage = true;

  const refresh = useCallback(async () => {
    try {
      const status = toolName
        ? await fetchToolCredentialStatus(toolName)
        : await getCloudKeyStatus();
      setHasKey(!!status[keyName]);
    } catch {
      setHasKey(false);
    }
  }, [keyName, toolName]);

  useEffect(() => {
    void refresh();
    window.addEventListener(CLOUD_KEY_STATUS_CHANGED, refresh);
    return () => window.removeEventListener(CLOUD_KEY_STATUS_CHANGED, refresh);
  }, [refresh]);

  const save = async (v: string) => {
    const next = v.trim();
    if (!next) return;
    setError('');
    try {
      if (toolName) {
        await saveToolCredentials(toolName, { [keyName]: next });
      } else {
        await saveCloudKey(keyName, next);
      }
      setValue('');
      setHasKey(true);
      setSaved(true);
      window.dispatchEvent(new Event(CLOUD_KEY_STATUS_CHANGED));
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e?.message || 'Failed to save API key');
    }
  };

  const remove = async () => {
    setError('');
    try {
      if (toolName) {
        await deleteToolCredential(toolName, keyName);
      } else {
        await saveCloudKey(keyName, '');
      }
      setValue('');
      setHasKey(false);
      setSaved(true);
      window.dispatchEvent(new Event(CLOUD_KEY_STATUS_CHANGED));
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e?.message || 'Failed to remove API key');
    }
  };

  return (
    <div className="flex items-center gap-2">
      <input
        type="password"
        value={value}
        onChange={e => setValue(e.target.value)}
        onBlur={() => { if (value.trim()) void save(value); }}
        placeholder={hasKey ? 'Configured' : placeholder}
        disabled={false}
        className="w-48 px-2 py-1 rounded text-xs"
        style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }} />
      {hasKey && (
        <button
          onClick={() => void remove()}
          className="px-2 py-1 rounded text-[10px] cursor-pointer"
          style={{ color: 'var(--color-error)', border: '1px solid var(--color-error)' }}
        >
          Remove
        </button>
      )}
      {saved && <span className="text-[10px]" style={{ color: 'var(--color-success)' }}>Saved</span>}
      {error && <span className="text-[10px]" style={{ color: 'var(--color-error)' }}>{error}</span>}
    </div>
  );
}

function CloudProviderStatus({ label, keyName }: { label: string; keyName: string }) {
  const [hasKey, setHasKey] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const status = await getCloudKeyStatus();
      setHasKey(!!status[keyName]);
    } catch {
      setHasKey(false);
    }
  }, [keyName]);

  useEffect(() => {
    void refresh();
    window.addEventListener(CLOUD_KEY_STATUS_CHANGED, refresh);
    return () => window.removeEventListener(CLOUD_KEY_STATUS_CHANGED, refresh);
  }, [refresh]);

  return (
    <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
        background: hasKey ? 'var(--color-success)' : 'var(--color-text-tertiary)',
      }} />
      {label}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl p-5"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
    >
      <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text)' }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function SettingRow({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div className="min-w-0">
        <div className="text-sm" style={{ color: 'var(--color-text)' }}>{label}</div>
        {description && (
          <div className="text-xs mt-0.5 break-words" style={{ color: 'var(--color-text-tertiary)' }}>{description}</div>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

type MemoryStatus =
  | { kind: 'loading' }
  | { kind: 'ready'; stats: MemoryStats }
  | { kind: 'error'; message: string };

export function MemoryStatusRow({
  status,
  onRetry,
}: {
  status: MemoryStatus;
  onRetry: () => void;
}) {
  const stats = status.kind === 'ready' ? status.stats : null;
  const description = status.kind === 'error'
    ? status.message
    : status.kind === 'loading'
      ? 'Checking memory backend...'
      : stats?.backend === 'none'
        ? 'Memory is not configured'
        : `${stats?.backend} backend — ${stats?.entries} entries`;
  const label = status.kind === 'loading'
    ? 'Checking...'
    : stats?.backend === 'none'
      ? 'Not configured'
      : stats
        ? `${stats.entries} entries`
        : 'Unavailable';

  return (
    <SettingRow label="Memory status" description={description}>
      <div className="flex items-center gap-2">
        <Brain size={14} style={{ color: stats && stats.backend !== 'none' ? 'var(--color-accent)' : 'var(--color-text-tertiary)' }} />
        <span className="text-xs whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
          {label}
        </span>
        {status.kind === 'error' && (
          <button
            type="button"
            onClick={onRetry}
            className="text-xs underline cursor-pointer whitespace-nowrap"
            style={{ color: 'var(--color-accent)' }}
          >
            Retry
          </button>
        )}
      </div>
    </SettingRow>
  );
}

const themeOptions: { value: ThemeMode; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

function MCPServersSection() {
  const [servers, setServers] = useState<MCPServerInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [testResults, setTestResults] = useState<Record<string, MCPTestResult>>({});
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState('');
  const [newTransport, setNewTransport] = useState<'http' | 'stdio'>('http');
  const [newUrl, setNewUrl] = useState('');
  const [newToken, setNewToken] = useState('');
  const [newCommand, setNewCommand] = useState('');
  const [newArgs, setNewArgs] = useState('');
  const [formErrors, setFormErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const loadServers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchMCPServers();
      setServers(data);
    } catch {
      setServers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadServers();
  }, [loadServers]);

  const handleTest = async (server: MCPServerInfo) => {
    setTesting((prev) => ({ ...prev, [server.name]: true }));
    try {
      const res = await testMCPServer(server);
      setTestResults((prev) => ({ ...prev, [server.name]: res }));
    } catch (err: any) {
      setTestResults((prev) => ({
        ...prev,
        [server.name]: {
          name: server.name,
          connected: false,
          discovered_tools_count: 0,
          tools: [],
          error: err?.message || 'Connection failed',
        },
      }));
    } finally {
      setTesting((prev) => ({ ...prev, [server.name]: false }));
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await deleteMCPServer(name);
      await loadServers();
    } catch {}
  };

  const handleAddServer = async () => {
    setFormErrors([]);
    const payload: Partial<MCPServerInfo> = {
      name: newName.trim(),
      transport: newTransport,
      enabled: true,
    };
    if (newTransport === 'http') {
      payload.url = newUrl.trim();
      if (newToken.trim()) payload.token = newToken.trim();
    } else {
      payload.command = newCommand.trim();
      payload.args = newArgs.trim() ? newArgs.trim().split(/\s+/) : [];
    }

    try {
      setSaving(true);
      const val = await validateMCPServer(payload);
      if (!val.valid) {
        setFormErrors(val.errors);
        return;
      }
      await saveMCPServer(payload);
      setNewName('');
      setNewUrl('');
      setNewToken('');
      setNewCommand('');
      setNewArgs('');
      setShowAdd(false);
      await loadServers();
    } catch (err: any) {
      setFormErrors([err?.message || 'Failed to save server']);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Section title="MCP Servers (Model Context Protocol)">
      <div className="text-xs mb-3" style={{ color: 'var(--color-text-tertiary)' }}>
        Connect local or remote MCP servers to expand Ultron's tools and context.
      </div>
      {loading ? (
        <div className="text-xs py-2" style={{ color: 'var(--color-text-tertiary)' }}>Loading MCP servers...</div>
      ) : servers.length === 0 ? (
        <div className="text-xs py-2" style={{ color: 'var(--color-text-tertiary)' }}>No MCP servers configured yet.</div>
      ) : (
        <div className="space-y-3 mb-4">
          {servers.map((s) => {
            const tr = testResults[s.name];
            const isTesting = testing[s.name];
            return (
              <div
                key={s.name}
                className="p-3 rounded-lg flex flex-col gap-2"
                style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>{s.name}</span>
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase"
                      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)' }}
                    >
                      {s.transport}
                    </span>
                    {tr && (
                      <span
                        className="flex items-center gap-1 text-[11px] font-medium"
                        style={{ color: tr.connected ? 'var(--color-success)' : 'var(--color-error)' }}
                      >
                        {tr.connected ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                        {tr.connected ? `Connected (${tr.latency_ms ?? 0}ms - ${tr.discovered_tools_count} tools)` : 'Unreachable'}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleTest(s)}
                      disabled={isTesting}
                      className="px-2 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer"
                      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                    >
                      {isTesting ? 'Testing...' : 'Test Connection'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(s.name)}
                      className="p-1 rounded text-xs transition-colors cursor-pointer"
                      style={{ color: 'var(--color-text-tertiary)' }}
                      title="Remove server"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
                <div className="text-[11px] font-mono break-all" style={{ color: 'var(--color-text-tertiary)' }}>
                  {s.url ? s.url : `${s.command || ''} ${(s.args || []).join(' ')}`}
                </div>
                {tr && !tr.connected && tr.error && (
                  <div className="text-[11px] mt-1 p-1.5 rounded" style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--color-error)' }}>
                    {tr.error}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showAdd ? (
        <div className="p-3.5 rounded-lg space-y-3" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}>
          <div className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>Add New MCP Server</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>Server Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. github-mcp"
                className="w-full text-xs px-2.5 py-1.5 rounded"
                style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
              />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>Transport</label>
              <select
                value={newTransport}
                onChange={(e) => setNewTransport(e.target.value as 'http' | 'stdio')}
                className="w-full text-xs px-2.5 py-1.5 rounded"
                style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
              >
                <option value="http">HTTP / SSE</option>
                <option value="stdio">Local Stdio (Subprocess)</option>
              </select>
            </div>
          </div>

          {newTransport === 'http' ? (
            <div className="space-y-2">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>Server URL</label>
                <input
                  type="text"
                  value={newUrl}
                  onChange={(e) => setNewUrl(e.target.value)}
                  placeholder="https://api.example.com/mcp"
                  className="w-full text-xs px-2.5 py-1.5 rounded"
                  style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>Bearer Token (Optional)</label>
                <input
                  type="password"
                  value={newToken}
                  onChange={(e) => setNewToken(e.target.value)}
                  placeholder="sk-..."
                  className="w-full text-xs px-2.5 py-1.5 rounded"
                  style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>Executable Command</label>
                <input
                  type="text"
                  value={newCommand}
                  onChange={(e) => setNewCommand(e.target.value)}
                  placeholder="e.g. python or npx"
                  className="w-full text-xs px-2.5 py-1.5 rounded"
                  style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--color-text-secondary)' }}>Arguments (Space-separated)</label>
                <input
                  type="text"
                  value={newArgs}
                  onChange={(e) => setNewArgs(e.target.value)}
                  placeholder="-m mcp_server_filesystem"
                  className="w-full text-xs px-2.5 py-1.5 rounded"
                  style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
                />
              </div>
            </div>
          )}

          {formErrors.length > 0 && (
            <div className="p-2 rounded text-xs space-y-0.5" style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--color-error)' }}>
              {formErrors.map((err, idx) => (
                <div key={idx}>• {err}</div>
              ))}
            </div>
          )}

          <div className="flex items-center gap-2 justify-end">
            <button
              type="button"
              onClick={() => { setShowAdd(false); setFormErrors([]); }}
              className="px-3 py-1.5 rounded text-xs transition-colors cursor-pointer"
              style={{ background: 'transparent', color: 'var(--color-text-secondary)' }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleAddServer}
              disabled={saving}
              className="px-3.5 py-1.5 rounded text-xs font-medium transition-colors cursor-pointer"
              style={{ background: 'var(--color-accent)', color: 'white' }}
            >
              {saving ? 'Validating...' : 'Validate & Save'}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
          style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
        >
          <Plus size={13} /> Add MCP Server
        </button>
      )}
    </Section>
  );
}

export function SettingsPage() {
  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const conversations = useAppStore((s) => s.conversations);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [speechBackendAvailable, setSpeechBackendAvailable] = useState<boolean | null>(null);
  const [ttsBackend, setTtsBackend] = useState<{ available: boolean; backend?: string; voice_id?: string } | null>(null);
  const [saved, setSaved] = useState(false);

  // Voice settings & ElevenLabs state
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings | null>(null);
  const [elevenLabsApiKeyInput, setElevenLabsApiKeyInput] = useState('');
  const [elevenLabsVoices, setElevenLabsVoices] = useState<ElevenLabsVoice[]>([]);
  const [elevenLabsModels, setElevenLabsModels] = useState<ElevenLabsModel[]>([]);
  const [connTestState, setConnTestState] = useState<{
    status: 'idle' | 'testing' | 'connected' | 'invalid_key' | 'quota_limited' | 'timeout' | 'error' | 'unconfigured';
    message: string;
  }>({ status: 'idle', message: '' });
  const [previewState, setPreviewState] = useState<'idle' | 'loading' | 'playing'>('idle');
  const [previewText, setPreviewText] = useState('Hello, I am Ultron. Speech synthesis is operational.');
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  // Personalization & Cyber Experience state
  const [userNameInput, setUserNameInput] = useState(settings.userName || 'Sir');
  const [userNameSaved, setUserNameSaved] = useState(false);

  useEffect(() => {
    fetchPersonalization()
      .then((data) => {
        if (data.user_name) setUserNameInput(data.user_name);
        updateSettings({
          userName: data.user_name || settings.userName,
          voicePresentation: data.presentation || settings.voicePresentation,
          persona: data.persona || settings.persona,
          language: data.language || settings.language,
          soundEnabled: data.sound_enabled ?? settings.soundEnabled,
          soundVolume: data.sound_volume ?? settings.soundVolume,
        });
      })
      .catch(() => {});
  }, []);

  const handleSaveUserName = async () => {
    const clean = userNameInput.trim() || 'Sir';
    setUserNameInput(clean);
    updateSettings({ userName: clean });
    try {
      await updatePersonalization({ user_name: clean });
    } catch {}
    setUserNameSaved(true);
    showSaved();
    setTimeout(() => setUserNameSaved(false), 2500);
    soundEffects.playSuccessChime();
  };

  const handlePresentationChange = async (p: 'masculine' | 'feminine' | 'neutral') => {
    updateSettings({ voicePresentation: p, voiceGender: p });
    showSaved();
    soundEffects.playClick();
    try {
      await updatePersonalization({
        presentation: 'neutral',
        voice_presentation: p,
        voice_gender: p,
      });
    } catch {}
  };

  const handlePersonaChange = async (pId: string) => {
    updateSettings({ persona: pId });
    showSaved();
    soundEffects.playClick();
    try {
      await updatePersonalization({ persona: pId });
    } catch {}
  };

  const handleLanguageChange = async (l: 'en' | 'ur' | 'hi' | 'auto') => {
    updateSettings({ language: l });
    showSaved();
    soundEffects.playClick();
    try {
      await updatePersonalization({ language: l });
    } catch {}
  };

  const handleSoundToggle = (enabled: boolean) => {
    updateSettings({ soundEnabled: enabled });
    soundEffects.setEnabled(enabled);
    showSaved();
    if (enabled) soundEffects.playClick();
  };

  const handleSoundVolumeChange = (vol: number) => {
    updateSettings({ soundVolume: vol });
    soundEffects.setVolume(vol);
    showSaved();
  };

  const handleRelaunchOnboarding = () => {
    soundEffects.playClick();
    window.dispatchEvent(new CustomEvent('ultron-relaunch-onboarding'));
  };

  const [autoUpdateEnabled, setAutoUpdateEnabled] = useState(() => !isAutoUpdateDisabled());
  const [updateCheckState, setUpdateCheckState] = useState<'idle' | 'checking' | 'available' | 'latest'>('idle');

  const handleAutoUpdateToggle = useCallback((enabled: boolean) => {
    setAutoUpdateEnabled(enabled);
    setAutoUpdateDisabled(!enabled);
  }, []);

  const handleCheckNow = useCallback(async () => {
    if (!(window as any).__TAURI_INTERNALS__) return;
    setUpdateCheckState('checking');
    try {
      const { check } = await import('@tauri-apps/plugin-updater');
      const update = await check();
      setUpdateCheckState(update ? 'available' : 'latest');
      setTimeout(() => setUpdateCheckState('idle'), 4000);
    } catch {
      setUpdateCheckState('idle');
    }
  }, []);

  const [memoryStatus, setMemoryStatus] = useState<MemoryStatus>({ kind: 'loading' });
  const memoryRequestId = useRef(0);
  const [memoryEnabled, setMemoryEnabled] = useState(() => {
    try { return localStorage.getItem('openjarvis-memory-enabled') !== 'false'; } catch { return true; }
  });
  const [memoryBackend, setMemoryBackend] = useState(() => {
    try { return localStorage.getItem('openjarvis-memory-backend') || 'sqlite'; } catch { return 'sqlite'; }
  });
  const [memoryTopK, setMemoryTopK] = useState(() => {
    try { return parseInt(localStorage.getItem('openjarvis-memory-top-k') || '5'); } catch { return 5; }
  });
  const [memoryMinScore, setMemoryMinScore] = useState(() => {
    try { return parseFloat(localStorage.getItem('openjarvis-memory-min-score') || '0.1'); } catch { return 0.1; }
  });
  const [memoryMaxTokens, setMemoryMaxTokens] = useState(() => {
    try { return parseInt(localStorage.getItem('openjarvis-memory-max-tokens') || '2048'); } catch { return 2048; }
  });

  const [srcKind, setSrcKind] = useState<InferenceSource['kind']>('ollama');
  const [customHost, setCustomHost] = useState('http://localhost:1234/v1');
  const [customModel, setCustomModel] = useState('');
  const [customEngine, setCustomEngine] = useState('lmstudio');
  const [customKey, setCustomKey] = useState('');
  const [srcMsg, setSrcMsg] = useState('');

  useEffect(() => {
    getInferenceSource().then((s) => {
      setSrcKind(s.kind);
      if (s.host) setCustomHost(s.host);
      if (s.model) setCustomModel(s.model);
      if (s.engine) setCustomEngine(s.engine);
    }).catch(() => {});
  }, []);

  const saveSource = useCallback(async () => {
    try {
      if (srcKind === 'custom') {
        await setInferenceSource({ kind: 'custom', host: customHost, model: customModel, engine: customEngine, apiKey: customKey || undefined });
      } else {
        await setInferenceSource({ kind: 'ollama' });
      }
      setSrcMsg('Saved — restart the app to apply.');
    } catch (e: any) {
      setSrcMsg(e?.message ?? 'Failed to save.');
    }
  }, [srcKind, customHost, customModel, customEngine, customKey]);

  const refreshMemoryStatus = useCallback(async () => {
    const requestId = ++memoryRequestId.current;
    setMemoryStatus({ kind: 'loading' });
    try {
      const stats = await getMemoryStats();
      if (requestId === memoryRequestId.current) {
        setMemoryStatus({ kind: 'ready', stats });
      }
    } catch (error) {
      if (requestId === memoryRequestId.current) {
        setMemoryStatus({
          kind: 'error',
          message: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }, []);

  useEffect(() => {
    void refreshMemoryStatus();
    const onFocus = () => { void refreshMemoryStatus(); };
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('focus', onFocus);
      ++memoryRequestId.current;
    };
  }, [refreshMemoryStatus, settings.apiUrl]);

  useEffect(() => {
    checkHealth().then(setHealthy);
    fetchSpeechHealth()
      .then((h) => setSpeechBackendAvailable(h.available))
      .catch(() => setSpeechBackendAvailable(false));
    fetchTtsHealth()
      .then((h) => setTtsBackend(h))
      .catch(() => setTtsBackend({ available: false }));
    fetchVoiceSettings()
      .then((vs) => {
        setVoiceSettings(vs);
        if (vs.has_api_key) {
          fetchElevenLabsVoices().then(setElevenLabsVoices).catch(() => {});
          fetchElevenLabsModels().then(setElevenLabsModels).catch(() => {});
        }
      })
      .catch(() => {});

    return () => {
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
    };
  }, []);

  const handleSaveApiKey = async () => {
    if (!elevenLabsApiKeyInput.trim()) return;
    try {
      const updated = await updateVoiceSettings({ api_key: elevenLabsApiKeyInput.trim() });
      setVoiceSettings(updated);
      setElevenLabsApiKeyInput('');
      showSaved();
      setConnTestState({ status: 'testing', message: 'Verifying saved API key...' });
      const testRes = await testElevenLabsConnection();
      setConnTestState({ status: testRes.status, message: testRes.message });
      if (testRes.valid) {
        fetchElevenLabsVoices().then(setElevenLabsVoices).catch(() => {});
        fetchElevenLabsModels().then(setElevenLabsModels).catch(() => {});
      }
      fetchTtsHealth().then(setTtsBackend).catch(() => setTtsBackend({ available: false }));
    } catch (err) {
      setConnTestState({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to save API key',
      });
    }
  };

  const handleTestConnection = async () => {
    setConnTestState({ status: 'testing', message: 'Testing connection to ElevenLabs...' });
    try {
      const res = await testElevenLabsConnection(elevenLabsApiKeyInput.trim() || undefined);
      setConnTestState({ status: res.status, message: res.message });
      if (res.valid) {
        fetchElevenLabsVoices().then(setElevenLabsVoices).catch(() => {});
        fetchElevenLabsModels().then(setElevenLabsModels).catch(() => {});
      }
    } catch (err) {
      setConnTestState({
        status: 'error',
        message: err instanceof Error ? err.message : 'Connection test failed',
      });
    }
  };

  const handleProviderChange = async (prov: string) => {
    try {
      const updated = await updateVoiceSettings({ provider: prov });
      setVoiceSettings(updated);
      showSaved();
      fetchTtsHealth().then(setTtsBackend).catch(() => setTtsBackend({ available: false }));
      if (prov === 'elevenlabs' && updated.has_api_key && elevenLabsVoices.length === 0) {
        fetchElevenLabsVoices().then(setElevenLabsVoices).catch(() => {});
        fetchElevenLabsModels().then(setElevenLabsModels).catch(() => {});
      }
    } catch (err) {
      console.error('Failed to change voice provider:', err);
    }
  };

  const handleVoiceParamChange = async (param: keyof VoiceSettingsUpdate, value: any) => {
    try {
      const updated = await updateVoiceSettings({ [param]: value });
      setVoiceSettings(updated);
      showSaved();
      fetchTtsHealth().then(setTtsBackend).catch(() => setTtsBackend({ available: false }));
    } catch (err) {
      console.error(`Failed to update voice setting ${param}:`, err);
    }
  };

  const handlePlayPreview = async () => {
    if (previewState === 'playing') {
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
      setPreviewState('idle');
      return;
    }

    setPreviewState('loading');
    try {
      const blob = await previewElevenLabsVoice({
        voiceId: voiceSettings?.voice_id,
        modelId: voiceSettings?.model_id,
        stability: voiceSettings?.stability,
        similarityBoost: voiceSettings?.similarity_boost,
        style: voiceSettings?.style,
        speed: voiceSettings?.speed,
        text: previewText,
      });
      const url = URL.createObjectURL(blob);
      previewUrlRef.current = url;
      const audioEl = new Audio(url);
      previewAudioRef.current = audioEl;
      audioEl.onended = () => {
        if (previewUrlRef.current) {
          URL.revokeObjectURL(previewUrlRef.current);
          previewUrlRef.current = null;
        }
        previewAudioRef.current = null;
        setPreviewState('idle');
      };
      audioEl.onerror = () => {
        if (previewUrlRef.current) {
          URL.revokeObjectURL(previewUrlRef.current);
          previewUrlRef.current = null;
        }
        previewAudioRef.current = null;
        setPreviewState('idle');
      };
      await audioEl.play();
      setPreviewState('playing');
    } catch (err) {
      setPreviewState('idle');
      setConnTestState({
        status: 'error',
        message: err instanceof Error ? err.message : 'Preview playback failed',
      });
    }
  };

  const showSaved = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  const handleExport = () => {
    const data = localStorage.getItem('openjarvis-conversations') || '{}';
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `openjarvis-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const data = JSON.parse(ev.target?.result as string);
          if (data.version === 1) {
            localStorage.setItem('openjarvis-conversations', JSON.stringify(data));
            useAppStore.getState().loadConversations();
            showSaved();
          }
        } catch {}
      };
      reader.readAsText(file);
    };
    input.click();
  };

  const [confirmClear, setConfirmClear] = useState(false);
  const handleClear = () => {
    if (!confirmClear) {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 3000);
      return;
    }
    localStorage.removeItem('openjarvis-conversations');
    useAppStore.getState().loadConversations();
    setConfirmClear(false);
    showSaved();
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-10">
      <div className="max-w-2xl mx-auto">
        <header className="mb-6">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
              Settings
            </h1>
            {saved && (
              <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full" style={{
                background: 'var(--color-accent-subtle)',
                color: 'var(--color-success)',
              }}>
                <Check size={12} /> Saved
              </span>
            )}
          </div>
          <p className="text-sm mt-2 max-w-2xl" style={{ color: 'var(--color-text-secondary)' }}>
            App preferences — appearance, model defaults, keyboard shortcuts, and data management.
          </p>
        </header>

        <div className="flex flex-col gap-4">
          {/* Appearance */}
          <Section title="Appearance">
            <SettingRow label="Theme" description="Choose how Ultron looks">
              <div className="flex gap-1 p-0.5 rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
                {themeOptions.map((opt) => {
                  const isActive = settings.theme === opt.value;
                  return (
                    <button
                      key={opt.value}
                      onClick={() => { updateSettings({ theme: opt.value }); showSaved(); }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer"
                      style={{
                        background: isActive ? 'var(--color-surface)' : 'transparent',
                        color: isActive ? 'var(--color-text)' : 'var(--color-text-tertiary)',
                        boxShadow: isActive ? 'var(--shadow-sm)' : 'none',
                      }}
                    >
                      <opt.icon size={14} />
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </SettingRow>
            <SettingRow label="Font size">
              <select
                value={settings.fontSize}
                onChange={(e) => { updateSettings({ fontSize: e.target.value as any }); showSaved(); }}
                className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <option value="small">Small</option>
                <option value="default">Default</option>
                <option value="large">Large</option>
              </select>
            </SettingRow>
          </Section>

          {/* Connection */}
          <Section title="Connection">
            <SettingRow
              label="Server status"
              description={
                serverInfo
                  ? `${typeof serverInfo.engine === 'string' ? serverInfo.engine : 'local'} / ${typeof serverInfo.model === 'string' ? serverInfo.model : 'default'}`
                  : 'Not connected'
              }
            >
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: healthy === true ? 'var(--color-success)' : healthy === false ? 'var(--color-error)' : 'var(--color-text-tertiary)' }}
                />
                <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {healthy === true ? 'Connected' : healthy === false ? 'Disconnected' : 'Checking...'}
                </span>
              </div>
            </SettingRow>
            <SettingRow label="API URL" description="Set if backend runs on a different port or host">
              <input
                type="text"
                value={settings.apiUrl}
                onChange={(e) => { updateSettings({ apiUrl: e.target.value }); showSaved(); }}
                placeholder="http://localhost:8000"
                className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              />
            </SettingRow>
            <SettingRow label="API key" description="Required only if the server was started with an API key">
              <input
                type="password"
                value={settings.apiKey}
                onChange={(e) => { updateSettings({ apiKey: e.target.value }); showSaved(); }}
                placeholder="OPENJARVIS_API_KEY"
                autoComplete="off"
                className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              />
            </SettingRow>
          </Section>

          {/* Inference source */}
          <Section title="Inference source">
            <SettingRow label="Source" description="Where the app runs models. Applies after restart.">
              <select
                value={srcKind}
                onChange={(e) => { setSrcKind(e.target.value as InferenceSource['kind']); setSrcMsg(''); }}
                className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
              >
                <option value="ollama">Bundled Ollama (default)</option>
                <option value="custom">Custom OpenAI-compatible server</option>
              </select>
            </SettingRow>
            {srcKind === 'custom' && (
              <>
                <SettingRow label="Server URL" description="e.g. LM Studio: http://localhost:1234/v1">
                  <input type="text" value={customHost} onChange={(e) => { setCustomHost(e.target.value); setSrcMsg(''); }} placeholder="http://localhost:1234/v1"
                    className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                    style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }} />
                </SettingRow>
                <SettingRow label="Model" description="Model id served by your endpoint">
                  <input type="text" value={customModel} onChange={(e) => { setCustomModel(e.target.value); setSrcMsg(''); }} placeholder="qwen2.5-7b-instruct"
                    className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                    style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }} />
                </SettingRow>
                <SettingRow label="Server type" description="OpenAI-compatible engine">
                  <select
                    value={customEngine}
                    onChange={(e) => {
                      const nextEngine = e.target.value;
                      setCustomEngine(nextEngine);
                      setSrcMsg('');
                      if (nextEngine === 'gemini') {
                        if (customHost === 'http://localhost:1234/v1' || !customHost.trim()) {
                          setCustomHost('https://generativelanguage.googleapis.com/v1beta/openai/');
                        }
                        if (!customModel.trim() || customModel === 'qwen2.5-7b-instruct') {
                          setCustomModel('gemini-3.8-flash');
                        }
                      }
                    }}
                    className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                    style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}>
                    <option value="gemini">Google Gemini</option>
                    <option value="lmstudio">LM Studio</option>
                    <option value="vllm">vLLM</option>
                    <option value="sglang">SGLang</option>
                    <option value="llamacpp">llama.cpp</option>
                    <option value="mlx">MLX</option>
                  </select>
                </SettingRow>
                <SettingRow label="API key (optional)" description="Only if your server requires one">
                  <input type="password" value={customKey} onChange={(e) => { setCustomKey(e.target.value); setSrcMsg(''); }} placeholder="leave blank if none"
                    className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
                    style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }} />
                </SettingRow>
              </>
            )}
            <SettingRow label="" description={srcMsg}>
              <button onClick={saveSource}
                className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                style={{ background: 'var(--color-accent, var(--color-bg-tertiary))', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}>
                Save inference source
              </button>
            </SettingRow>
          </Section>

          {/* Models */}
          <Section title="Models">
            <SettingRow label="Local models (Ollama)" description="Models available for local inference">
              <OllamaModelList />
            </SettingRow>
            <div className="text-xs mt-2 px-1" style={{ color: 'var(--color-text-tertiary)' }}>
              Run <code className="px-1 py-0.5 rounded text-[11px]" style={{ background: 'var(--color-bg-tertiary)' }}>ollama pull &lt;model-name&gt;</code> in your terminal to add more models
            </div>
            <SettingRow label="Cloud providers" description="Green dot means API key is configured">
              <div className="flex flex-wrap gap-3">
                <CloudProviderStatus label="OpenAI" keyName="OPENAI_API_KEY" />
                <CloudProviderStatus label="Anthropic" keyName="ANTHROPIC_API_KEY" />
                <CloudProviderStatus label="Google" keyName="GEMINI_API_KEY" />
                <CloudProviderStatus label="OpenRouter" keyName="OPENROUTER_API_KEY" />
                <CloudProviderStatus label="Atlas Cloud" keyName="ATLASCLOUD_API_KEY" />
              </div>
            </SettingRow>
          </Section>

          {/* One-Click Local Model Recommendation & Setup Wizard */}
          <LocalModelWizard />

          {/* Centralized Rate Limiting & Runtime Reliability */}
          <RuntimeLimitsSection />

          {/* API Keys */}
          <Section title="API Keys">
            <SettingRow label="OpenAI" description="GPT-4, GPT-3.5, etc.">
              <ApiKeyInput keyName="OPENAI_API_KEY" placeholder="sk-..." />
            </SettingRow>
            <SettingRow label="Anthropic" description="Claude models">
              <ApiKeyInput keyName="ANTHROPIC_API_KEY" placeholder="sk-ant-..." />
            </SettingRow>
            <SettingRow label="Google" description="Gemini models">
              <ApiKeyInput keyName="GEMINI_API_KEY" placeholder="AI..." />
            </SettingRow>
            <SettingRow label="OpenRouter" description="Multi-provider routing">
              <ApiKeyInput keyName="OPENROUTER_API_KEY" placeholder="sk-or-..." />
            </SettingRow>
            <SettingRow label="Atlas Cloud" description="Models routed through Atlas Cloud">
              <ApiKeyInput keyName="ATLASCLOUD_API_KEY" placeholder="Atlas Cloud API key" />
            </SettingRow>
          </Section>

          {/* Tools */}
          <Section title="Tools">
            <SettingRow label="Web Search" description="Tavily key for web search tool">
              <ApiKeyInput keyName="TAVILY_API_KEY" placeholder="tvly-..." toolName="web_search" />
            </SettingRow>
          </Section>

          {/* Memory */}
          <Section title="Memory">
            <MemoryStatusRow status={memoryStatus} onRetry={() => { void refreshMemoryStatus(); }} />
            <SettingRow label="Use memory context" description="Automatically inject relevant memories into conversations">
              <button
                onClick={() => {
                  const next = !memoryEnabled;
                  setMemoryEnabled(next);
                  try { localStorage.setItem('openjarvis-memory-enabled', String(next)); } catch {}
                  showSaved();
                }}
                className="relative w-11 h-6 rounded-full transition-colors cursor-pointer"
                style={{
                  background: memoryEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
                  style={{
                    transform: memoryEnabled ? 'translateX(20px)' : 'translateX(0)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }}
                />
              </button>
            </SettingRow>
            <SettingRow label="Memory backend" description="Which retrieval engine to use">
              <select
                value={memoryBackend}
                onChange={(e) => {
                  setMemoryBackend(e.target.value);
                  try { localStorage.setItem('openjarvis-memory-backend', e.target.value); } catch {}
                  showSaved();
                }}
                className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <option value="sqlite">sqlite</option>
                <option value="faiss">faiss</option>
                <option value="bm25">bm25</option>
                <option value="colbert">colbert</option>
                <option value="hybrid">hybrid</option>
              </select>
            </SettingRow>
            <SettingRow label="Results to inject" description={`${memoryTopK}`}>
              <input
                type="range"
                min="1"
                max="20"
                step="1"
                value={memoryTopK}
                onChange={(e) => {
                  const v = parseInt(e.target.value);
                  setMemoryTopK(v);
                  try { localStorage.setItem('openjarvis-memory-top-k', String(v)); } catch {}
                  showSaved();
                }}
                className="w-32 cursor-pointer accent-[var(--color-accent)]"
              />
            </SettingRow>
            <SettingRow label="Min relevance score" description={`${memoryMinScore}`}>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={memoryMinScore}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  setMemoryMinScore(v);
                  try { localStorage.setItem('openjarvis-memory-min-score', String(v)); } catch {}
                  showSaved();
                }}
                className="w-32 cursor-pointer accent-[var(--color-accent)]"
              />
            </SettingRow>
            <SettingRow label="Max context tokens" description={`${memoryMaxTokens}`}>
              <input
                type="range"
                min="256"
                max="8192"
                step="256"
                value={memoryMaxTokens}
                onChange={(e) => {
                  const v = parseInt(e.target.value);
                  setMemoryMaxTokens(v);
                  try { localStorage.setItem('openjarvis-memory-max-tokens', String(v)); } catch {}
                  showSaved();
                }}
                className="w-32 cursor-pointer accent-[var(--color-accent)]"
              />
            </SettingRow>
          </Section>

          {/* Model defaults */}
          <Section title="Model Defaults">
            <SettingRow label="Temperature" description={`${settings.temperature}`}>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={settings.temperature}
                onChange={(e) => { updateSettings({ temperature: parseFloat(e.target.value) }); showSaved(); }}
                className="w-32 cursor-pointer accent-[var(--color-accent)]"
              />
            </SettingRow>
            <SettingRow label="Max tokens" description={`${settings.maxTokens}`}>
              <input
                type="range"
                min="256"
                max="32768"
                step="256"
                value={settings.maxTokens}
                onChange={(e) => { updateSettings({ maxTokens: parseInt(e.target.value) }); showSaved(); }}
                className="w-32 cursor-pointer accent-[var(--color-accent)]"
              />
            </SettingRow>
          </Section>

          {/* Personalization & Cyber Experience */}
          <Section title="Personalization & Cyber Experience">
            <SettingRow
              label="Operator Title / Name"
              description="Preferred address used across speech replies and terminal greetings"
            >
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={userNameInput}
                  onChange={(e) => setUserNameInput(e.target.value)}
                  onKeyDown={(e) => {
                    soundEffects.handleKeyInputEvent(e);
                    if (e.key === 'Enter') handleSaveUserName();
                  }}
                  placeholder="e.g. Sir, Boss, Tony"
                  className="text-sm px-3 py-1.5 rounded-lg outline-none w-44"
                  style={{
                    background: 'var(--color-bg-secondary)',
                    color: 'var(--color-text)',
                    border: '1px solid var(--color-border)',
                  }}
                />
                <button
                  onClick={handleSaveUserName}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors"
                  style={{
                    background: userNameSaved ? 'var(--color-success)' : 'var(--color-accent)',
                    color: '#ffffff',
                  }}
                >
                  {userNameSaved ? 'Saved' : 'Save'}
                </button>
              </div>
            </SettingRow>

            <SettingRow
              label="Voice Gender / Timbre"
              description="Speech output voice timbre (Ultron's visual hologram is always the canonical Electron)"
            >
              <div className="flex gap-1.5 p-0.5 rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
                {(['masculine', 'feminine', 'neutral'] as const).map((p) => {
                  const isActive = (settings.voiceGender || settings.voicePresentation || 'masculine') === p;
                  return (
                    <button
                      key={p}
                      onClick={() => handlePresentationChange(p)}
                      className="px-3 py-1.5 rounded-md text-xs font-medium capitalize cursor-pointer transition-colors"
                      style={{
                        background: isActive ? 'var(--color-surface)' : 'transparent',
                        color: isActive ? 'var(--color-text)' : 'var(--color-text-tertiary)',
                        boxShadow: isActive ? 'var(--shadow-sm)' : 'none',
                      }}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </SettingRow>

            <div className="p-3 my-1 rounded-xl flex items-center justify-between border" style={{
              background: 'var(--color-bg-secondary)',
              borderColor: 'var(--color-border)',
            }}>
              <div>
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                  Canonical Hologram Preview
                </span>
                <p className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                  Visualized on the 1,100 node depth-projected Electron particle lattice.
                </p>
              </div>
              <div className="rounded-lg p-1" style={{ background: '#090d16' }}>
                <UltronParticleCore
                  variant="neutral"
                  state="idle"
                  size={120}
                  showReticle={false}
                />
              </div>
            </div>

            <SettingRow
              label="Behavioral Persona"
              description="Assistant style, tone calibration, and interactive register"
            >
              <select
                value={settings.persona || 'jarvis'}
                onChange={(e) => handlePersonaChange(e.target.value)}
                className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              >
                {PERSONA_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.badge})
                  </option>
                ))}
              </select>
            </SettingRow>

            <SettingRow
              label="Primary Language"
              description="Supported interaction language (full native support for English, Urdu & Hindi)"
            >
              <select
                value={settings.language || 'en'}
                onChange={(e) => handleLanguageChange(e.target.value as 'en' | 'ur' | 'hi' | 'auto')}
                className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <option value="en">English (US / UK)</option>
                <option value="ur">اردو (Urdu)</option>
                <option value="hi">हिंदी (Hindi)</option>
                <option value="auto">Auto-Detect (Multilingual)</option>
              </select>
            </SettingRow>

            {(settings.language === 'ur' || settings.language === 'hi') && (!voiceSettings || voiceSettings.provider === 'system') && (
              <div
                className="p-3 my-1 rounded-lg text-xs leading-relaxed"
                style={{
                  background: 'rgba(245, 158, 11, 0.08)',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                }}
              >
                <span className="font-semibold text-amber-500">Notice on Multilingual Spoken Audio: </span>
                Windows OS built-in SAPI voices synthesize English speech locally. Ultron generates fluent text in your selected language ({settings.language === 'ur' ? 'Urdu' : 'Hindi'}). For spoken neural voice output in Urdu or Hindi, configure ElevenLabs or OpenAI TTS below.
              </div>
            )}

            <SettingRow
              label="Cyber UI Sound Effects"
              description="Futuristic digital click, typing ticks, and confirmation chimes synthesized via Web Audio"
            >
              <button
                onClick={() => handleSoundToggle(!settings.soundEnabled)}
                className="relative w-11 h-6 rounded-full transition-colors cursor-pointer"
                style={{
                  background: settings.soundEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
                  style={{
                    transform: settings.soundEnabled ? 'translateX(20px)' : 'translateX(0)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }}
                />
              </button>
            </SettingRow>

            <SettingRow
              label="Cyber Sound Volume"
              description={`${Math.round((settings.soundVolume ?? 0.6) * 100)}%`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={settings.soundVolume ?? 0.6}
                  disabled={!settings.soundEnabled}
                  onChange={(e) => handleSoundVolumeChange(parseFloat(e.target.value))}
                  className="w-32 cursor-pointer accent-[var(--color-accent)]"
                  style={{ opacity: settings.soundEnabled ? 1 : 0.4 }}
                />
                <button
                  onClick={() => {
                    soundEffects.playClick();
                    setTimeout(() => soundEffects.playSuccessChime(), 120);
                  }}
                  disabled={!settings.soundEnabled}
                  className="px-2.5 py-1 text-xs rounded border cursor-pointer"
                  style={{
                    background: 'var(--color-bg-secondary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-secondary)',
                    opacity: settings.soundEnabled ? 1 : 0.4,
                  }}
                >
                  Test Audio
                </button>
              </div>
            </SettingRow>

            <SettingRow
              label="Cinematic Onboarding Tour"
              description="Revisit the multi-stage introduction, persona selector, and voice calibration wizard"
            >
              <button
                onClick={handleRelaunchOnboarding}
                className="px-3.5 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors flex items-center gap-1.5"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text)',
                }}
              >
                <Sparkles size={13} className="text-cyan-400" />
                Relaunch Tour
              </button>
            </SettingRow>
          </Section>

          {/* Speech */}
          <Section title="Speech">
            <SettingRow label="Speech-to-Text" description="Enable microphone input for voice dictation">
              <button
                onClick={() => { updateSettings({ speechEnabled: !settings.speechEnabled }); showSaved(); }}
                className="relative w-11 h-6 rounded-full transition-colors cursor-pointer"
                style={{
                  background: settings.speechEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
                  style={{
                    transform: settings.speechEnabled ? 'translateX(20px)' : 'translateX(0)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }}
                />
              </button>
            </SettingRow>
            <SettingRow label="Text-to-Speech" description="Show a read-aloud button on assistant replies">
              <button
                onClick={() => { updateSettings({ voiceOutputEnabled: !settings.voiceOutputEnabled }); showSaved(); }}
                className="relative w-11 h-6 rounded-full transition-colors cursor-pointer"
                style={{
                  background: settings.voiceOutputEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
                  style={{
                    transform: settings.voiceOutputEnabled ? 'translateX(20px)' : 'translateX(0)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }}
                />
              </button>
            </SettingRow>
            <SettingRow label="Speak replies automatically" description="Read every assistant reply aloud as soon as it finishes">
              <button
                onClick={() => { updateSettings({ voiceAutoplay: !settings.voiceAutoplay }); showSaved(); }}
                disabled={!settings.voiceOutputEnabled}
                className="relative w-11 h-6 rounded-full transition-colors cursor-pointer"
                style={{
                  background: settings.voiceAutoplay && settings.voiceOutputEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                  opacity: settings.voiceOutputEnabled ? 1 : 0.4,
                  cursor: settings.voiceOutputEnabled ? 'pointer' : 'default',
                }}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
                  style={{
                    transform: settings.voiceAutoplay && settings.voiceOutputEnabled ? 'translateX(20px)' : 'translateX(0)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                  }}
                />
              </button>
            </SettingRow>
            <SettingRow label="Voice provider" description="Select speech synthesis provider">
              <select
                id="voice-provider-select"
                value={voiceSettings?.provider || 'system'}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <option value="system">System Default (Windows SAPI / Local)</option>
                <option value="elevenlabs">ElevenLabs</option>
              </select>
            </SettingRow>

            <SettingRow label="Active voice" description="Backend and voice used for spoken replies">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    background: ttsBackend?.available ? 'var(--color-success)' : 'var(--color-text-tertiary)',
                  }}
                />
                <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {ttsBackend === null ? 'Checking...'
                    : ttsBackend.available ? `${ttsBackend.backend}${ttsBackend.voice_id ? ` / ${ttsBackend.voice_id}` : ''}`
                    : 'Not configured'}
                </span>
              </div>
            </SettingRow>

            {/* ElevenLabs Configuration Panel */}
            {(voiceSettings?.provider === 'elevenlabs' || voiceSettings?.has_api_key) && (
              <div
                id="elevenlabs-settings-panel"
                className="my-2 p-4 rounded-xl flex flex-col gap-3.5"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <div className="flex items-center justify-between pb-2 border-b" style={{ borderColor: 'var(--color-border)' }}>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">ElevenLabs Voice Configuration</span>
                    {voiceSettings?.has_api_key ? (
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: 'rgba(34,197,94,0.15)', color: 'var(--color-success)' }}>
                        Connected
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--color-error)' }}>
                        Key Required
                      </span>
                    )}
                  </div>
                  {voiceSettings?.masked_api_key && (
                    <span className="text-xs font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                      Key: {voiceSettings.masked_api_key}
                    </span>
                  )}
                </div>

                {/* API Key Input and Action Buttons */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                    API Key
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="elevenlabs-api-key-input"
                      type="password"
                      value={elevenLabsApiKeyInput}
                      onChange={(e) => setElevenLabsApiKeyInput(e.target.value)}
                      placeholder={voiceSettings?.has_api_key ? 'Update ElevenLabs API Key...' : 'Enter ElevenLabs API Key...'}
                      autoComplete="off"
                      className="text-sm px-3 py-1.5 rounded-lg outline-none flex-1"
                      style={{
                        background: 'var(--color-bg-primary)',
                        color: 'var(--color-text)',
                        border: '1px solid var(--color-border)',
                      }}
                    />
                    <button
                      id="elevenlabs-save-key-btn"
                      onClick={handleSaveApiKey}
                      disabled={!elevenLabsApiKeyInput.trim()}
                      className="text-xs px-3 py-1.5 rounded-lg transition-colors font-medium cursor-pointer"
                      style={{
                        background: elevenLabsApiKeyInput.trim() ? 'var(--color-accent)' : 'var(--color-bg-tertiary)',
                        color: elevenLabsApiKeyInput.trim() ? '#fff' : 'var(--color-text-tertiary)',
                        cursor: elevenLabsApiKeyInput.trim() ? 'pointer' : 'default',
                      }}
                    >
                      Save Key
                    </button>
                    <button
                      id="elevenlabs-test-conn-btn"
                      onClick={handleTestConnection}
                      disabled={connTestState.status === 'testing' || (!voiceSettings?.has_api_key && !elevenLabsApiKeyInput.trim())}
                      className="text-xs px-3 py-1.5 rounded-lg transition-colors font-medium cursor-pointer"
                      style={{
                        background: 'var(--color-bg-tertiary)',
                        color: 'var(--color-text)',
                        border: '1px solid var(--color-border)',
                      }}
                    >
                      {connTestState.status === 'testing' ? 'Testing...' : 'Test Connection'}
                    </button>
                  </div>
                  {connTestState.message && (
                    <div
                      id="elevenlabs-conn-status-msg"
                      className="text-xs mt-1 px-2.5 py-1.5 rounded-lg flex items-center gap-2"
                      style={{
                        background:
                          connTestState.status === 'connected' ? 'rgba(34,197,94,0.1)' :
                          connTestState.status === 'invalid_key' ? 'rgba(239,68,68,0.1)' :
                          connTestState.status === 'quota_limited' ? 'rgba(245,158,11,0.1)' :
                          'rgba(148,163,184,0.1)',
                        color:
                          connTestState.status === 'connected' ? 'var(--color-success)' :
                          connTestState.status === 'invalid_key' ? 'var(--color-error)' :
                          connTestState.status === 'quota_limited' ? '#f59e0b' :
                          'var(--color-text-secondary)',
                      }}
                    >
                      <span className="w-1.5 h-1.5 rounded-full" style={{
                        background:
                          connTestState.status === 'connected' ? 'var(--color-success)' :
                          connTestState.status === 'invalid_key' ? 'var(--color-error)' :
                          connTestState.status === 'quota_limited' ? '#f59e0b' :
                          'var(--color-text-secondary)',
                      }} />
                      <span>{connTestState.message}</span>
                    </div>
                  )}
                </div>

                {/* Voice & Model Dynamic Selectors */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                      Account Voice
                    </label>
                    <select
                      id="elevenlabs-voice-select"
                      value={voiceSettings?.voice_id || 'JBFqnCBsd6RMkjVDRZzb'}
                      onChange={(e) => handleVoiceParamChange('voice_id', e.target.value)}
                      className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                      style={{
                        background: 'var(--color-bg-primary)',
                        color: 'var(--color-text)',
                        border: '1px solid var(--color-border)',
                      }}
                    >
                      {elevenLabsVoices.length > 0 ? (
                        elevenLabsVoices.map((v) => (
                          <option key={v.voice_id} value={v.voice_id}>
                            {v.name} {v.category ? `(${v.category})` : ''}
                          </option>
                        ))
                      ) : (
                        <option value="JBFqnCBsd6RMkjVDRZzb">George (Jarvis Preset)</option>
                      )}
                    </select>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                      TTS Model
                    </label>
                    <select
                      id="elevenlabs-model-select"
                      value={voiceSettings?.model_id || 'eleven_turbo_v2_5'}
                      onChange={(e) => handleVoiceParamChange('model_id', e.target.value)}
                      className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
                      style={{
                        background: 'var(--color-bg-primary)',
                        color: 'var(--color-text)',
                        border: '1px solid var(--color-border)',
                      }}
                    >
                      {elevenLabsModels.length > 0 ? (
                        elevenLabsModels.map((m) => (
                          <option key={m.model_id} value={m.model_id}>
                            {m.name}
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="eleven_turbo_v2_5">Eleven Turbo v2.5 (Fastest)</option>
                          <option value="eleven_multilingual_v2">Eleven Multilingual v2</option>
                          <option value="eleven_monolingual_v1">Eleven Monolingual v1</option>
                        </>
                      )}
                    </select>
                  </div>
                </div>

                {/* Fine-Tuning Sliders: Stability, Similarity, Style, Speed */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 border-t" style={{ borderColor: 'var(--color-border)' }}>
                  <div className="flex flex-col gap-1">
                    <div className="flex justify-between text-xs">
                      <span style={{ color: 'var(--color-text-secondary)' }}>Stability</span>
                      <span className="font-mono text-xs">{voiceSettings?.stability?.toFixed(2) ?? '0.50'}</span>
                    </div>
                    <input
                      id="elevenlabs-stability-slider"
                      type="range"
                      min="0.0"
                      max="1.0"
                      step="0.05"
                      value={voiceSettings?.stability ?? 0.5}
                      onChange={(e) => handleVoiceParamChange('stability', parseFloat(e.target.value))}
                      className="accent-[var(--color-accent)] cursor-pointer"
                    />
                  </div>

                  <div className="flex flex-col gap-1">
                    <div className="flex justify-between text-xs">
                      <span style={{ color: 'var(--color-text-secondary)' }}>Similarity Boost</span>
                      <span className="font-mono text-xs">{voiceSettings?.similarity_boost?.toFixed(2) ?? '0.75'}</span>
                    </div>
                    <input
                      id="elevenlabs-similarity-slider"
                      type="range"
                      min="0.0"
                      max="1.0"
                      step="0.05"
                      value={voiceSettings?.similarity_boost ?? 0.75}
                      onChange={(e) => handleVoiceParamChange('similarity_boost', parseFloat(e.target.value))}
                      className="accent-[var(--color-accent)] cursor-pointer"
                    />
                  </div>

                  <div className="flex flex-col gap-1">
                    <div className="flex justify-between text-xs">
                      <span style={{ color: 'var(--color-text-secondary)' }}>Style Exaggeration</span>
                      <span className="font-mono text-xs">{voiceSettings?.style?.toFixed(2) ?? '0.00'}</span>
                    </div>
                    <input
                      id="elevenlabs-style-slider"
                      type="range"
                      min="0.0"
                      max="1.0"
                      step="0.05"
                      value={voiceSettings?.style ?? 0.0}
                      onChange={(e) => handleVoiceParamChange('style', parseFloat(e.target.value))}
                      className="accent-[var(--color-accent)] cursor-pointer"
                    />
                  </div>

                  <div className="flex flex-col gap-1">
                    <div className="flex justify-between text-xs">
                      <span style={{ color: 'var(--color-text-secondary)' }}>Speed</span>
                      <span className="font-mono text-xs">{voiceSettings?.speed?.toFixed(2) ?? '1.00'}x</span>
                    </div>
                    <input
                      id="elevenlabs-speed-slider"
                      type="range"
                      min="0.5"
                      max="2.0"
                      step="0.05"
                      value={voiceSettings?.speed ?? 1.0}
                      onChange={(e) => handleVoiceParamChange('speed', parseFloat(e.target.value))}
                      className="accent-[var(--color-accent)] cursor-pointer"
                    />
                  </div>
                </div>

                {/* Voice Preview Section */}
                <div className="pt-2 border-t flex flex-col gap-2" style={{ borderColor: 'var(--color-border)' }}>
                  <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                    Voice Preview
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="elevenlabs-preview-text-input"
                      type="text"
                      value={previewText}
                      onChange={(e) => setPreviewText(e.target.value)}
                      maxLength={120}
                      placeholder="Sample preview phrase..."
                      className="text-xs px-3 py-1.5 rounded-lg outline-none flex-1"
                      style={{
                        background: 'var(--color-bg-primary)',
                        color: 'var(--color-text)',
                        border: '1px solid var(--color-border)',
                      }}
                    />
                    <button
                      id="elevenlabs-preview-btn"
                      onClick={handlePlayPreview}
                      disabled={previewState === 'loading' || !voiceSettings?.has_api_key}
                      className="text-xs px-3.5 py-1.5 rounded-lg transition-colors font-medium flex items-center gap-1.5"
                      style={{
                        background: previewState === 'playing' ? 'var(--color-error)' : 'var(--color-accent)',
                        color: '#fff',
                        opacity: !voiceSettings?.has_api_key ? 0.5 : 1,
                        cursor: voiceSettings?.has_api_key ? 'pointer' : 'default',
                      }}
                    >
                      {previewState === 'loading' ? 'Generating...' : previewState === 'playing' ? 'Stop' : 'Play Preview'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            <SettingRow label="Backend status" description="Requires Whisper, Deepgram, or another speech backend">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    background: speechBackendAvailable === true ? 'var(--color-success)'
                      : speechBackendAvailable === false ? 'var(--color-text-tertiary)'
                      : 'var(--color-text-tertiary)',
                  }}
                />
                <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {speechBackendAvailable === null ? 'Checking...'
                    : speechBackendAvailable ? 'Available'
                    : 'Not configured'}
                </span>
              </div>
            </SettingRow>
            {!speechBackendAvailable && speechBackendAvailable !== null && (
              <div className="text-xs mt-2 px-1" style={{ color: 'var(--color-text-tertiary)' }}>
                Set up a speech backend to use voice input.
                See the <a href="https://open-jarvis.github.io/OpenJarvis/user-guide/tools/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-accent)' }}>documentation</a> for details.
              </div>
            )}
          </Section>

          {/* Model Context Protocol (MCP) */}
          <MCPServersSection />

          {/* Data */}
          <Section title="Data">
            <SettingRow label="Conversations" description={`${conversations.length} stored locally`}>
              <div className="flex gap-2">
                <button
                  onClick={handleExport}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                  style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
                >
                  <Download size={12} /> Export
                </button>
                <button
                  onClick={handleImport}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                  style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
                >
                  <Upload size={12} /> Import
                </button>
              </div>
            </SettingRow>
            <SettingRow label="Clear all data" description="Permanently delete all conversations">
              <button
                onClick={handleClear}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                style={{
                  color: confirmClear ? 'white' : 'var(--color-error)',
                  background: confirmClear ? 'var(--color-error)' : 'transparent',
                  border: '1px solid var(--color-error)',
                }}
                onMouseEnter={(e) => { if (!confirmClear) e.currentTarget.style.background = 'rgba(220,38,38,0.1)'; }}
                onMouseLeave={(e) => { if (!confirmClear) e.currentTarget.style.background = 'transparent'; }}
              >
                <Trash2 size={12} /> {confirmClear ? 'Click again to confirm' : 'Clear'}
              </button>
            </SettingRow>
          </Section>

          {/* Updates */}
          <Section title="Updates">
            <SettingRow label="Auto-update" description="Check for new desktop builds automatically every 30 minutes">
              <button
                onClick={() => handleAutoUpdateToggle(!autoUpdateEnabled)}
                className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
                style={{ background: autoUpdateEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)' }}
              >
                <span
                  className="inline-block h-3.5 w-3.5 rounded-full transition-transform"
                  style={{
                    background: 'white',
                    transform: autoUpdateEnabled ? 'translateX(18px)' : 'translateX(2px)',
                  }}
                />
              </button>
            </SettingRow>
            <SettingRow label="Check for updates" description="Manually check for a new version right now">
              <button
                onClick={handleCheckNow}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                style={{ background: 'var(--color-bg-tertiary)', border: '1px solid var(--color-border)', color: 'var(--color-text)', cursor: 'pointer' }}
                disabled={updateCheckState === 'checking'}
              >
                <RefreshCw size={12} className={updateCheckState === 'checking' ? 'animate-spin' : ''} />
                {updateCheckState === 'checking' && 'Checking...'}
                {updateCheckState === 'available' && 'Update available — see banner above'}
                {updateCheckState === 'latest' && 'Already up to date'}
                {updateCheckState === 'idle' && 'Check now'}
              </button>
            </SettingRow>
          </Section>

          {/* About */}
          <Section title="About">
            <div className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              <p className="mb-2">
                <span className="font-semibold" style={{ color: 'var(--color-text)' }}>Ultron</span> — Sovereign AI Assistant.
              </p>
              <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                Part of Intelligence Per Watt, a research initiative at Stanford SAIL.
              </p>
              <div className="flex gap-3 mt-3 text-xs">
                <a
                  href="https://openjarvis.stanford.edu/"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--color-accent)' }}
                >
                  Project site
                </a>
                <a
                  href="https://open-jarvis.github.io/OpenJarvis/"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--color-accent)' }}
                >
                  Documentation
                </a>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
