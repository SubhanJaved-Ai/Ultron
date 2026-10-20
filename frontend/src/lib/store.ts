import { create } from 'zustand';
import type {
  Conversation,
  ChatMessage,
  LiveEnergyMetrics,
  LogEntry,
  ModelInfo,
  MessageTelemetry,
  ResearchSearchTrace,
  ResearchSource,
  SavingsData,
  ServerInfo,
  StreamState,
  ToolCallInfo,
  TokenUsage,
} from '../types';
import type { ManagedAgent } from './api';
import { isEmbedOnlyModel } from './model-capabilities';
import { serializeToolCallArguments } from './tool-call';

export interface CachedConnector {
  connector_id: string;
  display_name: string;
  connected: boolean;
  chunks: number;
  auth_type: string;
}

export interface AgentEvent {
  type: string;
  timestamp: number;
  data: Record<string, unknown>;
}

// ── localStorage persistence ──────────────────────────────────────────

const CONVERSATIONS_KEY = 'openjarvis-conversations';
const SETTINGS_KEY = 'openjarvis-settings';
const OPTIN_KEY = 'openjarvis-optin';
const OPTIN_NAME_KEY = 'openjarvis-display-name';
const OPTIN_EMAIL_KEY = 'openjarvis-email';
const OPTIN_ANONID_KEY = 'openjarvis-anon-id';
const OPTIN_SEEN_KEY = 'openjarvis-optin-seen';

interface ConversationStore {
  version: 1;
  conversations: Record<string, Conversation>;
  activeId: string | null;
}

let _cachedStore: ConversationStore | null = null;
let _saveTimeout: ReturnType<typeof setTimeout> | null = null;

export function flushPendingConversationSave(): void {
  if (_saveTimeout) {
    clearTimeout(_saveTimeout);
    _saveTimeout = null;
  }
  if (_cachedStore) {
    try {
      localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(_cachedStore));
    } catch {
      // Best-effort disk write
    }
  }
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function loadConversations(): ConversationStore {
  if (_cachedStore) return _cachedStore;
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    if (!raw) {
      _cachedStore = { version: 1, conversations: {}, activeId: null };
      return _cachedStore;
    }
    const parsed = JSON.parse(raw);
    if (parsed.version === 1) {
      let repaired = false;
      for (const conversation of Object.values(parsed.conversations ?? {}) as Conversation[]) {
        for (const message of conversation.messages ?? []) {
          for (const toolCall of message.toolCalls ?? []) {
            const argumentsText = serializeToolCallArguments(toolCall.arguments);
            if (argumentsText !== toolCall.arguments) {
              toolCall.arguments = argumentsText;
              repaired = true;
            }
          }
        }
      }
      if (repaired) {
        try {
          localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(parsed));
        } catch {
          // Keep the repaired conversations usable in memory when storage is
          // read-only or full. A failed best-effort writeback must not make
          // otherwise readable conversation history disappear from the UI.
        }
      }
      _cachedStore = parsed;
      return parsed;
    }
    _cachedStore = { version: 1, conversations: {}, activeId: null };
    return _cachedStore;
  } catch {
    _cachedStore = { version: 1, conversations: {}, activeId: null };
    return _cachedStore;
  }
}

function saveConversations(store: ConversationStore, immediate = true): void {
  _cachedStore = store;
  if (immediate) {
    if (_saveTimeout) {
      clearTimeout(_saveTimeout);
      _saveTimeout = null;
    }
    try {
      localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(store));
    } catch {
      // Best-effort disk write
    }
  } else {
    if (!_saveTimeout) {
      _saveTimeout = setTimeout(() => {
        _saveTimeout = null;
        flushPendingConversationSave();
      }, 3000);
    }
  }
}

export type ThemeMode = 'light' | 'dark' | 'system';

interface Settings {
  theme: ThemeMode;
  apiUrl: string;
  // Local server API key (OPENJARVIS_API_KEY). Sent as a Bearer token on
  // /v1 + /api requests so a key-protected `jarvis serve` doesn't 401 the
  // frontend (#266). Empty = no auth header (keyless local default).
  apiKey: string;
  fontSize: 'small' | 'default' | 'large';
  defaultModel: string;
  defaultAgent: string;
  temperature: number;
  maxTokens: number;
  speechEnabled: boolean;
  voiceOutputEnabled: boolean;
  voiceAutoplay: boolean;
  // Personalization & Cyber Experience
  userName: string;
  voicePresentation?: 'masculine' | 'feminine' | 'neutral' | string;
  voiceGender?: 'masculine' | 'feminine' | 'neutral';
  persona: string;
  language: 'en' | 'ur' | 'hi' | 'auto';
  notificationPhone: string;
  soundEnabled: boolean;
  soundVolume: number;
  onboardingCompleted: boolean;
}

function loadSettings(): Settings {
  const defaults: Settings = {
    theme: 'system',
    apiUrl: '',
    apiKey: '',
    fontSize: 'default',
    defaultModel: '',
    defaultAgent: '',
    temperature: 0.7,
    maxTokens: 4096,
    speechEnabled: false,
    voiceOutputEnabled: false,
    voiceAutoplay: false,
    userName: 'Sir',
    voicePresentation: 'neutral',
    voiceGender: 'masculine',
    persona: 'jarvis',
    language: 'en',
    notificationPhone: '',
    soundEnabled: true,
    soundVolume: 0.6,
    onboardingCompleted: false,
  };
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return defaults;
    return { ...defaults, ...JSON.parse(raw) };
  } catch {
    return defaults;
  }
}

function saveSettings(settings: Settings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

// ── Store ─────────────────────────────────────────────────────────────

const INITIAL_STREAM: StreamState = {
  conversationId: null,
  isStreaming: false,
  phase: '',
  elapsedMs: 0,
  activeToolCalls: [],
  content: '',
};

interface AppState {
  // Conversations
  conversations: Conversation[];
  activeId: string | null;
  messages: ChatMessage[];
  streamState: StreamState;

  // Models & server
  models: ModelInfo[];
  modelsLoading: boolean;
  selectedModel: string;
  serverInfo: ServerInfo | null;
  savings: SavingsData | null;

  // Settings
  settings: Settings;

  // Command palette
  commandPaletteOpen: boolean;

  // Sidebar
  sidebarOpen: boolean;

  // System panel
  systemPanelOpen: boolean;

  // Opt-in sharing
  optInEnabled: boolean;
  optInDisplayName: string;
  optInEmail: string;
  optInAnonId: string;
  optInModalSeen: boolean;
  optInModalOpen: boolean;

  // Actions: conversations
  loadConversations: () => void;
  importOverlayConversation: () => Promise<void>;
  createConversation: (model?: string) => string;
  selectConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  loadMessages: (conversationId: string | null) => void;
  addMessage: (conversationId: string, message: ChatMessage) => void;
  updateLastAssistant: (
    conversationId: string,
    content: string,
    toolCalls?: ToolCallInfo[],
    usage?: TokenUsage,
    telemetry?: MessageTelemetry,
    audio?: { url: string },
    researchTraces?: ResearchSearchTrace[],
    researchSources?: ResearchSource[],
    immediate?: boolean,
  ) => void;
  setStreamState: (state: Partial<StreamState>) => void;
  resetStream: () => void;

  // Deep Research toggle
  deepResearch: boolean;
  setDeepResearch: (on: boolean) => void;

  // Actions: models & server
  setModels: (models: ModelInfo[]) => void;
  setModelsLoading: (loading: boolean) => void;
  setSelectedModel: (model: string) => void;
  setServerInfo: (info: ServerInfo | null) => void;
  setSavings: (data: SavingsData | null) => void;
  incrementSavings: (usage: TokenUsage) => void;

  // Live GPU metrics — streamed from /api/research system_metrics events.
  // When non-null, the System panel renders this instead of polled values
  // so Power (W) and Energy (kJ) update in real time during a research run.
  liveEnergy: LiveEnergyMetrics | null;
  setLiveEnergy: (data: LiveEnergyMetrics | null) => void;

  // Actions: settings & personalization
  updateSettings: (partial: Partial<Settings>) => void;
  setUserName: (userName: string) => void;
  setVoicePresentation: (voicePresentation: 'masculine' | 'feminine' | 'neutral') => void;
  setPersona: (persona: string) => void;
  setLanguage: (language: 'en' | 'ur' | 'auto') => void;
  setSoundSettings: (enabled: boolean, volume?: number) => void;
  setOnboardingCompleted: (completed: boolean) => void;

  // Actions: UI
  setCommandPaletteOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSystemPanel: () => void;
  setSystemPanelOpen: (open: boolean) => void;

  // Data sources (cached between visits to avoid empty-state flicker)
  cachedConnectors: CachedConnector[] | null;
  setCachedConnectors: (list: CachedConnector[] | null) => void;

  // Agents
  managedAgents: ManagedAgent[];
  managedAgentsLoading: boolean;
  selectedAgentId: string | null;

  // Actions: agents
  setManagedAgents: (agents: ManagedAgent[]) => void;
  setManagedAgentsLoading: (loading: boolean) => void;
  setSelectedAgentId: (id: string | null) => void;

  // Agent events (live stream)
  agentEvents: AgentEvent[];
  addAgentEvent: (event: AgentEvent) => void;
  clearAgentEvents: () => void;

  // Actions: opt-in sharing
  setOptIn: (enabled: boolean, displayName: string, email: string) => void;
  setOptInModalOpen: (open: boolean) => void;
  markOptInModalSeen: () => void;

  // Logs
  logEntries: LogEntry[];
  addLogEntry: (entry: LogEntry) => void;
  clearLogs: () => void;

  // Model loading
  modelLoading: boolean;
  setModelLoading: (loading: boolean) => void;
}

export const useAppStore = create<AppState>((set, get) => {
  const initial = loadConversations();
  const convList = Object.values(initial.conversations).sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );

  return {
    conversations: convList,
    activeId: initial.activeId,
    messages:
      initial.activeId && initial.conversations[initial.activeId]
        ? initial.conversations[initial.activeId].messages
        : [],
    streamState: INITIAL_STREAM,

    models: [],
    modelsLoading: true,
    selectedModel: '',
    serverInfo: null,
    savings: null,

    settings: loadSettings(),

    commandPaletteOpen: false,
    sidebarOpen: true,
    systemPanelOpen: true,

    optInEnabled: localStorage.getItem(OPTIN_KEY) === 'true',
    optInDisplayName: localStorage.getItem(OPTIN_NAME_KEY) || '',
    optInEmail: localStorage.getItem(OPTIN_EMAIL_KEY) || '',
    optInAnonId: localStorage.getItem(OPTIN_ANONID_KEY) || crypto.randomUUID(),
    optInModalSeen: localStorage.getItem(OPTIN_SEEN_KEY) === 'true',
    optInModalOpen: false,

    // ── Conversations ───────────────────────────────────────────────

    loadConversations: () => {
      const store = loadConversations();
      set({
        conversations: Object.values(store.conversations).sort(
          (a, b) => b.updatedAt - a.updatedAt,
        ),
        activeId: store.activeId,
      });
    },

    importOverlayConversation: async () => {
      try {
        const { invoke } = await import('@tauri-apps/api/core');
        const raw = await invoke<string>('get_overlay_conversation');
        if (!raw || raw === '[]') return;
        const overlay = JSON.parse(raw);
        if (!overlay.id || !overlay.messages?.length) return;
        const store = loadConversations();
        const existing = store.conversations[overlay.id];
        // Only update if the overlay has newer/more messages
        if (existing && existing.messages.length >= overlay.messages.length) return;
        // Track first use of overlay for this conversation
        if (!existing) {
          import('../lib/analytics').then(({ track }) => {
            track('feature_used', { feature_name: 'overlay' });
          });
        }
        store.conversations[overlay.id] = {
          id: overlay.id,
          title: overlay.title || 'Overlay chat',
          createdAt: overlay.createdAt || Date.now(),
          updatedAt: overlay.updatedAt || Date.now(),
          model: overlay.model || 'default',
          messages: overlay.messages,
        };
        saveConversations(store);
        set({
          conversations: Object.values(store.conversations).sort(
            (a, b) => b.updatedAt - a.updatedAt,
          ),
        });
      } catch {
        // Overlay command unavailable (non-Tauri or no overlay data)
      }
    },

    createConversation: (model?: string) => {
      const store = loadConversations();
      const conv: Conversation = {
        id: generateId(),
        title: 'New chat',
        createdAt: Date.now(),
        updatedAt: Date.now(),
        model: model || get().selectedModel || 'default',
        messages: [],
      };
      store.conversations[conv.id] = conv;
      store.activeId = conv.id;
      saveConversations(store);
      set({
        conversations: Object.values(store.conversations).sort(
          (a, b) => b.updatedAt - a.updatedAt,
        ),
        activeId: conv.id,
        messages: [],
      });
      return conv.id;
    },

    selectConversation: (id: string) => {
      const store = loadConversations();
      store.activeId = id;
      saveConversations(store);
      const conv = store.conversations[id];
      set({
        activeId: id,
        messages: conv ? conv.messages : [],
      });
    },

    deleteConversation: (id: string) => {
      const streamState = get().streamState;
      if (streamState.isStreaming && streamState.conversationId === id) return;

      const store = loadConversations();
      delete store.conversations[id];
      if (store.activeId === id) {
        const remaining = Object.keys(store.conversations);
        store.activeId = remaining.length > 0 ? remaining[0] : null;
      }
      saveConversations(store);
      const convList = Object.values(store.conversations).sort(
        (a, b) => b.updatedAt - a.updatedAt,
      );
      const activeConv = store.activeId
        ? store.conversations[store.activeId]
        : null;
      set({
        conversations: convList,
        activeId: store.activeId,
        messages: activeConv ? activeConv.messages : [],
      });
    },

    loadMessages: (conversationId: string | null) => {
      if (!conversationId) {
        set({ messages: [] });
        return;
      }
      const store = loadConversations();
      const conv = store.conversations[conversationId];
      set({ messages: conv ? conv.messages : [] });
    },

    addMessage: (conversationId: string, message: ChatMessage) => {
      const store = loadConversations();
      const conv = store.conversations[conversationId];
      if (!conv) return;
      conv.messages.push(message);
      conv.updatedAt = Date.now();
      if (message.role === 'user' && conv.title === 'New chat') {
        conv.title =
          message.content.slice(0, 50) +
          (message.content.length > 50 ? '...' : '');
      }
      saveConversations(store);
      const conversations = Object.values(store.conversations).sort(
        (a, b) => b.updatedAt - a.updatedAt,
      );
      if (get().activeId === conversationId) {
        set({ messages: [...conv.messages], conversations });
      } else {
        set({ conversations });
      }
    },

    updateLastAssistant: (
      conversationId: string,
      content: string,
      toolCalls?: ToolCallInfo[],
      usage?: TokenUsage,
      telemetry?: MessageTelemetry,
      audio?: { url: string },
      researchTraces?: ResearchSearchTrace[],
      researchSources?: ResearchSource[],
      immediate = false,
    ) => {
      const store = loadConversations();
      const conv = store.conversations[conversationId];
      if (!conv) return;
      const lastMsg = conv.messages[conv.messages.length - 1];
      if (lastMsg && lastMsg.role === 'assistant') {
        lastMsg.content = content;
        if (toolCalls) lastMsg.toolCalls = toolCalls;
        if (usage) lastMsg.usage = usage;
        if (telemetry) lastMsg.telemetry = telemetry;
        if (audio) lastMsg.audio = audio;
        if (researchTraces) lastMsg.researchTraces = researchTraces;
        if (researchSources) lastMsg.researchSources = researchSources;
        conv.updatedAt = Date.now();
        saveConversations(store, immediate);
        if (get().activeId === conversationId) {
          set({ messages: [...conv.messages] });
        }
      }
    },

    setStreamState: (partial: Partial<StreamState>) => {
      set((s) => ({ streamState: { ...s.streamState, ...partial } }));
    },

    resetStream: () => {
      set({ streamState: INITIAL_STREAM });
    },

    // ── Deep Research ─────────────────────────────────────────────
    deepResearch: false,
    setDeepResearch: (on: boolean) => set({ deepResearch: on }),

    // ── Models & server ────────────────────────────────────────────

    setModels: (models: ModelInfo[]) =>
      set((state) => {
        // Ollama returns embed-only models (e.g. nomic-embed-text) in the
        // same list as chat models. Auto-picking models[0] selected the
        // embedder and every chat failed with HTTP 400 "does not support
        // chat". Prefer a real chat model for selection / fallback.
        const chatModels = models.filter((m) => !isEmbedOnlyModel(m.id));
        const preferred =
          (state.settings.defaultModel &&
            chatModels.some((m) => m.id === state.settings.defaultModel) &&
            state.settings.defaultModel) ||
          chatModels[0]?.id ||
          models.find((m) => !isEmbedOnlyModel(m.id))?.id ||
          '';

        const currentIsBad =
          !!state.selectedModel && isEmbedOnlyModel(state.selectedModel);
        const currentMissing =
          !!state.selectedModel &&
          !models.some((m) => m.id === state.selectedModel);

        if (!state.selectedModel || currentIsBad || currentMissing) {
          // Prefer a real chat model. If none exist, clear a bad/missing
          // selection rather than keeping an embed-only id that 400s on chat.
          return {
            models,
            selectedModel: preferred,
          };
        }
        return { models };
      }),
    setModelsLoading: (loading: boolean) => set({ modelsLoading: loading }),
    setSelectedModel: (model: string) => set({ selectedModel: model }),
    setServerInfo: (info: ServerInfo | null) =>
      set((state) => {
        if (!info) return { serverInfo: null };
        const modelStr =
          typeof info.model === 'string' && info.model.trim() && info.model.trim() !== 'jarvis-v2'
            ? info.model.trim()
            : '';
        const engineStr =
          typeof info.engine === 'string' ? info.engine : '';
        const agentStr =
          typeof info.agent === 'string' ? info.agent : '';
        const sanitizedInfo: ServerInfo = {
          ...info,
          model: modelStr,
          engine: engineStr,
          agent: agentStr,
        };

        const shouldSync =
          !!modelStr &&
          (!state.selectedModel ||
            (info.engine === 'gemini' &&
              (state.selectedModel === 'gemini-2.5-pro' ||
                state.selectedModel === 'gemini-2.5-flash')));

        return {
          serverInfo: sanitizedInfo,
          ...(shouldSync ? { selectedModel: modelStr } : {}),
        };
      }),
    setSavings: (data: SavingsData | null) => set({ savings: data }),
    incrementSavings: (usage: TokenUsage) => {
      const cur = get().savings;
      const prompt = usage.prompt_tokens ?? 0;
      const completion = usage.completion_tokens ?? 0;
      const total = usage.total_tokens ?? prompt + completion;
      set({
        savings: {
          total_calls: (cur?.total_calls ?? 0) + 1,
          total_prompt_tokens: (cur?.total_prompt_tokens ?? 0) + prompt,
          total_completion_tokens: (cur?.total_completion_tokens ?? 0) + completion,
          total_tokens: (cur?.total_tokens ?? 0) + total,
          local_cost: cur?.local_cost ?? 0,
          per_provider: cur?.per_provider ?? [],
          token_counting_version: cur?.token_counting_version,
        },
      });
    },

    liveEnergy: null,
    setLiveEnergy: (data: LiveEnergyMetrics | null) => set({ liveEnergy: data }),

    cachedConnectors: null,
    setCachedConnectors: (list) => set({ cachedConnectors: list }),

    // ── Settings ───────────────────────────────────────────────────

    updateSettings: (partial: Partial<Settings>) => {
      const updated = { ...get().settings, ...partial };
      saveSettings(updated);
      set({ settings: updated });
    },
    setUserName: (userName: string) => get().updateSettings({ userName }),
    setVoicePresentation: (voicePresentation: 'masculine' | 'feminine' | 'neutral') =>
      get().updateSettings({ voicePresentation }),
    setPersona: (persona: string) => get().updateSettings({ persona }),
    setLanguage: (language: 'en' | 'ur' | 'auto') => get().updateSettings({ language }),
    setSoundSettings: (enabled: boolean, volume?: number) => {
      const curVol = get().settings.soundVolume;
      get().updateSettings({
        soundEnabled: enabled,
        soundVolume: volume !== undefined ? Math.max(0, Math.min(1, volume)) : curVol,
      });
    },
    setOnboardingCompleted: (completed: boolean) =>
      get().updateSettings({ onboardingCompleted: completed }),

    // ── UI ──────────────────────────────────────────────────────────

    setCommandPaletteOpen: (open: boolean) => set({ commandPaletteOpen: open }),
    toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
    setSidebarOpen: (open: boolean) => set({ sidebarOpen: open }),
    toggleSystemPanel: () => set((s) => ({ systemPanelOpen: !s.systemPanelOpen })),
    setSystemPanelOpen: (open: boolean) => set({ systemPanelOpen: open }),

    // ── Agents ─────────────────────────────────────────────────────

    managedAgents: [],
    managedAgentsLoading: false,
    selectedAgentId: null,

    setManagedAgents: (agents) => set({ managedAgents: agents }),
    setManagedAgentsLoading: (loading) => set({ managedAgentsLoading: loading }),
    setSelectedAgentId: (id) => set({ selectedAgentId: id }),

    agentEvents: [],
    addAgentEvent: (event) => set((s) => ({
      agentEvents: [...s.agentEvents.slice(-99), event],
    })),
    clearAgentEvents: () => set({ agentEvents: [] }),

    // ── Logs ────────────────────────────────────────────────────────
    logEntries: [],
    addLogEntry: (entry) => set((s) => ({
      logEntries: [...s.logEntries.slice(-499), entry],
    })),
    clearLogs: () => set({ logEntries: [] }),

    // ── Model loading ───────────────────────────────────────────────
    modelLoading: false,
    setModelLoading: (loading) => set({ modelLoading: loading }),

    // ── Opt-in sharing ──────────────────────────────────────────────

    setOptIn: (enabled: boolean, displayName: string, email: string) => {
      const anonId = get().optInAnonId;
      localStorage.setItem(OPTIN_KEY, String(enabled));
      localStorage.setItem(OPTIN_NAME_KEY, displayName);
      localStorage.setItem(OPTIN_EMAIL_KEY, email);
      localStorage.setItem(OPTIN_ANONID_KEY, anonId);
      set({ optInEnabled: enabled, optInDisplayName: displayName, optInEmail: email });
    },
    setOptInModalOpen: (open: boolean) => set({ optInModalOpen: open }),
    markOptInModalSeen: () => {
      localStorage.setItem(OPTIN_SEEN_KEY, 'true');
      set({ optInModalSeen: true });
    },
  };
});

export { generateId };
