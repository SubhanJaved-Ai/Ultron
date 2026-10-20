import { useState, useEffect } from 'react';
import {
  Shield,
  Activity,
  RotateCcw,
  Sliders,
  CheckCircle,
  AlertCircle,
  Clock,
  Zap,
  Save,
} from 'lucide-react';
import {
  getRuntimeLimits,
  updateRuntimeLimits,
  resetRuntimeLimits,
  type ProviderRuntimeStats,
} from '../../lib/api';

export function RuntimeLimitsSection() {
  const [providers, setProviders] = useState<Record<string, ProviderRuntimeStats>>({});
  const [loading, setLoading] = useState(false);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [formRpm, setFormRpm] = useState<number>(60);
  const [formTpm, setFormTpm] = useState<number>(100_000);
  const [formConcurrency, setFormConcurrency] = useState<number>(5);
  const [formTimeout, setFormTimeout] = useState<number>(60);
  const [statusMsg, setStatusMsg] = useState<string>('');

  const loadLimits = async () => {
    try {
      setLoading(true);
      const res = await getRuntimeLimits();
      setProviders(res.providers || {});
    } catch (err: any) {
      console.error('Failed to load runtime limits', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLimits();
  }, []);

  const handleStartEdit = (provName: string, stats: ProviderRuntimeStats) => {
    setEditingProvider(provName);
    setFormRpm(stats.requests_per_minute_limit || 60);
    setFormTpm(stats.tokens_per_minute_limit || 100_000);
    setFormConcurrency(stats.max_concurrency || 5);
    setFormTimeout(60);
    setStatusMsg('');
  };

  const handleSaveEdit = async () => {
    if (!editingProvider) return;
    try {
      setLoading(true);
      await updateRuntimeLimits({
        provider: editingProvider,
        requests_per_minute: formRpm,
        tokens_per_minute: formTpm,
        max_concurrency: formConcurrency,
        timeout_seconds: formTimeout,
      });
      setStatusMsg(`Successfully updated limits for ${editingProvider}!`);
      setEditingProvider(null);
      await loadLimits();
    } catch (err: any) {
      setStatusMsg(err?.message || 'Failed to update limits');
    } finally {
      setLoading(false);
    }
  };

  const handleResetAll = async () => {
    try {
      setLoading(true);
      await resetRuntimeLimits();
      setStatusMsg('All circuit breakers and rate limiters reset to clean state.');
      await loadLimits();
    } catch (err: any) {
      setStatusMsg(err?.message || 'Failed to reset limiters');
    } finally {
      setLoading(false);
    }
  };

  const provList = Object.entries(providers);

  return (
    <div
      className="p-5 rounded-xl border mb-6"
      style={{
        background: 'var(--color-bg-primary)',
        borderColor: 'var(--color-border)',
      }}
    >
      <div className="flex items-center justify-between pb-4 border-b mb-4 flex-wrap gap-2" style={{ borderColor: 'var(--color-border)' }}>
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Shield size={15} style={{ color: 'var(--color-accent)' }} />
            Runtime Reliability & Centralized Rate Limits
          </h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
            Protects backend inference across chat, tasks, and subagents with token-bucket limits, concurrency controls, and circuit breakers.
          </p>
        </div>
        <button
          onClick={handleResetAll}
          disabled={loading}
          className="px-3 py-1.5 rounded border text-xs font-medium flex items-center gap-1.5 transition-colors hover:bg-black/5"
          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
          title="Reset circuit breaker failure counts and rate tokens"
        >
          <RotateCcw size={12} className={loading ? 'animate-spin' : ''} />
          Reset All Breakers
        </button>
      </div>

      {statusMsg && (
        <div className="mb-4 p-2.5 rounded text-xs border border-blue-500/30 bg-blue-500/10 text-blue-600 flex items-center justify-between">
          <span>{statusMsg}</span>
          <button onClick={() => setStatusMsg('')} className="text-xs opacity-70 hover:opacity-100">Dismiss</button>
        </div>
      )}

      {provList.length === 0 ? (
        <div className="p-8 text-center text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          Loading provider limits…
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {provList.map(([provName, stats]) => {
            const isEditing = editingProvider === provName;
            const isCircuitHealthy = stats.circuit_state === 'closed';
            const isCircuitOpen = stats.circuit_state === 'open';

            return (
              <div
                key={provName}
                className="p-3.5 rounded-lg border flex flex-col justify-between"
                style={{
                  background: 'var(--color-bg-secondary)',
                  borderColor: isEditing ? 'var(--color-accent)' : 'var(--color-border)',
                }}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs capitalize" style={{ color: 'var(--color-text)' }}>
                        {provName}
                      </span>
                      <span
                        className="text-[10px] px-1.5 py-0.2 rounded font-mono"
                        style={{
                          background: stats.is_local ? 'rgba(34, 197, 94, 0.15)' : 'rgba(59, 130, 246, 0.15)',
                          color: stats.is_local ? 'var(--color-success)' : 'var(--color-accent)',
                        }}
                      >
                        {stats.is_local ? 'Local' : 'Cloud'}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span
                        className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-mono font-medium"
                        style={{
                          background: isCircuitHealthy
                            ? 'rgba(34, 197, 94, 0.15)'
                            : isCircuitOpen
                            ? 'rgba(239, 68, 68, 0.15)'
                            : 'rgba(234, 179, 8, 0.15)',
                          color: isCircuitHealthy
                            ? 'var(--color-success)'
                            : isCircuitOpen
                            ? 'var(--color-error)'
                            : '#b45309',
                        }}
                      >
                        {isCircuitHealthy ? <CheckCircle size={10} /> : <AlertCircle size={10} />}
                        {stats.circuit_state.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  {isEditing ? (
                    <div className="mt-3 flex flex-col gap-2 text-xs">
                      <div className="flex items-center justify-between">
                        <label className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>Req/min:</label>
                        <input
                          type="number"
                          value={formRpm}
                          onChange={(e) => setFormRpm(Number(e.target.value))}
                          className="w-24 px-2 py-1 rounded border text-xs font-mono"
                          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-primary)', color: 'var(--color-text)' }}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>Tokens/min:</label>
                        <input
                          type="number"
                          value={formTpm}
                          onChange={(e) => setFormTpm(Number(e.target.value))}
                          className="w-24 px-2 py-1 rounded border text-xs font-mono"
                          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-primary)', color: 'var(--color-text)' }}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>Max Concurrent:</label>
                        <input
                          type="number"
                          value={formConcurrency}
                          onChange={(e) => setFormConcurrency(Number(e.target.value))}
                          className="w-24 px-2 py-1 rounded border text-xs font-mono"
                          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-primary)', color: 'var(--color-text)' }}
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <label className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>Timeout (sec):</label>
                        <input
                          type="number"
                          value={formTimeout}
                          onChange={(e) => setFormTimeout(Number(e.target.value))}
                          className="w-24 px-2 py-1 rounded border text-xs font-mono"
                          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-primary)', color: 'var(--color-text)' }}
                        />
                      </div>
                      <div className="flex items-center justify-end gap-2 mt-2 pt-2 border-t" style={{ borderColor: 'var(--color-border)' }}>
                        <button
                          onClick={() => setEditingProvider(null)}
                          className="px-2.5 py-1 rounded text-[11px] border"
                          style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSaveEdit}
                          className="px-3 py-1 rounded text-[11px] font-medium text-white flex items-center gap-1"
                          style={{ background: 'var(--color-accent)' }}
                        >
                          <Save size={11} /> Save Limits
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
                      <div>
                        <span style={{ color: 'var(--color-text-tertiary)' }}>RPM Limit: </span>
                        <span className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                          {stats.requests_per_minute_limit ?? (stats as any).config?.requests_per_minute ?? 60} / min
                        </span>
                      </div>
                      <div>
                        <span style={{ color: 'var(--color-text-tertiary)' }}>Concurrency: </span>
                        <span className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                          {stats.active_concurrency ?? 0} / {stats.max_concurrency ?? (stats as any).config?.max_concurrent ?? 5}
                        </span>
                      </div>
                      <div className="col-span-2">
                        <span style={{ color: 'var(--color-text-tertiary)' }}>TPM Limit: </span>
                        <span className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                          {(stats.tokens_per_minute_limit ?? (stats as any).config?.tokens_per_minute ?? 100000).toLocaleString()} / min
                        </span>
                      </div>
                      {(stats.consecutive_failures || 0) > 0 && (
                        <div className="col-span-2 text-red-500 text-[10px]">
                          Failures: {stats.consecutive_failures} (cooldown: {(stats.circuit_cooldown_remaining_seconds ?? 0).toFixed(0)}s remaining)
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {!isEditing && (
                  <div className="mt-3 pt-2.5 border-t flex justify-end" style={{ borderColor: 'var(--color-border)' }}>
                    <button
                      onClick={() => handleStartEdit(provName, stats)}
                      className="text-[11px] px-2.5 py-1 rounded border flex items-center gap-1 hover:bg-black/5 transition-colors"
                      style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                    >
                      <Sliders size={11} /> Adjust Limits
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
