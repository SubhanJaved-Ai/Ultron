import { useState, useEffect, useCallback, useRef } from 'react';
import { Loader2, CheckCircle2, AlertCircle, Cpu, Server, Database } from 'lucide-react';
import {
  getSetupStatus,
  fetchModels,
  fetchRecommendedModel,
  resetInferenceSource,
  startBackend,
  updateInferenceCredential,
  type SetupStatus,
} from '../lib/api';
import { useAppStore } from '../lib/store';
import { isEmbedOnlyModel } from '../lib/model-capabilities';
import {
  CredentialRecoveryCard,
  InferenceRecoveryButton,
  InferenceSourceSetup,
  ProviderBusyCard,
} from './InferenceSourceSetup';
import { SetupStatusCard } from './SetupStatusCard';

const STEPS = [
  { key: 'ollama_ready', label: 'Inference Engine', icon: Cpu, detail: 'Starting Ollama...' },
  { key: 'model_ready', label: 'AI Model', icon: Database, detail: 'Loading model...' },
  { key: 'server_ready', label: 'API Server', icon: Server, detail: 'Starting server...' },
] as const;

type StepKey = (typeof STEPS)[number]['key'];

export function StepRow({
  icon: Icon,
  label,
  done,
  active,
  detail,
  hasError,
}: {
  icon: typeof Cpu;
  label: string;
  done: boolean;
  active: boolean;
  detail: string;
  hasError?: boolean;
}) {
  return (
    <div
      className="flex items-center gap-4 px-5 py-4 rounded-xl transition-all"
      style={{
        background: done
          ? 'var(--color-accent-subtle)'
          : active
            ? 'var(--color-surface)'
            : 'transparent',
        border: active ? '1px solid var(--color-border)' : '1px solid transparent',
      }}
    >
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
        style={{
          background: done
            ? 'var(--color-accent)'
            : hasError && active
              ? 'color-mix(in srgb, var(--color-warning, #f59e0b) 15%, transparent)'
              : 'var(--color-bg-tertiary)',
          color: done
            ? 'white'
            : hasError && active
              ? 'var(--color-warning, #f59e0b)'
              : 'var(--color-text-tertiary)',
        }}
      >
        <Icon size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
          {label}
        </div>
        <div className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)', maxWidth: '280px' }}>
          {done ? 'Ready' : active ? (hasError ? 'Stopped (see details below)' : detail) : 'Waiting...'}
        </div>
      </div>
      <div className="shrink-0">
        {done ? (
          <CheckCircle2 size={18} style={{ color: 'var(--color-accent)' }} />
        ) : active && hasError ? (
          <AlertCircle size={18} style={{ color: 'var(--color-warning, #f59e0b)' }} />
        ) : active ? (
          <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
        ) : (
          <div
            className="w-4 h-4 rounded-full"
            style={{ border: '2px solid var(--color-border)' }}
          />
        )}
      </div>
    </div>
  );
}

export function SetupScreen({ onReady }: { onReady: () => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [statusChecked, setStatusChecked] = useState(false);
  const [setupInitiated, setSetupInitiated] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [recoveryError, setRecoveryError] = useState('');
  const handedOffRef = useRef(false);
  const poll = useCallback(async () => {
    const s = await getSetupStatus();
    if (s) setStatus(s);
    setStatusChecked(true);
    if (s?.phase === 'ready' && !handedOffRef.current) {
      handedOffRef.current = true;
      // Pre-select a model BEFORE handing off so the chat is usable on
      // first send. Without this, the main app's post-mount fetch can
      // lose a race to a fast first message and Ollama 400s.
      try {
        const [models, rec] = await Promise.all([
          fetchModels().catch(() => []),
          fetchRecommendedModel().catch(() => ({ model: '', reason: '' })),
        ]);
        const store = useAppStore.getState();
        const hadSelection = !!store.selectedModel;
        store.setModels(models);
        store.setModelsLoading(false);
        const chatModels = models.filter((m) => !isEmbedOnlyModel(m.id));
        const recommended = rec.model && chatModels.some((m) => m.id === rec.model)
          ? rec.model
          : chatModels[0]?.id || '';
        if (recommended && !hadSelection) {
          store.setSelectedModel(recommended);
        }
      } catch {
        // Non-fatal: store.setModels auto-selects on later fetch, and
        // the InputArea guards the empty-model case with a toast.
      }
      setTimeout(() => onReady(), 600);
    }
  }, [onReady]);

  const changeInferenceSource = useCallback(async () => {
    setRecovering(true);
    setRecoveryError('');
    try {
      await resetInferenceSource();
      handedOffRef.current = false;
      setSetupInitiated(false);
      setStatus(null);
      await poll();
    } catch (error) {
      setRecoveryError(error instanceof Error ? error.message : String(error));
    } finally {
      setRecovering(false);
    }
  }, [poll]);

  const submitReplacementCredential = useCallback(
    async (keyName: string, keyValue: string) => {
      await updateInferenceCredential(keyName, keyValue);
      await poll();
    },
    [poll],
  );

  const retryBackendStartup = useCallback(async () => {
    await startBackend();
    await poll();
  }, [poll]);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, 800);
    return () => clearInterval(interval);
  }, [poll]);

  if (statusChecked && status?.requires_source && !setupInitiated) {
    return (
      <InferenceSourceSetup
        onStarted={() => {
          setSetupInitiated(true);
          void poll();
        }}
      />
    );
  }

  if (statusChecked && status?.requires_credential) {
    return (
      <div
        className="fixed inset-0 overflow-y-auto flex items-center justify-center p-4 sm:p-6"
        style={{ background: 'var(--color-bg)' }}
      >
        <div className="w-full max-w-md my-auto">
          <div className="text-center mb-6">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
              style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
            >
              <Cpu size={32} />
            </div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--color-text)' }}>
              OpenJarvis
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              Credential configuration required
            </p>
          </div>

          <CredentialRecoveryCard
            provider={status.credential_provider}
            keyName={status.credential_key_name}
            savedModel={status.saved_model}
            savedHost={status.saved_host}
            error={status.error}
            onSubmit={submitReplacementCredential}
            onResetSource={() => void changeInferenceSource()}
          />
        </div>
      </div>
    );
  }

  if (
    statusChecked &&
    (status?.phase === 'provider_busy' || status?.phase === 'network_error')
  ) {
    return (
      <div
        className="fixed inset-0 overflow-y-auto flex items-center justify-center p-4 sm:p-6"
        style={{ background: 'var(--color-bg)' }}
      >
        <div className="w-full max-w-md my-auto">
          <div className="text-center mb-6">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
              style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
            >
              <Cpu size={32} />
            </div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--color-text)' }}>
              OpenJarvis
            </h1>
          </div>

          <ProviderBusyCard
            provider={status.credential_provider}
            error={status.error}
            onRetry={retryBackendStartup}
            onResetSource={() => void changeInferenceSource()}
          />
        </div>
      </div>
    );
  }

  const activeStep: StepKey | null =
    status && !status.ollama_ready
      ? 'ollama_ready'
      : status && !status.model_ready
        ? 'model_ready'
        : status && !status.server_ready
          ? 'server_ready'
          : null;

  const hasStepError = Boolean(status?.error);

  return (
    <div
      className="fixed inset-0 overflow-y-auto flex items-center justify-center p-4 sm:p-6"
      style={{ background: 'var(--color-bg)' }}
    >
      <div className="w-full max-w-md my-auto px-2 sm:px-0">
        {/* Logo */}
        <div className="text-center mb-10">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
          >
            <Cpu size={32} />
          </div>
          <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--color-text)' }}>
            OpenJarvis
          </h1>
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {!statusChecked
              ? 'Checking your saved setup...'
              : status?.source === 'custom'
                ? 'Connecting to your AI server...'
                : 'Setting up your local AI...'}
          </p>
        </div>

        {/* Steps */}
        <div className="flex flex-col gap-2 mb-6">
          {(status?.source === 'custom'
            ? [
                { key: 'ollama_ready' as const, label: 'Inference Engine', icon: Cpu, detail: 'Connecting to your server...' },
                { key: 'model_ready' as const, label: 'Endpoint', icon: Database, detail: 'Checking endpoint...' },
                { key: 'server_ready' as const, label: 'API Server', icon: Server, detail: 'Starting server...' },
              ]
            : STEPS
          ).map((step) => (
            <StepRow
              key={step.key}
              icon={step.icon}
              label={step.label}
              done={status?.[step.key] ?? false}
              active={activeStep === step.key}
              hasError={hasStepError}
              detail={
                activeStep === step.key && status?.detail
                  ? status.detail
                  : step.detail
              }
            />
          ))}
        </div>

        {/* Polished Status Card for Errors */}
        {status?.error && (
          <div className="mb-6">
            <SetupStatusCard
              status={status}
              onRetry={retryBackendStartup}
              onUpdateCredential={submitReplacementCredential}
              onChangeProvider={() => void changeInferenceSource()}
              recovering={recovering}
            />
          </div>
        )}

        {recoveryError && (
          <div
            role="alert"
            className="mt-3 px-4 py-3 rounded-xl text-sm"
            style={{ color: 'var(--color-error)' }}
          >
            {recoveryError}
          </div>
        )}

        {statusChecked && status && !status.requires_source && status.phase !== 'ready' && !status.error && (
          <InferenceRecoveryButton
            recovering={recovering}
            onChange={() => void changeInferenceSource()}
          />
        )}

        {/* Progress bar */}
        {!status?.error && (
          <div
            className="h-1 rounded-full overflow-hidden"
            style={{ background: 'var(--color-bg-tertiary)' }}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                background: 'var(--color-accent)',
                width: `${
                  ((status?.ollama_ready ? 1 : 0) +
                    (status?.model_ready ? 1 : 0) +
                    (status?.server_ready ? 1 : 0)) *
                  33.33
                }%`,
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

