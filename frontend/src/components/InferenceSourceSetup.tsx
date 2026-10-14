import { useReducer, useState, type FormEvent } from 'react';
import { ArrowLeft, ChevronDown, Cpu, Download, Loader2, Server, ShieldCheck, Sparkles } from 'lucide-react';
import { sanitizeDiagnosticText } from '../lib/sanitize';
import {
  resetInferenceSource,
  stageInferenceSource,
  startBackend,
  type InferenceSource,
} from '../lib/api';

export type InferenceSetupStep = 'choose' | 'ollama' | 'custom' | 'gemini';
export type InferenceSetupAction =
  | 'choose_ollama'
  | 'choose_custom'
  | 'choose_gemini'
  | 'back';
export type InferenceSourceSubmission = InferenceSource & { apiKey?: string };

const GEMINI_DEFAULT_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/openai/';
const GEMINI_DEFAULT_MODEL = 'gemini-3.8-flash';

/** Pure navigation state: merely inspecting a source can never start setup. */
export function inferenceSetupReducer(
  state: InferenceSetupStep,
  action: InferenceSetupAction,
): InferenceSetupStep {
  switch (action) {
    case 'choose_ollama':
      return 'ollama';
    case 'choose_gemini':
      return 'gemini';
    case 'choose_custom':
      return 'custom';
    case 'back':
      return 'choose';
    default:
      return state;
  }
}

/**
 * Persist first, start second. Dependency injection keeps the consent boundary
 * directly testable without a Tauri runtime.
 */
export async function persistAndStartInferenceSource(
  source: InferenceSourceSubmission,
  persist: (value: InferenceSourceSubmission) => Promise<void> = stageInferenceSource,
  start: () => Promise<void> = startBackend,
  rollback: () => Promise<void> = resetInferenceSource,
): Promise<void> {
  let persisted = false;
  try {
    await persist(source);
    persisted = true;
    await start();
  } catch (error) {
    if (persisted) {
      await rollback().catch(() => {});
    }
    throw error;
  }
}

function SetupFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 flex items-center justify-center" style={{ background: 'var(--color-bg)' }}>
      <div className="w-full max-w-lg px-6">
        <div className="text-center mb-8">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
          >
            <Cpu size={32} />
          </div>
          <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--color-text)' }}>
            Choose your inference source
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            Nothing is installed, started, or downloaded until you confirm a choice.
          </p>
        </div>
        <div
          className="p-6 rounded-2xl"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

export function InferenceSourceChooser({
  onChoose,
}: {
  onChoose: (source: 'ollama' | 'gemini' | 'custom') => void;
}) {
  return (
    <SetupFrame>
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => onChoose('ollama')}
          className="flex items-start gap-4 p-4 rounded-xl text-left transition-all cursor-pointer hover:border-(--color-accent)"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <Cpu size={22} className="shrink-0 mt-0.5" style={{ color: 'var(--color-accent)' }} />
          <span>
            <span className="block text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
              Local Ollama
            </span>
            <span className="block text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
              Run models on this computer. Requires a separate confirmation before Ollama starts or a model downloads.
            </span>
          </span>
        </button>

        <button
          type="button"
          onClick={() => onChoose('gemini')}
          className="flex items-start gap-4 p-4 rounded-xl text-left transition-all cursor-pointer hover:border-(--color-accent)"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <Sparkles size={22} className="shrink-0 mt-0.5" style={{ color: 'var(--color-accent)' }} />
          <span>
            <span className="block text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
              Google Gemini
            </span>
            <span className="block text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
              Connect directly via your Google AI Studio API key. Cloud inference, no local GPU or model download required.
            </span>
          </span>
        </button>

        <button
          type="button"
          onClick={() => onChoose('custom')}
          className="flex items-start gap-4 p-4 rounded-xl text-left transition-all cursor-pointer hover:border-(--color-accent)"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          <Server size={22} className="shrink-0 mt-0.5" style={{ color: 'var(--color-accent)' }} />
          <span>
            <span className="block text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
              OpenAI-compatible server
            </span>
            <span className="block text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
              Connect to LM Studio, vLLM, SGLang, llama.cpp, MLX, or another compatible endpoint. Ollama stays off.
            </span>
          </span>
        </button>
      </div>
    </SetupFrame>
  );
}

function BackButton({ onClick, label = 'Back', disabled = false }: { onClick: () => void; label?: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 text-sm mb-5 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
      style={{ color: 'var(--color-text-secondary)' }}
    >
      <ArrowLeft size={15} />
      {label}
    </button>
  );
}

export function InferenceRecoveryButton({
  recovering,
  onChange,
}: {
  recovering: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={recovering}
      className="w-full mt-4 py-2.5 px-4 rounded-xl text-sm font-medium cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
      style={{
        color: 'var(--color-text-secondary)',
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
      }}
    >
      {recovering ? 'Stopping setup...' : 'Change inference source'}
    </button>
  );
}

export function OllamaConsent({
  onBack,
  onConfirm,
  busy = false,
  error = '',
}: {
  onBack: () => void;
  onConfirm: () => void;
  busy?: boolean;
  error?: string;
}) {
  return (
    <SetupFrame>
      <BackButton onClick={onBack} disabled={busy} />
      <div className="flex items-start gap-3 mb-5">
        <Download size={22} className="shrink-0 mt-0.5" style={{ color: 'var(--color-accent)' }} />
        <div>
          <h2 className="text-base font-semibold mb-1" style={{ color: 'var(--color-text)' }}>
            Allow local model setup?
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
            OpenJarvis will start Ollama and may download one model selected for this computer. Model downloads can use several gigabytes of disk space and network data.
          </p>
        </div>
      </div>
      <div
        className="flex items-start gap-2.5 px-3.5 py-3 rounded-lg text-xs mb-5"
        style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-text-secondary)' }}
      >
        <ShieldCheck size={16} className="shrink-0" style={{ color: 'var(--color-accent)' }} />
        Going back leaves Ollama stopped and does not save this choice.
      </div>
      {error && <SetupError message={error} />}
      <button
        type="button"
        onClick={onConfirm}
        disabled={busy}
        className="w-full py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-70"
        style={{ background: 'var(--color-accent)', color: 'white' }}
      >
        {busy && <Loader2 size={16} className="animate-spin" />}
        {busy ? 'Starting local setup...' : 'Use Ollama and continue'}
      </button>
    </SetupFrame>
  );
}

function SetupError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="px-3.5 py-3 rounded-lg text-sm mb-4"
      style={{
        background: 'color-mix(in srgb, var(--color-error) 10%, transparent)',
        border: '1px solid color-mix(in srgb, var(--color-error) 20%, transparent)',
        color: 'var(--color-error)',
      }}
    >
      {message}
    </div>
  );
}

export function GeminiSetup({
  onCancel,
  onConfirm,
  busy = false,
  error = '',
}: {
  onCancel: () => void;
  onConfirm: (source: InferenceSourceSubmission) => void;
  busy?: boolean;
  error?: string;
}) {
  const [host, setHost] = useState(GEMINI_DEFAULT_ENDPOINT);
  const [model, setModel] = useState(GEMINI_DEFAULT_MODEL);
  const [apiKey, setApiKey] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onConfirm({
      kind: 'custom',
      host: host.trim(),
      model: model.trim(),
      engine: 'gemini',
      apiKey: apiKey.trim() || undefined,
    });
  };

  const fieldStyle = {
    background: 'var(--color-surface)',
    color: 'var(--color-text)',
    border: '1px solid var(--color-border)',
  };

  return (
    <SetupFrame>
      <BackButton onClick={onCancel} label="Cancel" disabled={busy} />
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold mb-1" style={{ color: 'var(--color-text)' }}>
            Connect Google Gemini
          </h2>
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Cloud inference powered by Google Gemini. Your API key will be saved securely in Windows Credential Manager.
          </p>
        </div>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          API key
          <input
            aria-label="API key"
            type="password"
            required
            placeholder="AIzaSy..."
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            autoComplete="off"
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          />
        </label>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Model ID
          <input
            aria-label="Model ID"
            type="text"
            required
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder={GEMINI_DEFAULT_MODEL}
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          />
        </label>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Server URL
          <input
            aria-label="Server URL"
            type="url"
            required
            value={host}
            onChange={(event) => setHost(event.target.value)}
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          />
        </label>
        {error && <SetupError message={error} />}
        <button
          type="submit"
          disabled={busy || !host.trim() || !model.trim() || !apiKey.trim()}
          className="w-full py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--color-accent)', color: 'white' }}
        >
          {busy && <Loader2 size={16} className="animate-spin" />}
          {busy ? 'Connecting...' : 'Save and connect'}
        </button>
      </form>
    </SetupFrame>
  );
}

export function CustomEndpointSetup({
  onCancel,
  onConfirm,
  busy = false,
  error = '',
}: {
  onCancel: () => void;
  onConfirm: (source: InferenceSourceSubmission) => void;
  busy?: boolean;
  error?: string;
}) {
  const [host, setHost] = useState('http://localhost:1234/v1');
  const [model, setModel] = useState('');
  const [engine, setEngine] = useState('lmstudio');
  const [apiKey, setApiKey] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onConfirm({
      kind: 'custom',
      host: host.trim(),
      model: model.trim(),
      engine,
      apiKey: apiKey.trim() || undefined,
    });
  };

  const fieldStyle = {
    background: 'var(--color-surface)',
    color: 'var(--color-text)',
    border: '1px solid var(--color-border)',
  };

  return (
    <SetupFrame>
      <BackButton onClick={onCancel} label="Cancel" disabled={busy} />
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold mb-1" style={{ color: 'var(--color-text)' }}>
            Connect your server
          </h2>
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            OpenJarvis will connect only after you submit this form. Ollama will not start or download models.
          </p>
        </div>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Server type
          <select
            aria-label="Server type"
            value={engine}
            onChange={(event) => {
              const nextEngine = event.target.value;
              setEngine(nextEngine);
              if (nextEngine === 'gemini') {
                if (host === 'http://localhost:1234/v1' || !host.trim()) {
                  setHost(GEMINI_DEFAULT_ENDPOINT);
                }
                if (!model.trim() || model === 'qwen2.5-7b-instruct') {
                  setModel(GEMINI_DEFAULT_MODEL);
                }
              } else if (engine === 'gemini') {
                if (host === GEMINI_DEFAULT_ENDPOINT) {
                  setHost('http://localhost:1234/v1');
                }
                if (model === GEMINI_DEFAULT_MODEL) {
                  setModel('');
                }
              }
            }}
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          >
            <option value="gemini">Google Gemini</option>
            <option value="lmstudio">LM Studio</option>
            <option value="vllm">vLLM</option>
            <option value="sglang">SGLang</option>
            <option value="llamacpp">llama.cpp</option>
            <option value="mlx">MLX</option>
          </select>
        </label>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Model ID
          <input
            aria-label="Model ID"
            type="text"
            required
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder={engine === 'gemini' ? GEMINI_DEFAULT_MODEL : 'qwen2.5-7b-instruct'}
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          />
        </label>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Server URL
          <input
            aria-label="Server URL"
            type="url"
            required
            value={host}
            onChange={(event) => setHost(event.target.value)}
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          />
        </label>
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          API key (optional)
          <input
            aria-label="API key"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            autoComplete="off"
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none"
            style={fieldStyle}
          />
        </label>
        {error && <SetupError message={error} />}
        <button
          type="submit"
          disabled={busy || !host.trim() || !model.trim()}
          className="w-full py-3 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--color-accent)', color: 'white' }}
        >
          {busy && <Loader2 size={16} className="animate-spin" />}
          {busy ? 'Connecting...' : 'Save and connect'}
        </button>
      </form>
    </SetupFrame>
  );
}

export function InferenceSourceSetup({ onStarted }: { onStarted: () => void }) {
  const [step, dispatch] = useReducer(inferenceSetupReducer, 'choose');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const begin = async (source: InferenceSourceSubmission) => {
    setBusy(true);
    setError('');
    try {
      await persistAndStartInferenceSource(source);
      onStarted();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  if (step === 'ollama') {
    return (
      <OllamaConsent
        busy={busy}
        error={error}
        onBack={() => dispatch('back')}
        onConfirm={() => void begin({ kind: 'ollama' })}
      />
    );
  }
  if (step === 'gemini') {
    return (
      <GeminiSetup
        busy={busy}
        error={error}
        onCancel={() => dispatch('back')}
        onConfirm={(source) => void begin(source)}
      />
    );
  }
  if (step === 'custom') {
    return (
      <CustomEndpointSetup
        busy={busy}
        error={error}
        onCancel={() => dispatch('back')}
        onConfirm={(source) => void begin(source)}
      />
    );
  }
  return (
    <InferenceSourceChooser
      onChoose={(source) => {
        if (source === 'ollama') dispatch('choose_ollama');
        else if (source === 'gemini') dispatch('choose_gemini');
        else dispatch('choose_custom');
      }}
    />
  );
}

export function CredentialRecoveryCard({
  provider,
  keyName,
  savedModel,
  savedHost,
  error,
  onSubmit,
  onResetSource,
  busy = false,
}: {
  provider?: string | null;
  keyName?: string | null;
  savedModel?: string | null;
  savedHost?: string | null;
  error?: string | null;
  onSubmit: (keyName: string, keyValue: string) => Promise<void>;
  onResetSource: () => void;
  busy?: boolean;
}) {
  const [apiKey, setApiKey] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const sanitizedDetails = sanitizeDiagnosticText(error);

  const displayProvider =
    provider === 'gemini'
      ? 'Google Gemini'
      : provider
        ? provider.charAt(0).toUpperCase() + provider.slice(1)
        : 'Inference Provider';

  const resolvedKeyName =
    keyName ||
    (provider === 'gemini' ? 'GEMINI_API_KEY' : `${(provider || 'CUSTOM').toUpperCase()}_API_KEY`);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!apiKey.trim()) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      await onSubmit(resolvedKeyName, apiKey.trim());
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const fieldStyle = {
    background: 'var(--color-surface)',
    color: 'var(--color-text)',
    border: '1px solid var(--color-border)',
  };

  return (
    <div
      className="p-6 rounded-2xl w-full"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
      }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
        >
          <Sparkles size={20} />
        </div>
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            Update {displayProvider} API Key
          </h2>
          {savedModel && (
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              Configured model: <span className="font-mono">{savedModel}</span>
            </p>
          )}
        </div>
      </div>

      <div
        role="alert"
        className="px-4 py-3 rounded-xl text-xs mb-4 leading-relaxed flex flex-col gap-2"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div style={{ color: 'var(--color-text)' }}>
          {error ||
            'An API key is required or your existing key was rejected. Please enter a valid API key to reconnect.'}
        </div>
        <div
          className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium"
          style={{
            background: 'var(--color-accent-subtle)',
            color: 'var(--color-text)',
          }}
        >
          <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
            Recommended Action:{' '}
          </span>
          Generate a valid API key from your provider and enter it below to reconnect.
        </div>
        {sanitizedDetails && (
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setShowDiagnostics(!showDiagnostics)}
              className="text-[11px] flex items-center gap-1 cursor-pointer font-medium hover:underline"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              <span>{showDiagnostics ? 'Hide diagnostic details' : 'Show diagnostic details'}</span>
              <ChevronDown
                size={12}
                className={`transition-transform duration-200 ${showDiagnostics ? 'rotate-180' : ''}`}
              />
            </button>
            {showDiagnostics && (
              <pre
                className="mt-1.5 p-2 rounded-lg font-mono text-[10px] leading-relaxed overflow-x-auto whitespace-pre-wrap select-all max-h-36"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {sanitizedDetails}
              </pre>
            )}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Replacement API key
          <input
            aria-label="Replacement API key"
            type="password"
            required
            autoComplete="off"
            placeholder={provider === 'gemini' ? 'AIzaSy...' : 'sk-...'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            disabled={submitting || busy}
            className="block w-full mt-1.5 px-3 py-2 rounded-lg text-sm outline-none font-mono"
            style={fieldStyle}
          />
        </label>

        {submitError && <SetupError message={submitError} />}

        <div className="flex flex-col gap-2 pt-1">
          <button
            type="submit"
            disabled={submitting || busy || !apiKey.trim()}
            className="w-full py-2.5 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--color-accent)', color: 'white' }}
          >
            {(submitting || busy) && <Loader2 size={16} className="animate-spin" />}
            {submitting || busy ? 'Connecting...' : 'Update Key & Connect'}
          </button>

          <button
            type="button"
            onClick={onResetSource}
            disabled={submitting || busy}
            className="w-full py-2 px-4 rounded-xl text-xs font-medium cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
            style={{
              color: 'var(--color-text-secondary)',
              background: 'transparent',
            }}
          >
            Change inference source
          </button>
        </div>
      </form>
    </div>
  );
}

export function ProviderBusyCard({
  provider,
  error,
  onRetry,
  onResetSource,
  busy = false,
}: {
  provider?: string | null;
  error?: string | null;
  onRetry: () => Promise<void>;
  onResetSource: () => void;
  busy?: boolean;
}) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState('');
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const sanitizedDetails = sanitizeDiagnosticText(error);

  const displayProvider =
    provider === 'gemini'
      ? 'Google Gemini'
      : provider
        ? provider.charAt(0).toUpperCase() + provider.slice(1)
        : 'Inference Provider';

  const handleRetry = async () => {
    setRetrying(true);
    setRetryError('');
    try {
      await onRetry();
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : String(err));
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      className="p-6 rounded-2xl w-full"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
      }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
        >
          <Server size={20} />
        </div>
        <div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            {displayProvider} Temporarily Unavailable
          </h2>
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Your configuration has been safely preserved.
          </p>
        </div>
      </div>

      <div
        role="alert"
        className="px-3.5 py-3 rounded-xl text-xs mb-4 leading-relaxed flex flex-col gap-2"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text)',
        }}
      >
        <div>
          {error ||
            'The provider is experiencing temporary rate limiting or maintenance (HTTP 429/503). You can retry without re-entering your settings.'}
        </div>
        <div
          className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium"
          style={{
            background: 'var(--color-accent-subtle)',
            color: 'var(--color-text)',
          }}
        >
          <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
            Recommended Action:{' '}
          </span>
          Wait a moment for provider capacity to recover, then retry connecting.
        </div>
        {sanitizedDetails && (
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setShowDiagnostics(!showDiagnostics)}
              className="text-[11px] flex items-center gap-1 cursor-pointer font-medium hover:underline"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              <span>{showDiagnostics ? 'Hide diagnostic details' : 'Show diagnostic details'}</span>
              <ChevronDown
                size={12}
                className={`transition-transform duration-200 ${showDiagnostics ? 'rotate-180' : ''}`}
              />
            </button>
            {showDiagnostics && (
              <pre
                className="mt-1.5 p-2 rounded-lg font-mono text-[10px] leading-relaxed overflow-x-auto whitespace-pre-wrap select-all max-h-36"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {sanitizedDetails}
              </pre>
            )}
          </div>
        )}
      </div>

      {retryError && <SetupError message={retryError} />}

      <div className="flex flex-col gap-2 pt-1">
        <button
          type="button"
          onClick={handleRetry}
          disabled={retrying || busy}
          className="w-full py-2.5 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--color-accent)', color: 'white' }}
        >
          {(retrying || busy) && <Loader2 size={16} className="animate-spin" />}
          {retrying || busy ? 'Retrying...' : 'Retry Connection'}
        </button>

        <button
          type="button"
          onClick={onResetSource}
          disabled={retrying || busy}
          className="w-full py-2 px-4 rounded-xl text-xs font-medium cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
          style={{
            color: 'var(--color-text-secondary)',
            background: 'transparent',
          }}
        >
          Change inference source
        </button>
      </div>
    </div>
  );
}
