import { useState, useEffect } from 'react';
import {
  Cpu,
  HardDrive,
  CheckCircle,
  AlertTriangle,
  Play,
  RotateCcw,
  Download,
  ShieldAlert,
  Sparkles,
  Zap,
  Check,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';
import {
  getHardwareScan,
  getModelRecommendations,
  runModelBenchmark,
  installLocalModel,
  getCurrentModelPreferences,
  configureModelPreferences,
  rollbackModelPreferences,
  type HardwareScanResult,
  type ModelRecommendation,
  type LocalBenchmarkResult,
} from '../../lib/api';

export function LocalModelWizard() {
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [loading, setLoading] = useState(false);
  const [hardware, setHardware] = useState<HardwareScanResult | null>(null);
  const [recommendations, setRecommendations] = useState<ModelRecommendation[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('qwen3:8b');
  const [benchmarkResult, setBenchmarkResult] = useState<LocalBenchmarkResult | null>(null);
  const [installConfirm, setInstallConfirm] = useState(false);
  const [installStatus, setInstallStatus] = useState<{ status: string; detail?: string } | null>(null);
  const [currentPref, setCurrentPref] = useState<{ provider: string; model: string; previous_model?: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState<string>('');

  useEffect(() => {
    loadCurrentPrefs();
  }, []);

  const loadCurrentPrefs = async () => {
    try {
      const res = await getCurrentModelPreferences();
      if (res?.current) {
        setCurrentPref(res.current);
      }
    } catch {
      // Ignore if unconfigured
    }
  };

  const handleScanHardware = async () => {
    setLoading(true);
    setStatusMsg('');
    try {
      const data = await getModelRecommendations();
      setHardware(data.hardware);
      setRecommendations(data.recommendations);
      if (data.recommendations.length > 0) {
        setSelectedModel(data.recommendations[0].model_id);
      }
      setStep(2);
    } catch (err: any) {
      setStatusMsg(err?.message || 'Hardware scan failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRunBenchmark = async () => {
    setLoading(true);
    setStatusMsg('');
    try {
      const res = await runModelBenchmark(selectedModel);
      setBenchmarkResult(res);
      setStep(3);
    } catch (err: any) {
      setStatusMsg(err?.message || 'Benchmark run failed');
    } finally {
      setLoading(false);
    }
  };

  const handleInstallModel = async () => {
    if (!installConfirm) {
      setStatusMsg('Explicit confirmation is required before downloading model weights.');
      return;
    }
    setLoading(true);
    setStatusMsg('');
    try {
      const res = await installLocalModel(selectedModel, true);
      setInstallStatus(res);
      if (res.status === 'success' || res.output) {
        setStatusMsg(`Successfully prepared ${selectedModel}!`);
      } else {
        setStatusMsg(res.detail || res.error || 'Installation report received.');
      }
    } catch (err: any) {
      setStatusMsg(err?.message || 'Installation failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleConfigureModel = async () => {
    setLoading(true);
    setStatusMsg('');
    try {
      const res = await configureModelPreferences('ollama', selectedModel);
      setCurrentPref(res.current);
      setStatusMsg(`Ultron is now configured to use ${selectedModel} via Ollama!`);
      loadCurrentPrefs();
    } catch (err: any) {
      setStatusMsg(err?.message || 'Configuration failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRollbackModel = async () => {
    setLoading(true);
    setStatusMsg('');
    try {
      const res = await rollbackModelPreferences();
      setCurrentPref(res.current);
      setStatusMsg(`Successfully rolled back to ${res.current?.model}!`);
      loadCurrentPrefs();
    } catch (err: any) {
      setStatusMsg(err?.message || 'Rollback failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="p-5 rounded-xl border mb-6"
      style={{
        background: 'var(--color-bg-primary)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* Wizard Header & Stepper */}
      <div className="flex items-center justify-between pb-4 border-b mb-4 flex-wrap gap-2" style={{ borderColor: 'var(--color-border)' }}>
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Sparkles size={15} style={{ color: 'var(--color-accent)' }} />
            One-Click Local Model Recommendation & Wizard
          </h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
            Scan system hardware, receive Ultron-optimized local recommendations, benchmark, and install with 1 click.
          </p>
        </div>
        {currentPref && (
          <div className="text-[11px] px-2.5 py-1 rounded border flex items-center gap-1.5" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-secondary)' }}>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Active Model:</span>
            <span className="font-mono font-medium" style={{ color: 'var(--color-text)' }}>{currentPref.model}</span>
            <span className="text-[9px] uppercase font-mono px-1 py-0.5 rounded" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}>
              {currentPref.provider}
            </span>
          </div>
        )}
      </div>

      {/* Steps Nav */}
      <div className="flex items-center gap-1 mb-5 overflow-x-auto pb-1 text-xs font-medium">
        {[
          { num: 1, label: '1. Scan' },
          { num: 2, label: '2. Recommendations' },
          { num: 3, label: '3. Benchmark' },
          { num: 4, label: '4. Install' },
          { num: 5, label: '5. Configure' },
        ].map((s) => (
          <button
            key={s.num}
            onClick={() => setStep(s.num as any)}
            className="flex items-center gap-1 px-3 py-1 rounded-lg border transition-all cursor-pointer whitespace-nowrap"
            style={{
              borderColor: step === s.num ? 'var(--color-accent)' : 'var(--color-border)',
              background: step === s.num ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
              color: step === s.num ? 'var(--color-accent)' : 'var(--color-text-secondary)',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      {statusMsg && (
        <div className="mb-4 p-2.5 rounded text-xs border border-blue-500/30 bg-blue-500/10 text-blue-600 flex items-center justify-between">
          <span>{statusMsg}</span>
          <button onClick={() => setStatusMsg('')} className="text-xs opacity-70 hover:opacity-100">Dismiss</button>
        </div>
      )}

      {/* STEP 1: SCAN */}
      {step === 1 && (
        <div className="flex flex-col gap-4">
          <div className="p-4 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
            <div>
              <div className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                System Hardware Discovery
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                Non-privileged scan of CPU cores, total/free RAM, GPU vendor, VRAM, and local Ollama service status.
              </p>
            </div>
            <button
              onClick={handleScanHardware}
              disabled={loading}
              className="px-4 py-2 rounded-lg font-medium text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-sm text-white"
              style={{ background: 'var(--color-accent)' }}
            >
              <Zap size={14} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Scanning System…' : 'Scan Hardware & Recommend'}
            </button>
          </div>

          {hardware && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>CPU & Architecture</div>
                <div className="font-semibold mt-0.5 truncate" style={{ color: 'var(--color-text)' }}>{hardware.cpu_brand}</div>
                <div className="text-[10px] text-gray-400">{hardware.cpu_cores} cores · {hardware.architecture}</div>
              </div>
              <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>System RAM</div>
                <div className="font-semibold mt-0.5" style={{ color: 'var(--color-text)' }}>{hardware.total_ram_gb.toFixed(1)} GB Total</div>
                <div className="text-[10px] text-gray-400">{hardware.free_ram_gb.toFixed(1)} GB Available</div>
              </div>
              <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>GPU & VRAM</div>
                <div className="font-semibold mt-0.5 truncate" style={{ color: 'var(--color-text)' }}>{hardware.gpu_name}</div>
                <div className="text-[10px] text-gray-400">
                  {hardware.total_vram_gb > 0 ? `${hardware.total_vram_gb.toFixed(1)} GB VRAM` : 'No Dedicated VRAM'}
                </div>
              </div>
              <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>Ollama Runtime</div>
                <div className="font-semibold mt-0.5 flex items-center gap-1.5" style={{ color: hardware.ollama_installed ? 'var(--color-success)' : '#ef4444' }}>
                  <span className={`w-2 h-2 rounded-full ${hardware.ollama_installed ? 'bg-emerald-500' : 'bg-red-500'}`} />
                  {hardware.ollama_installed ? (hardware.ollama_running ? 'Running' : 'Installed') : 'Not Installed'}
                </div>
                <div className="text-[10px] text-gray-400">{hardware.installed_models.length} local models present</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* STEP 2: RECOMMENDATIONS */}
      {step === 2 && (
        <div className="flex flex-col gap-3">
          <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Ranked for Ultron agentic workflows (tool schema reliability, instruction following, and memory fit):
          </div>

          <div className="flex flex-col gap-2.5">
            {recommendations.map((rec) => {
              const isSelected = selectedModel === rec.model_id;
              return (
                <div
                  key={rec.model_id}
                  onClick={() => setSelectedModel(rec.model_id)}
                  className="p-3.5 rounded-lg border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  style={{
                    borderColor: isSelected ? 'var(--color-accent)' : 'var(--color-border)',
                    background: isSelected ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
                  }}
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-xs" style={{ color: 'var(--color-text)' }}>
                        {rec.name}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium" style={{ background: 'rgba(0,0,0,0.06)', color: 'var(--color-text-secondary)' }}>
                        {rec.parameter_size}
                      </span>
                      <span
                        className="text-[10px] px-2 py-0.5 rounded font-medium"
                        style={{
                          background:
                            rec.fit_status === 'recommended'
                              ? 'rgba(34, 197, 94, 0.15)'
                              : rec.fit_status === 'supported'
                              ? 'rgba(59, 130, 246, 0.15)'
                              : 'rgba(234, 179, 8, 0.15)',
                          color:
                            rec.fit_status === 'recommended'
                              ? 'var(--color-success)'
                              : rec.fit_status === 'supported'
                              ? 'var(--color-accent)'
                              : '#b45309',
                        }}
                      >
                        {rec.fit_status.toUpperCase()}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/10 text-purple-600 font-medium">
                        Tools: {rec.tool_calling_support}
                      </span>
                    </div>
                    <p className="text-xs mt-1.5 leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                      {rec.reasoning}
                    </p>
                    <div className="flex items-center gap-3 text-[10px] mt-2 font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                      <span>Download: ~{rec.estimated_download_gb} GB</span>
                      <span>RAM Needed: ~{rec.estimated_ram_gb} GB</span>
                      <span>Context: {rec.context_length.toLocaleString()}</span>
                      <span>License: {rec.license_type}</span>
                    </div>
                  </div>

                  <div className="flex sm:flex-col items-end justify-between sm:justify-center gap-2">
                    <div className="text-right">
                      <div className="text-lg font-bold font-mono" style={{ color: 'var(--color-accent)' }}>
                        {rec.overall_score}/100
                      </div>
                      <div className="text-[9px] uppercase font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                        Suitability Score
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedModel(rec.model_id);
                        setStep(3);
                      }}
                      className="px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1 border transition-colors hover:bg-black/5"
                      style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                    >
                      Benchmark <ChevronRight size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* STEP 3: BENCHMARK */}
      {step === 3 && (
        <div className="flex flex-col gap-4">
          <div className="p-4 rounded-lg border flex flex-col sm:flex-row sm:items-center justify-between gap-3" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
            <div>
              <div className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                Ultron Capability Benchmark for <span className="font-mono text-blue-600">{selectedModel}</span>
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                Evaluates 8 isolated scenarios: tool format, parameter validation, multi-step planning, tool recovery, and destructive action refusal.
              </p>
            </div>
            <button
              onClick={handleRunBenchmark}
              disabled={loading}
              className="px-4 py-2 rounded-lg font-medium text-xs flex items-center justify-center gap-2 transition-all cursor-pointer shadow-sm text-white"
              style={{ background: 'var(--color-accent)' }}
            >
              <Play size={13} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Evaluating Model…' : 'Run 8-Scenario Benchmark'}
            </button>
          </div>

          {benchmarkResult && (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-3 gap-2.5 text-xs">
                <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                  <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>Pass Rate</div>
                  <div className="text-xl font-bold font-mono mt-0.5" style={{ color: benchmarkResult.pass_rate_pct >= 75 ? 'var(--color-success)' : '#eab308' }}>
                    {benchmarkResult.pass_rate_pct.toFixed(0)}%
                  </div>
                  <div className="text-[10px] text-gray-400">{benchmarkResult.scenarios_passed}/{benchmarkResult.scenarios_tested} passed</div>
                </div>
                <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                  <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>Average Latency</div>
                  <div className="text-xl font-bold font-mono mt-0.5" style={{ color: 'var(--color-text)' }}>
                    {benchmarkResult.avg_latency_ms.toFixed(0)} ms
                  </div>
                  <div className="text-[10px] text-gray-400">Isolated evaluation</div>
                </div>
                <div className="p-3 rounded border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
                  <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>Tool Validity</div>
                  <div className="text-xl font-bold font-mono mt-0.5" style={{ color: 'var(--color-accent)' }}>
                    {benchmarkResult.tool_validity_pct.toFixed(0)}%
                  </div>
                  <div className="text-[10px] text-gray-400">Strict schema conformance</div>
                </div>
              </div>

              <div className="flex flex-col gap-1.5 mt-2">
                {benchmarkResult.results.map((res) => (
                  <div
                    key={res.scenario_id}
                    className="p-2.5 rounded border text-xs flex items-center justify-between"
                    style={{ background: 'var(--color-bg-primary)', borderColor: 'var(--color-border)' }}
                  >
                    <div className="flex items-center gap-2">
                      {res.passed ? (
                        <CheckCircle size={14} style={{ color: 'var(--color-success)' }} />
                      ) : (
                        <AlertTriangle size={14} style={{ color: 'var(--color-error)' }} />
                      )}
                      <span className="font-medium" style={{ color: 'var(--color-text)' }}>
                        {res.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 font-mono text-[11px]">
                      <span style={{ color: 'var(--color-text-secondary)' }}>{res.latency_ms.toFixed(0)}ms</span>
                      <span className="text-[10px] uppercase font-bold" style={{ color: res.passed ? 'var(--color-success)' : 'var(--color-error)' }}>
                        {res.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-end mt-2">
                <button
                  onClick={() => setStep(4)}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-white flex items-center gap-1.5 transition-colors"
                  style={{ background: 'var(--color-accent)' }}
                >
                  Proceed to Install <ChevronRight size={13} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* STEP 4: INSTALL */}
      {step === 4 && (
        <div className="flex flex-col gap-4">
          <div className="p-4 rounded-lg border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
            <div className="flex items-center gap-2 text-xs font-semibold mb-2" style={{ color: 'var(--color-text)' }}>
              <Download size={14} style={{ color: 'var(--color-accent)' }} />
              Guided Model Installation for <span className="font-mono text-blue-600">{selectedModel}</span>
            </div>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              In accordance with safety guidelines, downloading model weights requires explicit user confirmation.
              Ultron communicates directly with your local Ollama daemon to securely pull weights into your local repository.
            </p>

            <div className="mt-4 p-3 rounded border flex items-center gap-2 bg-amber-500/10 border-amber-500/30 text-amber-800 text-xs">
              <input
                type="checkbox"
                id="installConfirmCheck"
                checked={installConfirm}
                onChange={(e) => setInstallConfirm(e.target.checked)}
                className="rounded cursor-pointer"
              />
              <label htmlFor="installConfirmCheck" className="cursor-pointer font-medium">
                I explicitly confirm downloading weights for {selectedModel} onto this machine.
              </label>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <button
                onClick={handleInstallModel}
                disabled={loading || !installConfirm}
                className="px-4 py-2 rounded-lg text-xs font-medium text-white flex items-center gap-2 transition-opacity cursor-pointer disabled:opacity-50"
                style={{ background: 'var(--color-accent)' }}
              >
                <Download size={13} className={loading ? 'animate-spin' : ''} />
                {loading ? 'Downloading Model…' : 'Start Download'}
              </button>
              <button
                onClick={() => setStep(5)}
                className="px-3 py-2 rounded-lg text-xs font-medium border transition-colors hover:bg-black/5"
                style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
              >
                Skip / Already Installed
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STEP 5: CONFIGURE & ROLLBACK */}
      {step === 5 && (
        <div className="flex flex-col gap-4">
          <div className="p-4 rounded-lg border" style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}>
            <div className="text-xs font-semibold mb-1" style={{ color: 'var(--color-text)' }}>
              Activate and Configure Model
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              Set <span className="font-mono font-medium">{selectedModel}</span> as your active local model. Previous configurations are automatically backed up and can be restored at any time.
            </p>

            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={handleConfigureModel}
                disabled={loading}
                className="px-4 py-2 rounded-lg text-xs font-medium text-white flex items-center gap-2 transition-all cursor-pointer shadow-sm"
                style={{ background: 'var(--color-accent)' }}
              >
                <Check size={14} />
                Activate {selectedModel}
              </button>

              {currentPref?.previous_model && (
                <button
                  onClick={handleRollbackModel}
                  disabled={loading}
                  className="px-3 py-2 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition-colors hover:bg-black/5"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                  title={`Restore previous configuration (${currentPref.previous_model})`}
                >
                  <RotateCcw size={13} />
                  Rollback to {currentPref.previous_model}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
