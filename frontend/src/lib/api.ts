import type {
  ModelInfo,
  SavingsData,
  ServerInfo,
  TaskRecord,
  TaskStep,
  TaskStatus,
  StepStatus,
  MemoryFact,
  MemoryFactsResponse,
  LearnedSkill,
  LearnedSkillsResponse,
  MaintenanceSuggestion,
  MaintenanceScanResponse,
  CreateCompositeSkillRequest,
  ValidateCompositeSkillResponse,
  CreateCompositeSkillResponse,
} from '../types';
import { SUPABASE_ANON_KEY, SUPABASE_URL } from './supabase';
import { serializeToolCallArguments } from './tool-call';

// ---------------------------------------------------------------------------
// Supabase config
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export const isTauri = () => typeof window !== 'undefined' && !!window.__TAURI_INTERNALS__;

export type CloudKeyStatus = Record<string, boolean>;

export async function getCloudKeyStatus(): Promise<CloudKeyStatus> {
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const rows = await invoke<Array<{ key: string; set: boolean }>>('get_cloud_key_status');
      const status = Object.fromEntries(rows.map((row) => [row.key, row.set]));
      if (Object.keys(status).length > 0) {
        return status;
      }
    } catch {
      // Fall through to server endpoint
    }
  }
  try {
    const res = await apiFetch('/v1/cloud/keys');
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Ignore error and return empty status
  }
  return {};
}

export async function saveCloudKey(keyName: string, keyValue: string): Promise<void> {
  let saved = false;
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('save_cloud_key', { keyName, keyValue });
      saved = true;
    } catch (e) {
      console.warn('Tauri save_cloud_key failed, using server endpoint:', e);
    }
  }
  try {
    const res = await apiFetch('/v1/cloud/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key_name: keyName, key_value: keyValue }),
    });
    if (res.ok) {
      saved = true;
    } else if (!saved) {
      const err = await res.text();
      throw new Error(`Failed to save cloud key: ${err}`);
    }
  } catch (e: any) {
    if (!saved) {
      throw new Error(e?.message ?? 'Failed to save cloud key');
    }
  }
}

// Cached API base URL fetched from the Tauri backend at startup.
// This avoids hardcoding the port — the Rust backend is the single
// source of truth for JARVIS_PORT.
let _tauriApiBase: string | null = null;

/** Pre-fetch the API base URL from the Tauri backend (call once at init). */
export async function initApiBase(): Promise<void> {
  if (!isTauri()) return;
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    _tauriApiBase = await invoke<string>('get_api_base');
  } catch {
    // Command may not exist on older builds; fall through to default.
  }
}

const DESKTOP_API_FALLBACK = 'http://127.0.0.1:8000';

const getSettingsApiUrl = (): string => {
  try {
    const raw = localStorage.getItem('openjarvis-settings');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.apiUrl) return parsed.apiUrl.replace(/\/+$/, '');
    }
  } catch {}
  return '';
};

export const getBase = (): string => {
  const settingsUrl = getSettingsApiUrl();
  if (settingsUrl) return settingsUrl;
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (isTauri()) return _tauriApiBase || DESKTOP_API_FALLBACK;
  return '';
};

// Resolve the local server API key (OPENJARVIS_API_KEY). When `jarvis serve`
// is started with a key, AuthMiddleware 401s every /v1 and /api request that
// lacks a Bearer token — so the frontend must send it (#266). Sourced from the
// same settings blob as the API URL, with an optional build-time env override.
// Returns '' when unset, so a keyless local server keeps working unchanged.
export const getApiKey = (): string => {
  try {
    const raw = localStorage.getItem('openjarvis-settings');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.apiKey) return String(parsed.apiKey);
    }
  } catch {}
  if (import.meta.env.VITE_OPENJARVIS_API_KEY) {
    return import.meta.env.VITE_OPENJARVIS_API_KEY as string;
  }
  return '';
};

// Build request headers with the Bearer Authorization token when a local key
// is configured, merging any caller-supplied headers. Adds no Authorization
// header when no key is set, so keyless local dev is byte-for-byte unchanged.
export const authHeaders = (
  extra: Record<string, string> = {},
): Record<string, string> => {
  const key = getApiKey();
  return key ? { ...extra, Authorization: `Bearer ${key}` } : { ...extra };
};

// Centralized fetch for the local server: prepends getBase() and injects the
// Bearer auth header (when a key is set) on every call. Using this everywhere
// guarantees no /v1 or /api request is sent without auth — the bug in #266 was
// that direct fetch() calls omitted the header and 401'd. `path` is the
// server-relative path (e.g. "/v1/savings").
export const apiFetch = (
  path: string,
  init: RequestInit = {},
): Promise<Response> => {
  const headers = authHeaders(
    (init.headers as Record<string, string> | undefined) ?? {},
  );
  return fetch(`${getBase()}${path}`, { ...init, headers });
};

async function tauriInvoke<T>(command: string, args: Record<string, unknown> = {}): Promise<T> {
  const { invoke } = await import('@tauri-apps/api/core');
  const apiUrl = getBase();
  return invoke<T>(command, { apiUrl, ...args });
}

export const syncDesktopAuthToken = async (token?: string): Promise<void> => {
  try {
    const key = token !== undefined ? token : getApiKey();
    await tauriInvoke('set_desktop_auth_token', { token: key });
  } catch {
    // Silently ignore if running outside Tauri desktop
  }
};

// ---------------------------------------------------------------------------
// Setup status (desktop only)
// ---------------------------------------------------------------------------

export interface SetupStatus {
  phase: string;
  detail: string;
  ollama_ready: boolean;
  server_ready: boolean;
  model_ready: boolean;
  error: string | null;
  source: 'unconfigured' | 'ollama' | 'custom';
  requires_source: boolean;
  requires_credential?: boolean;
  credential_provider?: string | null;
  credential_key_name?: string | null;
  saved_model?: string | null;
  saved_host?: string | null;
}

export async function getSetupStatus(): Promise<SetupStatus | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<SetupStatus>('get_setup_status');
  } catch {
    return null;
  }
}

/** Start desktop services after an inference source has been persisted. */
export async function startBackend(): Promise<void> {
  if (!isTauri()) throw new Error('The desktop backend is available in the desktop app only.');
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke<void>('start_backend');
  } catch (e: any) {
    throw new Error(e?.message ?? e ?? 'Failed to start the desktop backend');
  }
}

/** Update an inference credential in secure storage and restart desktop backend startup. */
export async function updateInferenceCredential(keyName: string, keyValue: string): Promise<void> {
  if (!isTauri()) throw new Error('Credential update is available in the desktop app only.');
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke<void>('update_inference_credential', { keyName, keyValue });
  } catch (e: any) {
    throw new Error(e?.message ?? e ?? 'Failed to update inference credential');
  }
}

/** Stop an in-flight setup and return the desktop to its inert source chooser. */
export async function resetInferenceSource(): Promise<void> {
  if (!isTauri()) throw new Error('Inference setup recovery is available in the desktop app only.');
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke<void>('reset_inference_source');
  } catch (e: any) {
    throw new Error(e?.message ?? e ?? 'Failed to reset inference setup');
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchModels(): Promise<ModelInfo[]> {
  if (isTauri()) {
    try {
      const result = await tauriInvoke<{ data?: ModelInfo[] }>('fetch_models');
      return result?.data || [];
    } catch {
      // Fall through to fetch
    }
  }
  const res = await apiFetch(`/v1/models`);
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`);
  const data = await res.json();
  return data.data || [];
}

export async function fetchRecommendedModel(): Promise<{ model: string; reason: string }> {
  const res = await apiFetch(`/v1/recommended-model`);
  if (!res.ok) return { model: '', reason: 'Failed to fetch' };
  return res.json();
}

export async function pullModel(modelName: string): Promise<void> {
  // In Tauri, go through the Rust backend directly (avoids CORS / timeout
  // issues with long model downloads via fetch).
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('pull_ollama_model', { modelName });
      return;
    } catch (e: any) {
      throw new Error(e?.message || e || 'Download failed');
    }
  }
  const res = await apiFetch(`/v1/models/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Failed to pull model: ${detail}`);
  }
}

export async function deleteModel(modelName: string): Promise<void> {
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('delete_ollama_model', { modelName });
      return;
    } catch (e: any) {
      throw new Error(e?.message || e || 'Delete failed');
    }
  }
  const res = await apiFetch(`/v1/models/${encodeURIComponent(modelName)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Failed to delete model: ${detail}`);
  }
}

const _CLOUD_PREFIXES = ['gpt-', 'o1-', 'o3-', 'o4-', 'claude-', 'gemini-', 'openrouter/', 'atlascloud/', 'minimax', 'deepseek-'];

export async function preloadModel(modelName: string, owner?: string): Promise<void> {
  // Cloud models don't need Ollama preloading
  if (owner === 'litellm' || _CLOUD_PREFIXES.some(p => modelName.startsWith(p))) {
    return;
  }
  // Trigger Ollama to load the model into memory (empty prompt, no generation).
  const ollamaUrl = 'http://127.0.0.1:11434';
  try {
    const res = await fetch(`${ollamaUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelName, prompt: '', keep_alive: '5m' }),
      signal: AbortSignal.timeout(120_000),
    });
    if (!res.ok) throw new Error(`Preload failed: ${res.status}`);
  } catch (e: any) {
    if (e.name === 'TimeoutError') throw new Error('Model load timed out (120s)');
    throw e;
  }
}

export async function fetchSavings(): Promise<SavingsData> {
  const res = await apiFetch(`/v1/savings`);
  if (!res.ok) throw new Error(`Failed to fetch savings: ${res.status}`);
  return res.json();
}

export async function fetchServerInfo(): Promise<ServerInfo> {
  const res = await apiFetch(`/v1/info`);
  if (!res.ok) throw new Error(`Failed to fetch server info: ${res.status}`);
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  if (isTauri()) {
    try {
      await tauriInvoke('check_health', { apiUrl: getBase() });
      return true;
    } catch {
      return false;
    }
  }
  // In the browser, hit /health relative to the page origin so the request
  // flows through whatever path is already serving the SPA — the Vite
  // proxy in dev, FastAPI's static mount in prod. This avoids the
  // false-negative "Cannot reach backend" banner when getBase() points at
  // an absolute URL the browser can't reach directly.
  //
  // If /health itself fails for any reason (proxy quirk, stale service
  // worker, etc.) fall back to an arbitrary API endpoint we know the rest
  // of the app polls successfully. If THAT also fails we genuinely can't
  // reach the backend.
  const probe = async (url: string): Promise<boolean> => {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      return res.ok;
    } catch {
      return false;
    }
  };
  // In browser mode Vite serves the SPA on a different port than the API.
  // Probe the configured API base first; the relative fallback supports
  // production deployments where both are served from one origin.
  const base = getBase().replace(/\/+$/, '');
  if (base && await probe(`${base}/health`)) return true;
  if (await probe('/health')) return true;
  if (base && await probe(`${base}/v1/connectors`)) return true;
  return probe('/v1/connectors');
}

export async function fetchEnergy(): Promise<unknown> {
  if (isTauri()) {
    try {
      return await tauriInvoke('fetch_energy', { apiUrl: getBase() });
    } catch {}
  }
  const res = await apiFetch(`/v1/telemetry/energy`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchTelemetry(): Promise<unknown> {
  if (isTauri()) {
    try {
      return await tauriInvoke('fetch_telemetry', { apiUrl: getBase() });
    } catch {}
  }
  const res = await apiFetch(`/v1/telemetry/stats`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchTraces(limit: number = 50): Promise<unknown> {
  if (isTauri()) {
    try {
      return await tauriInvoke('fetch_traces', { apiUrl: getBase(), limit });
    } catch {}
  }
  const res = await apiFetch(`/v1/traces?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Speech
// ---------------------------------------------------------------------------

export interface TranscriptionResult {
  text: string;
  language: string | null;
  confidence: number | null;
  duration_seconds: number;
}

export interface SpeechHealth {
  available: boolean;
  backend?: string;
  reason?: string;
}

export async function transcribeAudio(audioBlob: Blob, filename = 'recording.webm'): Promise<TranscriptionResult> {
  if (isTauri()) {
    try {
      const buffer = await audioBlob.arrayBuffer();
      return await tauriInvoke<TranscriptionResult>('transcribe_audio', {
        audioData: Array.from(new Uint8Array(buffer)),
        filename,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(msg || 'Transcription failed');
    }
  }
  const formData = new FormData();
  formData.append('file', audioBlob, filename);
  const res = await apiFetch(`/v1/speech/transcribe`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : "";
    } catch {
      // Keep the status-only message below when the body is not JSON.
    }
    throw new Error(detail || `Transcription failed: ${res.status}`);
  }
  return res.json();
}

export interface TtsHealth {
  available: boolean;
  backend?: string;
  voice_id?: string;
  speed?: number;
  reason?: string;
}

export async function synthesizeSpeech(
  text: string,
  opts: { voiceId?: string; speed?: number; signal?: AbortSignal } = {},
): Promise<Blob> {
  const res = await apiFetch(`/v1/speech/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice_id: opts.voiceId, speed: opts.speed }),
    signal: opts.signal,
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : '';
    } catch {
      // Keep the status-only message below when the body is not JSON.
    }
    throw new Error(detail || `Speech synthesis failed: ${res.status}`);
  }
  return res.blob();
}

export async function fetchTtsHealth(): Promise<TtsHealth> {
  const res = await apiFetch(`/v1/speech/tts/health`);
  if (!res.ok) return { available: false };
  return res.json();
}

export async function fetchSpeechHealth(): Promise<SpeechHealth> {
  if (isTauri()) {
    try {
      return await tauriInvoke<SpeechHealth>('speech_health');
    } catch {
      return { available: false };
    }
  }
  const res = await apiFetch(`/v1/speech/health`);
  if (!res.ok) return { available: false };
  return res.json();
}

export interface VoiceProviderOption {
  id: string;
  name: string;
  available: boolean;
}

export interface VoiceSettings {
  provider: string;
  voice_id: string;
  model_id: string;
  stability: number;
  similarity_boost: number;
  style: number;
  speed: number;
  has_api_key: boolean;
  masked_api_key: string;
  available_providers?: VoiceProviderOption[];
}

export interface VoiceSettingsUpdate {
  provider?: string;
  api_key?: string;
  voice_id?: string;
  model_id?: string;
  stability?: number;
  similarity_boost?: number;
  style?: number;
  speed?: number;
}

export interface ElevenLabsVoice {
  voice_id: string;
  name: string;
  category?: string;
  preview_url?: string;
  labels?: Record<string, string>;
}

export interface ElevenLabsModel {
  model_id: string;
  name: string;
  description?: string;
  can_do_text_to_speech?: boolean;
  can_be_finetuned?: boolean;
}

export interface ElevenLabsConnectionTestResult {
  valid: boolean;
  status: 'connected' | 'invalid_key' | 'quota_limited' | 'timeout' | 'error' | 'unconfigured';
  message: string;
  voices_count: number;
  models_count: number;
}

export async function fetchVoiceSettings(): Promise<VoiceSettings> {
  const res = await apiFetch(`/v1/speech/voice-settings`);
  if (!res.ok) {
    throw new Error(`Failed to fetch voice settings: ${res.status}`);
  }
  return res.json();
}

export async function updateVoiceSettings(updates: VoiceSettingsUpdate): Promise<VoiceSettings> {
  const res = await apiFetch(`/v1/speech/voice-settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || '';
    } catch {
      // Ignore non-json
    }
    throw new Error(detail || `Failed to update voice settings: ${res.status}`);
  }
  return res.json();
}

export interface PersonalizationPreferences {
  user_name: string;
  phone_number?: string;
  notification_phone?: string;
  presentation?: 'masculine' | 'feminine' | 'neutral' | string;
  voice_presentation?: 'masculine' | 'feminine' | 'neutral' | string;
  voice_gender?: 'masculine' | 'feminine' | 'neutral';
  persona: string;
  language: 'en' | 'ur' | 'hi' | 'auto';
  sound_enabled: boolean;
  sound_volume: number;
  sound_effects?: {
    enabled: boolean;
    volume: number;
  };
  onboarding_completed: boolean;
}

export interface VoiceOptionInfo {
  id: string;
  name: string;
  gender: string;
  lang: string;
}

export interface VoiceProviderCapability {
  id: string;
  name: string;
  free: boolean;
  requires_key: boolean;
  available: boolean;
  supported_languages: string[];
  cost_notice: string;
  voices?: VoiceOptionInfo[];
}

export async function fetchPersonalization(): Promise<PersonalizationPreferences> {
  const res = await apiFetch('/v1/personalization');
  if (!res.ok) {
    throw new Error(`Failed to fetch personalization: ${res.status}`);
  }
  return res.json();
}

export async function updatePersonalization(
  updates: Partial<PersonalizationPreferences>,
): Promise<PersonalizationPreferences> {
  const res = await apiFetch('/v1/personalization', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || '';
    } catch {
      // Ignore non-json
    }
    throw new Error(detail || `Failed to update personalization: ${res.status}`);
  }
  return res.json();
}

export interface VoicePreviewResult {
  status: string;
  text?: string;
  audioBlob?: Blob;
}

export async function previewVoiceUtterance(opts: {
  provider?: string;
  voice_id?: string;
  language?: string;
  voice_gender?: string;
  text?: string;
}): Promise<VoicePreviewResult> {
  const res = await apiFetch('/v1/speech/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || '';
    } catch {
      // Ignore non-json
    }
    throw new Error(detail || `Voice preview failed: ${res.status}`);
  }
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('audio')) {
    const audioBlob = await res.blob();
    return { status: 'server_audio', audioBlob };
  }
  return res.json();
}

export async function testElevenLabsConnection(apiKey?: string): Promise<ElevenLabsConnectionTestResult> {
  const res = await apiFetch(`/v1/speech/elevenlabs/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey || undefined }),
  });
  if (!res.ok) {
    throw new Error(`Connection test failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchElevenLabsVoices(): Promise<ElevenLabsVoice[]> {
  const res = await apiFetch(`/v1/speech/elevenlabs/voices`);
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || '';
    } catch {
      // Ignore non-json
    }
    throw new Error(detail || `Failed to fetch ElevenLabs voices: ${res.status}`);
  }
  const data = await res.json();
  return data.voices || [];
}

export async function fetchElevenLabsModels(): Promise<ElevenLabsModel[]> {
  const res = await apiFetch(`/v1/speech/elevenlabs/models`);
  if (!res.ok) {
    let detail = '';
    try {
      const err = await res.json();
      detail = err.detail || '';
    } catch {
      // Ignore non-json
    }
    throw new Error(detail || `Failed to fetch ElevenLabs models: ${res.status}`);
  }
  const data = await res.json();
  return data.models || [];
}

export async function previewElevenLabsVoice(opts: {
  voiceId?: string;
  modelId?: string;
  stability?: number;
  similarityBoost?: number;
  style?: number;
  speed?: number;
  text?: string;
  signal?: AbortSignal;
} = {}): Promise<Blob> {
  const res = await apiFetch(`/v1/speech/elevenlabs/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      voice_id: opts.voiceId,
      model_id: opts.modelId,
      stability: opts.stability,
      similarity_boost: opts.similarityBoost,
      style: opts.style,
      speed: opts.speed,
      text: opts.text,
    }),
    signal: opts.signal,
  });
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = body.detail || '';
    } catch {
      // Keep status code
    }
    throw new Error(detail || `Voice preview failed: ${res.status}`);
  }
  return res.blob();
}


// ---------------------------------------------------------------------------
// Agent Manager
// ---------------------------------------------------------------------------

export interface ManagedAgentConfig extends Record<string, unknown> {
  schedule_type?: string;
  schedule_value?: string | number;
}

export interface ManagedAgent {
  id: string;
  name: string;
  agent_type: string;
  config: ManagedAgentConfig;
  status: 'idle' | 'running' | 'paused' | 'error' | 'archived' | 'needs_attention' | 'budget_exceeded' | 'stalled';
  summary_memory: string;
  created_at: number;
  updated_at: number;
  // Runtime stats
  total_runs?: number;
  total_cost?: number;
  total_tokens?: number;
  input_tokens?: number;
  output_tokens?: number;
  last_run_at?: number | null;
  // Budget
  budget?: number;
  // Learning
  learning_enabled?: boolean;
  // Live progress
  current_activity?: string;
}

export interface AgentTask {
  id: string;
  agent_id: string;
  description: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  progress: Record<string, unknown>;
  findings: unknown[];
  created_at: number;
}

export interface ChannelBinding {
  id: string;
  agent_id: string;
  channel_type: string;
  config: Record<string, unknown>;
  session_id: string;
  routing_mode: string;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  source: 'built-in' | 'user';
  agent_type: string;
  [key: string]: unknown;
}

export interface PersistedToolCall {
  tool: string;
  arguments: string;
  result?: string;
  success?: boolean;
  latency?: number;
}

export interface AgentMessage {
  id: string;
  agent_id: string;
  direction: 'user_to_agent' | 'agent_to_user';
  content: string;
  mode: 'immediate' | 'queued';
  status: 'pending' | 'delivered' | 'responded';
  created_at: number;
  tool_calls?: PersistedToolCall[] | null;
}

export async function fetchManagedAgents(): Promise<ManagedAgent[]> {
  const res = await apiFetch(`/v1/managed-agents`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.agents || [];
}

export async function fetchManagedAgent(agentId: string): Promise<ManagedAgent> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function createManagedAgent(body: {
  name: string;
  agent_type?: string;
  template_id?: string;
  config?: Record<string, unknown>;
}): Promise<ManagedAgent> {
  const res = await apiFetch(`/v1/managed-agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function updateManagedAgent(
  agentId: string,
  body: Partial<{ name: string; agent_type: string; config: Record<string, unknown> }>,
): Promise<ManagedAgent> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function deleteManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function pauseManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/pause`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function resumeManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/resume`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function fetchAgentTasks(agentId: string): Promise<AgentTask[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/tasks`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.tasks || [];
}

export async function createAgentTask(agentId: string, description: string): Promise<AgentTask> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchAgentChannels(agentId: string): Promise<ChannelBinding[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/channels`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.bindings || [];
}

export async function bindAgentChannel(
  agentId: string,
  channelType: string,
  config?: Record<string, unknown>,
): Promise<ChannelBinding> {
  const res = await fetch(
    `${getBase()}/v1/managed-agents/${agentId}/channels`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel_type: channelType,
        config: config || {},
        routing_mode: 'dedicated',
      }),
    },
  );
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function unbindAgentChannel(
  agentId: string,
  bindingId: string,
): Promise<void> {
  const res = await fetch(
    `${getBase()}/v1/managed-agents/${agentId}/channels/${bindingId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

// -- SendBlue auto-setup helpers ------------------------------------------

export async function sendblueVerify(
  apiKeyId: string,
  apiSecretKey: string,
): Promise<{ valid: boolean; numbers: string[]; raw: unknown }> {
  const res = await apiFetch(`/v1/channels/sendblue/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key_id: apiKeyId, api_secret_key: apiSecretKey }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Verification failed: ${res.status}`);
  }
  return res.json();
}

export async function sendblueRegisterWebhook(
  apiKeyId: string,
  apiSecretKey: string,
  webhookUrl: string,
): Promise<{ registered: boolean; status: number }> {
  const res = await apiFetch(`/v1/channels/sendblue/register-webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key_id: apiKeyId,
      api_secret_key: apiSecretKey,
      webhook_url: webhookUrl,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Webhook registration failed: ${res.status}`);
  }
  return res.json();
}

export async function sendblueTest(
  apiKeyId: string,
  apiSecretKey: string,
  fromNumber: string,
  toNumber: string,
): Promise<{ sent: boolean; status: number }> {
  const res = await apiFetch(`/v1/channels/sendblue/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key_id: apiKeyId,
      api_secret_key: apiSecretKey,
      from_number: fromNumber,
      to_number: toNumber,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Test message failed: ${res.status}`);
  }
  return res.json();
}

export async function sendblueHealth(): Promise<{ channel_connected: boolean; bridge_wired: boolean; ready: boolean }> {
  const res = await apiFetch(`/v1/channels/sendblue/health`);
  if (!res.ok) return { channel_connected: false, bridge_wired: false, ready: false };
  return res.json();
}

export async function fetchTemplates(): Promise<AgentTemplate[]> {
  const res = await apiFetch(`/v1/templates`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.templates || [];
}

export async function runManagedAgent(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/run`, { method: 'POST' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Failed: ${res.status}`);
  }
}

export async function recoverManagedAgent(agentId: string): Promise<{ recovered: boolean; checkpoint: unknown }> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/recover`, { method: 'POST' });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchAgentState(agentId: string): Promise<{
  agent: ManagedAgent;
  tasks: AgentTask[];
  channels: ChannelBinding[];
  messages: AgentMessage[];
  checkpoint: unknown;
}> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/state`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export interface AgentToolCallStart {
  tool: string;
  arguments: string;
}

export interface AgentToolCallEnd {
  tool: string;
  success: boolean;
  latency: number;
  result?: string;
}

export async function sendAgentMessage(
  agentId: string,
  content: string,
  mode: 'immediate' | 'queued' = 'queued',
  callbacks?: {
    onProgress?: (label: string) => void;
    onContentDelta?: (delta: string, fullContent: string) => void;
    onToolCallStart?: (info: AgentToolCallStart) => void;
    onToolCallEnd?: (info: AgentToolCallEnd) => void;
    onDone?: (fullContent: string, usage?: Record<string, number>, telemetry?: Record<string, unknown>) => void;
  },
): Promise<AgentMessage> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, mode, stream: true }),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);

  // If streaming, consume the SSE response so the agent runs
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('text/event-stream') && res.body) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let fullContent = '';
    let buffer = '';
    let lastUsage: Record<string, number> | undefined;
    let lastTelemetry: Record<string, unknown> | undefined;
    let currentEvent: string | undefined;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
            continue;
          }
          if (!line.startsWith('data: ')) {
            if (line.trim() === '') currentEvent = undefined;
            continue;
          }
          const data = line.slice(6);
          if (data === '[DONE]') {
            currentEvent = undefined;
            continue;
          }
          const evName = currentEvent;
          currentEvent = undefined;

          if (evName === 'tool_call_start') {
            try {
              const parsed = JSON.parse(data);
              callbacks?.onToolCallStart?.({
                tool: parsed.tool,
                arguments: serializeToolCallArguments(parsed.arguments),
              });
            } catch {
              /* skip */
            }
            continue;
          }
          if (evName === 'tool_call_end') {
            try {
              const parsed = JSON.parse(data);
              callbacks?.onToolCallEnd?.({
                tool: parsed.tool,
                success: !!parsed.success,
                latency: typeof parsed.latency === 'number' ? parsed.latency : 0,
                result: parsed.result,
              });
            } catch {
              /* skip */
            }
            continue;
          }

          try {
            const chunk = JSON.parse(data);
            // Deep-research branch still uses tool_progress in a data chunk
            const toolProgress = chunk.choices?.[0]?.tool_progress;
            if (toolProgress) {
              callbacks?.onProgress?.(toolProgress);
            }
            const delta = chunk.choices?.[0]?.delta?.content || '';
            if (delta) {
              fullContent += delta;
              callbacks?.onContentDelta?.(delta, fullContent);
            }
            if (chunk.usage) lastUsage = chunk.usage;
            if (chunk.telemetry) lastTelemetry = chunk.telemetry;
          } catch {
            /* skip malformed chunks */
          }
        }
      }
    } catch { /* stream ended */ }

    callbacks?.onDone?.(fullContent, lastUsage, lastTelemetry);

    return {
      id: '',
      agent_id: agentId,
      direction: 'agent_to_user',
      content: fullContent,
      mode,
      status: 'delivered',
      created_at: Date.now() / 1000,
    };
  }

  return res.json();
}

/**
 * Ask the agent a question by triggering an ad-hoc run.
 *
 * Posts the question as an `immediate`, non-streamed message — the backend
 * stores it and spawns a real agent tick (`execute_tick`) that consumes it as
 * the run's input (tools, trace, and all), rather than a raw one-shot chat.
 * Returns immediately with the stored user message; progress is observed via
 * the `/v1/agents/events` WebSocket and the resulting trace.
 */
export async function askAgent(agentId: string, content: string): Promise<AgentMessage> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, mode: 'immediate', stream: false }),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

export async function fetchAgentMessages(agentId: string): Promise<AgentMessage[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/messages`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.messages || [];
}

export async function fetchErrorAgents(): Promise<ManagedAgent[]> {
  const res = await apiFetch(`/v1/agents/errors`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.agents || [];
}

// ---------------------------------------------------------------------------
// Agent Learning + Traces
// ---------------------------------------------------------------------------

export interface LearningLogEntry {
  id: string;
  agent_id: string;
  event_type: string;
  description: string;
  data: Record<string, unknown>;
  created_at: number;
}

export interface AgentTrace {
  id: string;
  outcome: string;
  duration: number;
  started_at: number;
  steps: number;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  source: 'tool' | 'channel';
  requires_credentials: boolean;
  credential_keys: string[];
  configured: boolean;
}

export async function fetchAvailableTools(): Promise<ToolInfo[]> {
  const res = await apiFetch(`/v1/tools`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.tools || [];
}

export async function saveToolCredentials(
  toolName: string,
  credentials: Record<string, string>,
): Promise<void> {
  const res = await apiFetch(`/v1/tools/${toolName}/credentials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials),
  });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function fetchToolCredentialStatus(
  toolName: string,
): Promise<Record<string, boolean>> {
  const res = await apiFetch(`/v1/tools/${toolName}/credentials/status`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return await res.json();
}

export async function deleteToolCredential(
  toolName: string,
  keyName: string,
): Promise<void> {
  const res = await apiFetch(
    `/v1/tools/${encodeURIComponent(toolName)}/credentials/${encodeURIComponent(keyName)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export interface AgentTraceDetail {
  id: string;
  agent: string;
  outcome: string;
  duration: number;
  started_at: number;
  steps: Array<{
    step_type: string;
    input: unknown;
    output: string;
    duration: number;
    metadata: Record<string, unknown>;
  }>;
}

export async function fetchLearningLog(agentId: string): Promise<LearningLogEntry[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/learning`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.learning_log || [];
}

export async function triggerLearning(agentId: string): Promise<void> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/learning/run`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function fetchAgentTraces(agentId: string, limit = 20): Promise<AgentTrace[]> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/traces?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.traces || [];
}

export async function fetchAgentTrace(agentId: string, traceId: string): Promise<AgentTraceDetail> {
  const res = await apiFetch(`/v1/managed-agents/${agentId}/traces/${traceId}`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Leaderboard savings submission (Supabase)
// ---------------------------------------------------------------------------

export interface SavingsSubmission {
  anon_id: string;
  display_name: string;
  email: string;
  total_calls: number;
  total_tokens: number;
  dollar_savings: number;
  energy_wh_saved: number;
  flops_saved: number;
  token_counting_version?: number;
}

export async function submitSavings(data: SavingsSubmission): Promise<boolean> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return false;
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/savings_entries?on_conflict=anon_id`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          Prefer: 'resolution=merge-duplicates',
        },
        body: JSON.stringify(data),
      },
    );
    return res.ok || res.status === 201 || res.status === 200;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

export interface MemorySearchResult {
  content: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface MemoryStats {
  entries: number;
  backend: string;
  [key: string]: unknown;
}

export interface MemoryConfig {
  backend: string;
  // Set by the server when the native `openjarvis_rust` extension is missing,
  // so the UI can show the real cause instead of a healthy-looking config.
  available?: boolean;
  detail?: string | null;
  context_from_memory: boolean;
  context_top_k: number;
  context_min_score: number;
  context_max_tokens: number;
}

/**
 * Extract the server's `detail` message from a failed JSON response so the UI
 * surfaces the real cause (e.g. "openjarvis_rust extension is not installed")
 * instead of a blanket fallback string (#502).
 */
async function memoryErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    if (data && typeof data.detail === 'string' && data.detail) return data.detail;
  } catch {
    // Non-JSON body — fall through to the generic message below.
  }
  return fallback;
}

export async function getMemoryStats(): Promise<MemoryStats> {
  let res: Response;
  try {
    res = await apiFetch(`/v1/memory/stats`);
  } catch {
    throw new Error('Could not reach the OpenJarvis API. Check the server status and API URL, then retry.');
  }
  if (!res.ok) {
    const detail = await memoryErrorDetail(res, 'Memory status request failed');
    throw new Error(`${detail} (HTTP ${res.status})`);
  }
  return res.json();
}

export async function searchMemory(query: string, topK: number = 5): Promise<MemorySearchResult[]> {
  const res = await apiFetch(`/v1/memory/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) throw new Error('Failed to search memory');
  const data = await res.json();
  return data.results;
}

export async function storeMemory(content: string, metadata?: Record<string, unknown>): Promise<void> {
  const res = await apiFetch(`/v1/memory/store`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, metadata }),
  });
  if (!res.ok) throw new Error(await memoryErrorDetail(res, 'Failed to store memory'));
}

export async function indexMemoryPath(path: string): Promise<{ chunks_indexed: number; note?: string }> {
  const res = await apiFetch(`/v1/memory/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw new Error(await memoryErrorDetail(res, 'Failed to index path'));
  return res.json();
}

export async function getMemoryConfig(): Promise<MemoryConfig> {
  const res = await apiFetch(`/v1/memory/config`);
  if (!res.ok) throw new Error('Failed to fetch memory config');
  return res.json();
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

export interface PendingApproval {
  id: string;
  action_type: string;
  description: string;
  payload: Record<string, unknown>;
  permission_key: string;
  tier: 'trivial' | 'low' | 'medium' | 'high';
  status: string;
  created_at: string;
  expires_at: string;
}

export async function fetchPendingApprovals(): Promise<PendingApproval[]> {
  const res = await apiFetch(`/v1/approvals/pending`);
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
  const data = await res.json();
  return data.actions || [];
}

export async function approveAction(actionId: string): Promise<void> {
  const res = await apiFetch(`/v1/approvals/${actionId}/approve`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

export async function denyAction(actionId: string): Promise<void> {
  const res = await apiFetch(`/v1/approvals/${actionId}/deny`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed: ${res.status}`);
}

// ---------------------------------------------------------------------------
// Inference source (desktop only)
// ---------------------------------------------------------------------------

export type InferenceSource = {
  kind: 'ollama' | 'custom';
  model?: string;
  host?: string;
  engine?: string;
};

export async function getInferenceSource(): Promise<InferenceSource> {
  if (isTauri()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      return await invoke<InferenceSource>('get_inference_source');
    } catch (e: any) {
      throw new Error(e?.message ?? e ?? 'Failed to read inference source');
    }
  }
  return { kind: 'ollama' };
}

export async function setInferenceSource(
  src: InferenceSource & { apiKey?: string },
  options: { pending?: boolean } = {},
): Promise<void> {
  if (!isTauri()) throw new Error('Inference source is configurable in the desktop app only.');
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke<void>('set_inference_source', {
      kind: src.kind,
      model: src.model ?? null,
      host: src.host ?? null,
      engine: src.engine ?? null,
      apiKey: src.apiKey ?? null,
      pending: options.pending ?? null,
    });
  } catch (e: any) {
    // Surface the backend's actionable error strings (e.g. "A server URL is
    // required…", "Could not store the API key…") as proper Error instances.
    throw new Error(e?.message ?? e ?? 'Failed to save inference source');
  }
}

/** Stage a first-run choice; Rust confirms it only after backend readiness. */
export const stageInferenceSource = (
  src: InferenceSource & { apiKey?: string },
): Promise<void> => setInferenceSource(src, { pending: true });

// ---------------------------------------------------------------------------
// Persistent Task Runner APIs
// ---------------------------------------------------------------------------

export async function fetchTasks(status?: string, limit: number = 50): Promise<TaskRecord[]> {
  const params = new URLSearchParams();
  if (status && status !== 'all') params.set('status', status);
  if (limit) params.set('limit', limit.toString());
  const queryString = params.toString() ? `?${params.toString()}` : '';
  const res = await apiFetch(`/api/tasks${queryString}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch tasks: ${res.status}`);
  }
  const data = await res.json();
  return data.tasks || [];
}

export async function fetchTask(taskId: string): Promise<TaskRecord> {
  const res = await apiFetch(`/api/tasks/${taskId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch task: ${res.status}`);
  }
  const data = await res.json();
  return data.task;
}

export async function createTask(
  prompt: string,
  steps?: any[],
  metadata?: Record<string, any>,
  autoRun: boolean = true,
): Promise<TaskRecord> {
  const res = await apiFetch(`/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, steps, metadata, auto_run: autoRun }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create task: ${res.status}`);
  }
  const data = await res.json();
  return data.task;
}

export async function pauseTask(taskId: string): Promise<void> {
  const res = await apiFetch(`/api/tasks/${taskId}/pause`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to pause task: ${res.status}`);
  }
}

export async function resumeTask(taskId: string): Promise<TaskRecord> {
  const res = await apiFetch(`/api/tasks/${taskId}/resume`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to resume task: ${res.status}`);
  }
  const data = await res.json();
  return data.task;
}

export async function cancelTask(taskId: string): Promise<void> {
  const res = await apiFetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to cancel task: ${res.status}`);
  }
}

export interface ApproveTaskStepPayload {
  step_id?: string;
  safety_code?: string;
  token?: string;
  resolution?: string;
  confirm_duplicate_risk?: boolean;
  tool_args?: Record<string, any>;
}

export async function approveTaskStep(
  taskId: string,
  payload: ApproveTaskStepPayload = {},
): Promise<void> {
  const res = await apiFetch(`/api/tasks/${taskId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to approve step: ${res.status}`);
  }
}

export interface SubmitStepInputPayload {
  step_id?: string;
  tool_args: Record<string, any>;
}

export async function submitStepInput(
  taskId: string,
  payload: SubmitStepInputPayload,
): Promise<{
  status: string;
  task_id?: string;
  step_id?: string;
  requires_approval?: boolean;
  requires_code?: boolean;
  resumed?: boolean;
  decision?: Record<string, any>;
}> {
  const res = await apiFetch(`/api/tasks/${taskId}/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to submit step input: ${res.status}`);
  }
  return res.json();
}

export interface RejectTaskStepPayload {
  step_id?: string;
  reason?: string;
}

export async function rejectTaskStep(
  taskId: string,
  payload: RejectTaskStepPayload = {},
): Promise<void> {
  const res = await apiFetch(`/api/tasks/${taskId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to reject step: ${res.status}`);
  }
}

// ---------------------------------------------------------------------------
// Memory & Skills Control Center API Endpoints
// ---------------------------------------------------------------------------

export interface FetchMemoryFactsParams {
  q?: string;
  category?: string;
  project?: string;
  trust?: string;
  verified?: boolean;
  source_type?: string;
  limit?: number;
  offset?: number;
}

export async function fetchMemoryFacts(
  params: FetchMemoryFactsParams = {},
): Promise<MemoryFactsResponse> {
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.category && params.category !== 'all') query.set('category', params.category);
  if (params.project && params.project !== 'all') query.set('project', params.project);
  if (params.trust && params.trust !== 'all') query.set('trust', params.trust);
  if (params.verified !== undefined) query.set('verified', String(params.verified));
  if (params.source_type && params.source_type !== 'all') query.set('source_type', params.source_type);
  if (params.limit) query.set('limit', String(params.limit));
  if (params.offset) query.set('offset', String(params.offset));

  const qs = query.toString();
  const path = `/api/memory/facts${qs ? `?${qs}` : ''}`;
  const res = await apiFetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch memory facts: ${res.status}`);
  }
  return res.json();
}

export async function fetchMemoryFact(memoryId: string): Promise<MemoryFact> {
  const res = await apiFetch(`/api/memory/facts/${memoryId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch memory '${memoryId}': ${res.status}`);
  }
  const data = await res.json();
  return data.memory;
}

export interface CreateMemoryFactPayload {
  text: string;
  category?: string;
  project?: string;
  source?: string;
  source_type?: string;
  trust?: 'trusted' | 'auto' | 'untrusted';
  verified?: boolean;
  metadata?: Record<string, any>;
}

export async function createMemoryFact(
  payload: CreateMemoryFactPayload,
): Promise<MemoryFact> {
  const res = await apiFetch('/api/memory/facts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create memory fact: ${res.status}`);
  }
  const data = await res.json();
  return data.memory;
}

export interface UpdateMemoryFactPayload {
  text?: string;
  category?: string;
  project?: string;
  trust?: string;
  verified?: boolean;
  source_type?: string;
  metadata?: Record<string, any>;
}

export async function updateMemoryFact(
  memoryId: string,
  payload: UpdateMemoryFactPayload,
): Promise<MemoryFact> {
  const res = await apiFetch(`/api/memory/facts/${memoryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update memory '${memoryId}': ${res.status}`);
  }
  const data = await res.json();
  return data.memory;
}

export async function deleteMemoryFact(memoryId: string): Promise<void> {
  const res = await apiFetch(`/api/memory/facts/${memoryId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete memory '${memoryId}': ${res.status}`);
  }
}

export interface FetchLearnedSkillsParams {
  status?: string;
  q?: string;
}

export async function fetchLearnedSkills(
  params: FetchLearnedSkillsParams = {},
): Promise<LearnedSkillsResponse> {
  const query = new URLSearchParams();
  if (params.status && params.status !== 'all') query.set('status', params.status);
  if (params.q) query.set('q', params.q);

  const qs = query.toString();
  const path = `/api/skills/learned${qs ? `?${qs}` : ''}`;
  const res = await apiFetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch learned skills: ${res.status}`);
  }
  return res.json();
}

export async function fetchLearnedSkillDetail(skillName: string): Promise<LearnedSkill> {
  const res = await apiFetch(`/api/skills/learned/${skillName}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch skill '${skillName}': ${res.status}`);
  }
  const data = await res.json();
  return data.skill;
}

export async function approveLearnedSkill(skillName: string): Promise<LearnedSkill> {
  const res = await apiFetch(`/api/skills/learned/${skillName}/approve`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to approve skill '${skillName}': ${res.status}`);
  }
  const data = await res.json();
  return data.skill;
}

export async function rejectLearnedSkill(
  skillName: string,
  reason?: string,
): Promise<LearnedSkill> {
  const res = await apiFetch(`/api/skills/learned/${skillName}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to reject skill '${skillName}': ${res.status}`);
  }
  const data = await res.json();
  return data.skill;
}

export async function disableLearnedSkill(
  skillName: string,
  reason?: string,
): Promise<LearnedSkill> {
  const res = await apiFetch(`/api/skills/learned/${skillName}/disable`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to disable skill '${skillName}': ${res.status}`);
  }
  const data = await res.json();
  return data.skill;
}

export async function enableLearnedSkill(skillName: string): Promise<LearnedSkill> {
  const res = await apiFetch(`/api/skills/learned/${skillName}/enable`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to enable skill '${skillName}': ${res.status}`);
  }
  const data = await res.json();
  return data.skill;
}

export async function validateCompositeSkill(
  payload: CreateCompositeSkillRequest,
): Promise<ValidateCompositeSkillResponse> {
  const res = await apiFetch('/api/skills/composite/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Validation request failed: ${res.status}`);
  }
  return res.json();
}

export async function createCompositeSkill(
  payload: CreateCompositeSkillRequest,
): Promise<CreateCompositeSkillResponse> {
  const res = await apiFetch('/api/skills/composite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create composite skill: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Memory Maintenance & Consolidation Endpoints
// ---------------------------------------------------------------------------

export async function scanMemoryMaintenance(project?: string): Promise<MaintenanceScanResponse> {
  const query = new URLSearchParams();
  if (project && project !== 'all') query.set('project', project);
  const qs = query.toString();
  const res = await apiFetch(`/api/memory/maintenance/scan${qs ? `?${qs}` : ''}`, {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Maintenance scan failed: ${res.status}`);
  }
  return res.json();
}

export interface FetchMaintenanceSuggestionsParams {
  project?: string;
  issue_type?: string;
  status?: string;
}

export async function fetchMaintenanceSuggestions(
  params: FetchMaintenanceSuggestionsParams = {},
): Promise<MaintenanceScanResponse> {
  const query = new URLSearchParams();
  if (params.project && params.project !== 'all') query.set('project', params.project);
  if (params.issue_type && params.issue_type !== 'all') query.set('issue_type', params.issue_type);
  if (params.status && params.status !== 'all') query.set('status', params.status);

  const qs = query.toString();
  const res = await apiFetch(`/api/memory/maintenance/suggestions${qs ? `?${qs}` : ''}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch maintenance suggestions: ${res.status}`);
  }
  return res.json();
}

export async function approveMaintenanceSuggestion(
  suggestionId: string,
  payload?: { custom_text?: string; target_trust?: string },
): Promise<any> {
  const res = await apiFetch(`/api/memory/maintenance/suggestions/${suggestionId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to approve suggestion: ${res.status}`);
  }
  return res.json();
}

export async function dismissMaintenanceSuggestion(
  suggestionId: string,
  payload?: { reason?: string },
): Promise<any> {
  const res = await apiFetch(`/api/memory/maintenance/suggestions/${suggestionId}/dismiss`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to dismiss suggestion: ${res.status}`);
  }
  return res.json();
}
export interface MCPServerInfo {
  name: string;
  transport: 'http' | 'stdio';
  url?: string;
  command?: string;
  args?: string[];
  token?: string;
  enabled: boolean;
  include_tools?: string[];
  exclude_tools?: string[];
}

export interface MCPTestResult {
  name: string;
  connected: boolean;
  latency_ms?: number;
  discovered_tools_count: number;
  tools: string[];
  error?: string;
}

export async function fetchMCPServers(): Promise<MCPServerInfo[]> {
  const res = await apiFetch('/api/mcp/servers');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch MCP servers: ${res.status}`);
  }
  return res.json();
}

export async function validateMCPServer(
  server: Partial<MCPServerInfo>,
): Promise<{ valid: boolean; server?: Record<string, any>; errors: string[] }> {
  const res = await apiFetch('/api/mcp/servers/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(server),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Validation failed: ${res.status}`);
  }
  return res.json();
}

export async function testMCPServer(
  server: Partial<MCPServerInfo>,
): Promise<MCPTestResult> {
  const res = await apiFetch('/api/mcp/servers/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(server),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Connection test failed: ${res.status}`);
  }
  return res.json();
}

export async function saveMCPServer(
  server: Partial<MCPServerInfo>,
): Promise<MCPServerInfo> {
  const res = await apiFetch('/api/mcp/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(server),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to save MCP server: ${res.status}`);
  }
  return res.json();
}

export async function deleteMCPServer(serverName: string): Promise<{ name: string; status: string }> {
  const res = await apiFetch(`/api/mcp/servers/${encodeURIComponent(serverName)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete MCP server: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Advanced Runtime & Resource Limiting
// ---------------------------------------------------------------------------

export interface ProviderRuntimeStats {
  provider: string;
  is_local: boolean;
  circuit_state: 'closed' | 'open' | 'half_open';
  active_concurrency: number;
  max_concurrency: number;
  requests_per_minute_limit: number;
  tokens_per_minute_limit: number;
  current_rpm_tokens: number;
  current_tpm_tokens: number;
  consecutive_failures: number;
  circuit_cooldown_remaining_seconds: number;
}

export interface RuntimeLimitsResponse {
  status: string;
  providers: Record<string, ProviderRuntimeStats>;
}

export async function getRuntimeLimits(): Promise<RuntimeLimitsResponse> {
  const res = await apiFetch('/v1/runtime/limits');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to get runtime limits: ${res.status}`);
  }
  return res.json();
}

export async function updateRuntimeLimits(data: {
  provider: string;
  requests_per_minute?: number;
  tokens_per_minute?: number;
  max_concurrency?: number;
  timeout_seconds?: number;
  max_retries?: number;
}): Promise<any> {
  const res = await apiFetch('/v1/runtime/limits', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update runtime limits: ${res.status}`);
  }
  return res.json();
}

export async function resetRuntimeLimits(): Promise<any> {
  const res = await apiFetch('/v1/runtime/limits/reset', { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to reset runtime limits: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Cloud Usage & Cost Ledger
// ---------------------------------------------------------------------------

export interface UsageSummary {
  period: { start_time: number; end_time: number };
  pricing_version: string;
  total_requests: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cached_tokens: number;
  total_reasoning_tokens: number;
  total_characters: number;
  total_estimated_cost_usd: number;
  total_billed_cost_usd: number;
  local_requests: number;
  local_tokens: number;
  unknown_cost_requests: number;
  by_provider: Array<{
    provider: string;
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    characters: number;
    estimated_cost_usd: number;
    billed_cost_usd: number;
    is_local: boolean;
  }>;
  by_model: Array<{
    provider: string;
    model: string;
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    characters: number;
    estimated_cost_usd: number;
    billed_cost_usd: number;
  }>;
}

export interface UsageRecord {
  request_id: string;
  task_id: string;
  agent_id: string;
  purpose: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_prompt_tokens: number;
  reasoning_tokens: number;
  characters: number;
  duration_seconds: number;
  cost_type: 'estimated' | 'provider_billed' | 'local_zero' | 'unknown';
  estimated_cost_usd: number;
  billed_cost_usd: number;
  pricing_version: string;
  status: string;
  retry_count: number;
  metadata: Record<string, any>;
  created_at: number;
}

export async function getUsageSummary(hours?: number): Promise<UsageSummary> {
  const qs = hours ? `?hours=${encodeURIComponent(hours)}` : '';
  const res = await apiFetch(`/v1/usage/summary${qs}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch usage summary: ${res.status}`);
  }
  return res.json();
}

export async function getUsageLedger(
  limit: number = 50,
  offset: number = 0,
  provider?: string,
  model?: string,
): Promise<{ records: UsageRecord[]; count: number }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (provider) params.set('provider', provider);
  if (model) params.set('model', model);
  const res = await apiFetch(`/v1/usage/ledger?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch usage ledger: ${res.status}`);
  }
  return res.json();
}

export async function exportUsageCsv(): Promise<string> {
  const res = await apiFetch('/v1/usage/export');
  if (!res.ok) {
    throw new Error(`Failed to export usage CSV: ${res.status}`);
  }
  return res.text();
}

export async function reconcileUsageCost(
  requestId: string,
  providerBilledCost: number,
  reconciliationSource: string = 'manual_reconciliation',
): Promise<any> {
  const res = await apiFetch('/v1/usage/reconcile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      request_id: requestId,
      provider_billed_cost: providerBilledCost,
      reconciliation_source: reconciliationSource,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to reconcile usage cost: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Local Model Wizard & Hardware Discovery
// ---------------------------------------------------------------------------

export interface HardwareScanResult {
  platform_os: string;
  architecture: string;
  cpu_brand: string;
  cpu_cores: number;
  total_ram_gb: number;
  free_ram_gb: number;
  total_disk_gb: number;
  free_disk_gb: number;
  disk_path: string;
  gpu_vendor: string;
  gpu_name: string;
  total_vram_gb: number;
  free_vram_gb: number;
  cuda_compute_capability: string;
  ollama_installed: boolean;
  ollama_running: boolean;
  installed_models: Array<{ name: string; size?: number }>;
  scan_timestamp: number;
}

export interface ModelRecommendation {
  model_id: string;
  name: string;
  parameter_size: string;
  estimated_download_gb: number;
  estimated_ram_gb: number;
  category: string;
  fit_status: 'recommended' | 'supported' | 'marginal' | 'insufficient_memory';
  overall_score: number;
  tool_calling_support: 'verified' | 'standard' | 'experimental' | 'unsupported';
  reasoning: string;
  context_length: number;
  license_type: string;
}

export interface BenchmarkScenarioResult {
  scenario_id: string;
  name: string;
  passed: boolean;
  latency_ms: number;
  output: string;
  error?: string;
}

export interface LocalBenchmarkResult {
  model_id: string;
  scenarios_tested: number;
  scenarios_passed: number;
  pass_rate_pct: number;
  avg_latency_ms: number;
  tool_validity_pct: number;
  results: BenchmarkScenarioResult[];
  completed_at: number;
}

export async function getHardwareScan(): Promise<HardwareScanResult> {
  const res = await apiFetch('/v1/wizard/hardware');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Hardware scan failed: ${res.status}`);
  }
  return res.json();
}

export async function getModelRecommendations(): Promise<{
  hardware: HardwareScanResult;
  recommendations: ModelRecommendation[];
}> {
  const res = await apiFetch('/v1/wizard/recommendations');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch model recommendations: ${res.status}`);
  }
  return res.json();
}

export async function runModelBenchmark(modelId: string = 'qwen3:8b'): Promise<LocalBenchmarkResult> {
  const res = await apiFetch('/v1/wizard/benchmark', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Benchmark failed: ${res.status}`);
  }
  return res.json();
}

export async function installLocalModel(modelId: string, confirm: boolean): Promise<any> {
  const res = await apiFetch('/v1/wizard/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, confirm }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Model install failed: ${res.status}`);
  }
  return res.json();
}

export async function getCurrentModelPreferences(): Promise<{
  current: {
    provider: string;
    model: string;
    previous_provider?: string;
    previous_model?: string;
    updated_at?: number;
  };
}> {
  const res = await apiFetch('/v1/wizard/current');
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to get model preferences: ${res.status}`);
  }
  return res.json();
}

export async function configureModelPreferences(
  provider: string,
  model: string,
): Promise<{ status: string; current: any }> {
  const res = await apiFetch('/v1/wizard/configure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to configure model preferences: ${res.status}`);
  }
  return res.json();
}

export async function rollbackModelPreferences(): Promise<{ status: string; current: any }> {
  const res = await apiFetch('/v1/wizard/rollback', {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to rollback model preferences: ${res.status}`);
  }
  return res.json();
}
