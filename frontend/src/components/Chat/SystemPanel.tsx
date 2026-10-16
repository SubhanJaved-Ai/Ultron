import { useState, useEffect, useCallback } from 'react';
import {
  Zap,
  Activity,
  Thermometer,
  DollarSign,
  TrendingDown,
  Cloud,
  HardDrive,
  Hash,
  X,
  Trophy,
  ExternalLink,
  Cpu,
  CheckCircle2,
} from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { getBase } from '../../lib/api';
import {
  calculateModelCost,
  getModelPricing,
  formatModelName,
} from '../../lib/model-pricing';

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

const BENCHMARKS = [
  { name: 'GPT-4o', input: 2.50, output: 10.00 },
  { name: 'Claude 3.5 Sonnet', input: 3.00, output: 15.00 },
];

export function SystemPanel() {
  const savings = useAppStore((s) => s.savings);
  const toggleSystemPanel = useAppStore((s) => s.toggleSystemPanel);
  const optInEnabled = useAppStore((s) => s.optInEnabled);
  const setOptInModalOpen = useAppStore((s) => s.setOptInModalOpen);
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
  const activeModelId = selectedModel || telemetry?.active_model || serverInfo?.model || 'Local Model';

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

  const promptK = promptTokens / 1000;
  const completionK = completionTokens / 1000;

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
          System
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
              label="Output Tokens"
              value={formatNumber(completionTokens || totalTokens)}
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

        {/* Real-Time Cost & Usage */}
        <section>
          <h4 className="text-[11px] font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
            Model Usage & Cost
          </h4>

          {/* Active Model */}
          <div
            className="flex items-center gap-2 rounded-lg px-3 py-2.5 mb-2"
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
                {promptTokens > 0 || completionTokens > 0
                  ? `${formatNumber(promptTokens)} in · ${formatNumber(completionTokens)} out`
                  : '0 tokens used'}
              </div>
            </div>
            <div className="text-xs font-bold font-mono" style={{ color: 'var(--color-text)' }}>
              ${activeModelCost.toFixed(4)}
            </div>
          </div>

          {/* Local vs Cloud Context */}
          {activeModelId.toLowerCase().includes('ollama') || activeModelId.toLowerCase().includes('local') ? (
            <div
              className="flex items-center gap-2 rounded-lg px-3 py-2 mb-2"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
            >
              <HardDrive size={14} style={{ color: 'var(--color-success)' }} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }}>On-Device Inference</div>
                <div className="text-[9.5px]" style={{ color: 'var(--color-text-tertiary)' }}>100% Private & Free</div>
              </div>
              <div className="text-xs font-mono font-semibold" style={{ color: 'var(--color-success)' }}>
                $0.0000
              </div>
            </div>
          ) : (
            <div
              className="flex items-center gap-2 rounded-lg px-3 py-2 mb-2"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
            >
              <Cloud size={14} style={{ color: 'var(--color-accent)' }} />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }}>Cloud Provider</div>
                <div className="text-[9.5px]" style={{ color: 'var(--color-text-tertiary)' }}>Pay-Per-Token / BYOK</div>
              </div>
              <div className="text-xs font-mono font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                ${activeModelCost.toFixed(4)}
              </div>
            </div>
          )}

          {/* Hypothetical Commercial Benchmark (Savings) */}
          <div
            className="rounded-lg p-2.5"
            style={{
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border)',
            }}
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-medium uppercase tracking-wide" style={{ color: 'var(--color-text-tertiary)' }}>
                Commercial Benchmark (Hypothetical)
              </span>
              <DollarSign size={11} style={{ color: 'var(--color-text-tertiary)' }} />
            </div>
            {BENCHMARKS.map((provider) => {
              const hypotheticalCost = (promptK * provider.input) / 1000 + (completionK * provider.output) / 1000;
              const savedVsActive = hypotheticalCost - activeModelCost;
              return (
                <div
                  key={provider.name}
                  className="flex items-center justify-between text-[11px] py-1 border-t first:border-t-0"
                  style={{ borderColor: 'var(--color-border)' }}
                >
                  <span style={{ color: 'var(--color-text-secondary)' }}>{provider.name}</span>
                  <div className="text-right">
                    <span className="font-mono text-[10.5px]" style={{ color: 'var(--color-text-tertiary)' }}>
                      ${hypotheticalCost.toFixed(4)}
                    </span>
                    {savedVsActive > 0.0001 && (
                      <span className="text-[9px] block font-medium" style={{ color: 'var(--color-success)' }}>
                        Save ${(savedVsActive).toFixed(4)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Leaderboard / Share */}
        <section>
          <h4
            className="text-[11px] font-medium uppercase tracking-wide mb-2"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            Leaderboard
          </h4>

          <button
            onClick={() => setOptInModalOpen(true)}
            className="w-full flex items-center gap-2 rounded-lg px-3 py-2.5 transition-colors cursor-pointer"
            style={{
              background: optInEnabled
                ? 'var(--color-accent-subtle)'
                : 'var(--color-bg-secondary)',
              border: optInEnabled
                ? '1px solid var(--color-accent)'
                : '1px solid var(--color-border)',
            }}
          >
            <Trophy
              size={14}
              style={{
                color: optInEnabled ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
              }}
            />
            <span
              className="text-xs flex-1 text-left"
              style={{
                color: optInEnabled ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              }}
            >
              {optInEnabled ? 'Sharing Savings' : 'Share Your Savings'}
            </span>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full"
              style={{
                background: optInEnabled ? 'var(--color-accent)' : 'var(--color-bg-tertiary, var(--color-bg-secondary))',
                color: optInEnabled ? 'white' : 'var(--color-text-tertiary)',
              }}
            >
              {optInEnabled ? 'ON' : 'OFF'}
            </span>
          </button>

          <a
            href="https://open-jarvis.github.io/OpenJarvis/leaderboard"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 mt-1.5 px-3 py-1.5 text-[11px] rounded-lg transition-colors"
            style={{ color: 'var(--color-text-tertiary)' }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-accent)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--color-text-tertiary)')}
          >
            <ExternalLink size={10} />
            View Leaderboard
          </a>
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
