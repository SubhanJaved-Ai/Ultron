import { useState, useEffect, useCallback } from 'react';
import {
  Zap,
  Activity,
  Thermometer,
  Hash,
  X,
  Cpu,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { getBase } from '../../lib/api';
import { calculateModelCost } from '../../lib/model-pricing';

interface EnergyData {
  total_energy_j?: number;
  energy_per_token_j?: number;
  avg_power_w?: number;
  cpu_temp_c?: number | null;
  gpu_temp_c?: number | null;
}

interface TelemetryStats {
  total_requests?: number;
  total_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  active_model?: string;
}

export function SystemPanel() {
  const savings = useAppStore((s) => s.savings);
  const toggleSystemPanel = useAppStore((s) => s.toggleSystemPanel);
  const liveEnergy = useAppStore((s) => s.liveEnergy);
  const [energy, setEnergy] = useState<EnergyData | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryStats | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const base = getBase();
      const [energyRes, telRes] = await Promise.allSettled([
        fetch(`${base}/v1/telemetry/energy`).then((r) => (r.ok ? r.json() : null)),
        fetch(`${base}/v1/telemetry/stats`).then((r) => (r.ok ? r.json() : null)),
      ]);
      if (energyRes.status === 'fulfilled' && energyRes.value) {
        setEnergy(energyRes.value as EnergyData);
      }
      if (telRes.status === 'fulfilled' && telRes.value) {
        setTelemetry(telRes.value as TelemetryStats);
      }
    } catch {
      // best-effort
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Re-fetch energy/telemetry when savings updates (after a chat message)
  useEffect(() => {
    if (savings) fetchData();
  }, [savings, fetchData]);

  const selectedModel = useAppStore((s) => s.selectedModel);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const rawModel =
    (typeof selectedModel === 'string' && selectedModel) ||
    (typeof telemetry?.active_model === 'string' && telemetry.active_model) ||
    (typeof serverInfo?.model === 'string' && serverInfo.model) ||
    '';
  const activeModelId = rawModel || 'Local Model';

  const totalRequests = savings?.total_calls ?? telemetry?.total_requests ?? 0;
  const promptTokens = (savings?.total_prompt_tokens && savings.total_prompt_tokens > 0)
    ? savings.total_prompt_tokens
    : (telemetry?.prompt_tokens ?? 0);
  const completionTokens = (savings?.total_completion_tokens && savings.total_completion_tokens > 0)
    ? savings.total_completion_tokens
    : (telemetry?.completion_tokens ?? 0);
  const totalTokens = promptTokens + completionTokens;

  const activeCostResult = calculateModelCost(activeModelId, promptTokens, completionTokens, savings?.local_cost ?? 0);
  const activeModelCost = activeCostResult.cost;

  const activeLower = activeModelId.toLowerCase();
  const isLocal = Boolean(
    activeCostResult.pricing.isLocal ||
    activeLower.includes('ollama') ||
    activeLower.includes('local')
  );

  return (
    <div
      className="flex flex-col h-full overflow-y-auto"
      style={{
        width: 280,
        minWidth: 280,
        background: 'var(--color-bg)',
        borderLeft: '1px solid var(--color-border)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <span className="text-xs font-semibold tracking-wide uppercase" style={{ color: 'var(--color-text-secondary)' }}>
          System & Telemetry
        </span>
        <button
          onClick={toggleSystemPanel}
          className="p-1 rounded-md transition-colors cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
          title="Close panel"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex flex-col gap-4 p-4">
        {/* Session Stats */}
        <section>
          <h4 className="text-[11px] font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
            Session
          </h4>
          <div className="grid grid-cols-2 gap-2">
            <MiniStat icon={Hash} label="Requests" value={String(totalRequests)} />
            <MiniStat
              icon={Hash}
              label="Tokens Used"
              value={formatNumber(totalTokens || completionTokens)}
            />
          </div>
        </section>

        {/* Device */}
        <section>
          <h4 className="text-[11px] font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
            Device
          </h4>
          <div className="grid grid-cols-2 gap-2">
            {energy?.cpu_temp_c != null && (
              <MiniStat icon={Thermometer} label="CPU Temp" value={String(Math.round(energy.cpu_temp_c))} unit="°C" />
            )}
            {energy?.gpu_temp_c != null && (
              <MiniStat icon={Thermometer} label="GPU Temp" value={String(Math.round(energy.gpu_temp_c))} unit="°C" />
            )}
            <MiniStat
              icon={Zap}
              label="Power"
              value={(liveEnergy?.power_w ?? energy?.avg_power_w ?? 0).toFixed(1)}
              unit="W"
            />
            <MiniStat
              icon={Activity}
              label="Energy"
              value={(
                ((liveEnergy?.energy_j ?? energy?.total_energy_j ?? 0) / 1000)
              ).toFixed(1)}
              unit="kJ"
            />
          </div>
        </section>

        {/* Real-Time Cost & Usage — ONLY the Active Model */}
        <section>
          <h4 className="text-[11px] font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
            Active Model & Cost
          </h4>

          {/* Active Model Card */}
          <div
            className="flex items-center gap-2 rounded-lg px-3 py-2.5 mb-2.5"
            style={{ background: 'var(--color-accent-subtle)', border: '1px solid var(--color-accent)' }}
          >
            <Cpu size={15} style={{ color: 'var(--color-accent)' }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }}>
                  {activeCostResult.pricing.displayName}
                </span>
                <span
                  className="text-[8.5px] uppercase px-1 py-0.2 rounded font-semibold shrink-0"
                  style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}
                >
                  Active
                </span>
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                {isLocal ? 'On-Device · Zero API Cost' : 'Cloud Provider · Live Pay-Per-Token'}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-xs font-bold font-mono" style={{ color: isLocal ? 'var(--color-success)' : 'var(--color-text)' }}>
                ${activeModelCost.toFixed(4)}
              </div>
            </div>
          </div>

          {/* Detailed Token Accounting Box */}
          <div
            className="rounded-lg p-3 space-y-2"
            style={{
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border)',
            }}
          >
            <div className="flex items-center justify-between text-[11px]">
              <span style={{ color: 'var(--color-text-secondary)' }}>Input (Prompt) Tokens</span>
              <span className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                {formatNumber(promptTokens)}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span style={{ color: 'var(--color-text-secondary)' }}>Output (Completion) Tokens</span>
              <span className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>
                {formatNumber(completionTokens)}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px] pt-1.5 border-t" style={{ borderColor: 'var(--color-border)' }}>
              <span className="font-semibold" style={{ color: 'var(--color-text)' }}>Total Session Cost</span>
              <span className="font-mono font-bold text-xs" style={{ color: isLocal ? 'var(--color-success)' : 'var(--color-accent)' }}>
                ${activeModelCost.toFixed(4)}
              </span>
            </div>
            {!isLocal && activeCostResult.pricing.inputPerMillion > 0 && (
              <div className="text-[9.5px] pt-1 text-center font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                Rate: ${activeCostResult.pricing.inputPerMillion}/1M in · ${activeCostResult.pricing.outputPerMillion}/1M out
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function MiniStat({
  icon: Icon,
  label,
  value,
  unit,
}: {
  icon: typeof Zap;
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div
      className="rounded-lg px-2.5 py-2"
      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
    >
      <div className="flex items-center gap-1 mb-0.5">
        <Icon size={10} style={{ color: 'var(--color-accent)' }} />
        <span className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
          {label}
        </span>
      </div>
      <div className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
        {value}
        {unit && (
          <span className="text-[10px] font-normal ml-0.5" style={{ color: 'var(--color-text-tertiary)' }}>
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}
