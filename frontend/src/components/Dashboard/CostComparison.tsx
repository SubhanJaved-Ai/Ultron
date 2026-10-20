import { useState, useEffect } from 'react';
import {
  DollarSign,
  Cloud,
  HardDrive,
  Download,
  List,
  ShieldCheck,
  RefreshCw,
  X,
  Radio,
  Clock,
  Receipt,
  AlertTriangle,
} from 'lucide-react';
import {
  getUsageSummary,
  getUsageLedger,
  exportUsageCsv,
  type UsageSummary,
  type UsageRecord,
} from '../../lib/api';

export function CostComparison() {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<number | undefined>(undefined); // all time vs 24h
  const [showLedgerModal, setShowLedgerModal] = useState(false);
  const [ledgerRecords, setLedgerRecords] = useState<UsageRecord[]>([]);
  const [loadingLedger, setLoadingLedger] = useState(false);
  const [downloadingCsv, setDownloadingCsv] = useState(false);

  const fetchSummary = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getUsageSummary(timeRange);
      setSummary(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load usage summary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, [timeRange]);

  const handleOpenLedger = async () => {
    setShowLedgerModal(true);
    setLoadingLedger(true);
    try {
      const data = await getUsageLedger(50, 0);
      setLedgerRecords(data.records || []);
    } catch (err) {
      console.error('Failed to fetch usage ledger records', err);
    } finally {
      setLoadingLedger(false);
    }
  };

  const handleExportCsv = async () => {
    try {
      setDownloadingCsv(true);
      const csvText = await exportUsageCsv();
      const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ultron_usage_ledger_${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('CSV export failed', err);
    } finally {
      setDownloadingCsv(false);
    }
  };

  return (
    <div className="hud-panel p-6">
      {/* Header with Title and Actions */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3 className="hud-label flex items-center gap-2 m-0">
          <DollarSign size={13} style={{ color: 'var(--color-success)' }} />
          Cloud Usage & Cost Accounting
        </h3>
        <div className="flex items-center gap-2">
          {summary?.pricing_version && (
            <span
              className="text-[10px] px-2 py-0.5 rounded border flex items-center gap-1 font-mono"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-secondary)',
                color: 'var(--color-text-secondary)',
              }}
              title="Official pricing catalogue effective version"
            >
              <ShieldCheck size={10} style={{ color: 'var(--color-accent)' }} />
              v:{summary.pricing_version}
            </span>
          )}
          <button
            onClick={() => setTimeRange(timeRange ? undefined : 24)}
            className="text-[11px] px-2 py-1 rounded border flex items-center gap-1 transition-colors"
            style={{
              borderColor: 'var(--color-border)',
              background: timeRange ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
              color: timeRange ? 'var(--color-accent)' : 'var(--color-text-secondary)',
            }}
            title="Toggle All Time vs Last 24 Hours"
          >
            <Clock size={11} />
            {timeRange ? 'Last 24h' : 'All Time'}
          </button>
          <button
            onClick={fetchSummary}
            className="p-1 rounded border hover:opacity-80 transition-opacity"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
            title="Refresh Usage Data"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && !summary ? (
        <div className="h-44 flex items-center justify-center text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
          <span className="hud-mono">fetching usage ledger…</span>
        </div>
      ) : error ? (
        <div className="p-3 text-xs rounded mb-3 border border-red-500/30 text-red-500">
          {error}
        </div>
      ) : summary?.total_requests === 0 ? (
        <div className="p-6 text-center rounded-lg border border-dashed" style={{ borderColor: 'var(--color-border)' }}>
          <Radio size={24} className="mx-auto mb-2 opacity-40" />
          <div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
            No Cloud Usage Recorded Yet
          </div>
          <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            Requests made to OpenAI, Anthropic, Gemini, or ElevenLabs will be recorded in the auditable ledger.
          </div>
        </div>
      ) : (
        <>
          {/* Top High-level Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
            {/* Estimated Cloud API Spend */}
            <div
              className="p-3 rounded-lg border flex flex-col justify-between"
              style={{
                background: 'var(--color-bg-secondary)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                <span className="flex items-center gap-1.5 font-medium">
                  <Cloud size={13} style={{ color: 'var(--color-accent)' }} />
                  Estimated Spend
                </span>
                <span
                  className="text-[9px] uppercase px-1.5 py-0.5 rounded font-mono font-semibold"
                  style={{
                    background: 'var(--color-accent-subtle)',
                    color: 'var(--color-accent)',
                  }}
                >
                  Estimated
                </span>
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono" style={{ color: 'var(--color-text)' }}>
                  ${(summary?.total_estimated_cost_usd || 0).toFixed(4)}
                </span>
                <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  {(summary?.total_requests || 0).toLocaleString()} requests
                </span>
              </div>
              <div className="text-[10px] mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
                {((summary?.total_prompt_tokens || 0) + (summary?.total_completion_tokens || 0)).toLocaleString()} tokens
                {summary?.total_characters ? ` · ${summary.total_characters.toLocaleString()} chars` : ''}
              </div>
            </div>

            {/* Authoritative Provider-Billed Spend */}
            <div
              className="p-3 rounded-lg border flex flex-col justify-between"
              style={{
                background: 'var(--color-bg-secondary)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                <span className="flex items-center gap-1.5 font-medium">
                  <Receipt size={13} style={{ color: '#3b82f6' }} />
                  Provider-Billed
                </span>
                <span
                  className="text-[9px] uppercase px-1.5 py-0.5 rounded font-mono font-semibold"
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: '#3b82f6',
                  }}
                >
                  Reconciled
                </span>
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono" style={{ color: 'var(--color-text)' }}>
                  ${(summary?.total_billed_cost_usd || 0).toFixed(4)}
                </span>
                <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  reconciled
                </span>
              </div>
              <div className="text-[10px] mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
                Authoritative provider billing invoices
              </div>
            </div>

            {/* Local Inference (Free API inference) */}
            <div
              className="p-3 rounded-lg border flex flex-col justify-between"
              style={{
                background: 'var(--color-bg-secondary)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                <span className="flex items-center gap-1.5 font-medium">
                  <HardDrive size={13} style={{ color: 'var(--color-success)' }} />
                  Local Inference
                </span>
                <span
                  className="text-[9px] uppercase px-1.5 py-0.5 rounded font-mono font-semibold"
                  style={{
                    background: 'rgba(34, 197, 94, 0.15)',
                    color: 'var(--color-success)',
                  }}
                >
                  $0.00 API
                </span>
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono" style={{ color: 'var(--color-success)' }}>
                  $0.0000
                </span>
                <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  {summary?.local_requests || 0} calls
                </span>
              </div>
              <div className="text-[10px] mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
                Inference API fee only (excludes host electricity)
              </div>
            </div>

            {/* Unknown / Unmetered Requests */}
            <div
              className="p-3 rounded-lg border flex flex-col justify-between"
              style={{
                background: 'var(--color-bg-secondary)',
                borderColor: 'var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                <span className="flex items-center gap-1.5 font-medium">
                  <AlertTriangle size={13} style={{ color: summary?.unknown_cost_requests ? '#f59e0b' : 'var(--color-text-tertiary)' }} />
                  Unmetered Calls
                </span>
                <span
                  className="text-[9px] uppercase px-1.5 py-0.5 rounded font-mono font-semibold"
                  style={{
                    background: summary?.unknown_cost_requests ? 'rgba(245, 158, 11, 0.15)' : 'rgba(156, 163, 175, 0.15)',
                    color: summary?.unknown_cost_requests ? '#b45309' : 'var(--color-text-tertiary)',
                  }}
                >
                  {summary?.unknown_cost_requests ? 'Action Needed' : 'None'}
                </span>
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-xl font-bold font-mono" style={{ color: 'var(--color-text)' }}>
                  {summary?.unknown_cost_requests || 0}
                </span>
                <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  requests
                </span>
              </div>
              <div className="text-[10px] mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
                Unverified model rates or missing pricing
              </div>
            </div>
          </div>

          {/* Breakdown by Provider */}
          <div className="mb-4">
            <div className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-secondary)' }}>
              Provider Spend Breakdown
            </div>
            <div className="flex flex-col gap-1.5">
              {(summary?.by_provider || []).map((prov) => (
                <div
                  key={prov.provider}
                  className="flex items-center justify-between p-2.5 rounded border text-xs"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                  }}
                >
                  <div className="flex items-center gap-2">
                    {prov.is_local ? (
                      <HardDrive size={13} style={{ color: 'var(--color-success)' }} />
                    ) : (
                      <Cloud size={13} style={{ color: 'var(--color-accent)' }} />
                    )}
                    <span className="font-medium capitalize" style={{ color: 'var(--color-text)' }}>
                      {prov.provider}
                    </span>
                    <span className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                      ({prov.requests} calls)
                    </span>
                  </div>
                  <div className="flex items-center gap-3 font-mono">
                    <span className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                      {(prov.prompt_tokens + prov.completion_tokens).toLocaleString()} toks
                    </span>
                    <span
                      className="font-semibold"
                      style={{
                        color: prov.is_local ? 'var(--color-success)' : 'var(--color-text)',
                      }}
                    >
                      {prov.is_local ? '$0.0000' : `$${prov.estimated_cost_usd.toFixed(4)}`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Action Row: Export CSV & Drill-down Modal */}
          <div
            className="flex items-center justify-between pt-3 border-t text-xs flex-wrap gap-2"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <button
              onClick={handleOpenLedger}
              className="px-3 py-1.5 rounded border flex items-center gap-1.5 font-medium transition-colors hover:bg-black/5"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-secondary)',
                color: 'var(--color-text)',
              }}
            >
              <List size={13} />
              View Request Ledger
            </button>

            <button
              onClick={handleExportCsv}
              disabled={downloadingCsv}
              className="px-3 py-1.5 rounded border flex items-center gap-1.5 font-medium transition-colors hover:bg-black/5"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-secondary)',
                color: 'var(--color-text)',
              }}
            >
              <Download size={13} />
              {downloadingCsv ? 'Exporting…' : 'Export CSV'}
            </button>
          </div>
        </>
      )}

      {/* Request Ledger Drill-Down Modal */}
      {showLedgerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div
            className="hud-panel p-6 max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl rounded-xl"
            style={{ background: 'var(--color-bg-primary)', border: '1px solid var(--color-border)' }}
          >
            <div className="flex items-center justify-between pb-3 border-b mb-4" style={{ borderColor: 'var(--color-border)' }}>
              <div>
                <h4 className="text-base font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
                  <List size={16} style={{ color: 'var(--color-accent)' }} />
                  Auditable Usage Ledger Records
                </h4>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  Transparent request-level records with honest cost attribution and pricing tags.
                </p>
              </div>
              <button
                onClick={() => setShowLedgerModal(false)}
                className="p-1 rounded hover:bg-black/10 transition-colors"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-auto">
              {loadingLedger ? (
                <div className="p-12 text-center text-sm font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                  loading ledger records…
                </div>
              ) : ledgerRecords.length === 0 ? (
                <div className="p-8 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  No request records found in this window.
                </div>
              ) : (
                <table className="w-full text-left text-xs border-collapse font-sans">
                  <thead>
                    <tr
                      className="border-b text-[11px] font-semibold uppercase tracking-wider"
                      style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                    >
                      <th className="py-2 px-2">Request ID</th>
                      <th className="py-2 px-2">Provider / Model</th>
                      <th className="py-2 px-2">Tokens</th>
                      <th className="py-2 px-2">Cost Type</th>
                      <th className="py-2 px-2 text-right">Cost (USD)</th>
                      <th className="py-2 px-2 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledgerRecords.map((r) => (
                      <tr
                        key={r.request_id}
                        className="border-b transition-colors hover:bg-black/[0.02]"
                        style={{ borderColor: 'var(--color-border)' }}
                      >
                        <td className="py-2.5 px-2 font-mono text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                          {r.request_id.slice(0, 12)}…
                        </td>
                        <td className="py-2.5 px-2">
                          <div className="font-medium" style={{ color: 'var(--color-text)' }}>
                            {r.model}
                          </div>
                          <div className="text-[10px] uppercase font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                            {r.provider} {r.purpose ? `· ${r.purpose}` : ''}
                          </div>
                        </td>
                        <td className="py-2.5 px-2 font-mono">
                          <div>{(r.prompt_tokens + r.completion_tokens).toLocaleString()}</div>
                          <div className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                            {r.prompt_tokens} in / {r.completion_tokens} out
                          </div>
                        </td>
                        <td className="py-2.5 px-2">
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium"
                            style={{
                              background:
                                r.cost_type === 'local_zero'
                                  ? 'rgba(34, 197, 94, 0.15)'
                                  : r.cost_type === 'provider_billed'
                                  ? 'rgba(59, 130, 246, 0.15)'
                                  : r.cost_type === 'unknown'
                                  ? 'rgba(156, 163, 175, 0.2)'
                                  : 'rgba(234, 179, 8, 0.15)',
                              color:
                                r.cost_type === 'local_zero'
                                  ? 'var(--color-success)'
                                  : r.cost_type === 'provider_billed'
                                  ? 'var(--color-accent)'
                                  : r.cost_type === 'unknown'
                                  ? 'var(--color-text-secondary)'
                                  : '#b45309',
                            }}
                          >
                            {r.cost_type === 'local_zero'
                              ? 'Local ($0.00)'
                              : r.cost_type === 'provider_billed'
                              ? 'Provider-Billed'
                              : r.cost_type === 'unknown'
                              ? 'Unknown'
                              : 'Estimated'}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-semibold" style={{ color: 'var(--color-text)' }}>
                          {r.cost_type === 'local_zero'
                            ? '$0.0000'
                            : r.cost_type === 'unknown'
                            ? '—'
                            : `$${(r.billed_cost_usd > 0 ? r.billed_cost_usd : r.estimated_cost_usd).toFixed(4)}`}
                        </td>
                        <td className="py-2.5 px-2 text-center">
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono"
                            style={{
                              background: r.status === 'success' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                              color: r.status === 'success' ? 'var(--color-success)' : 'var(--color-error)',
                            }}
                          >
                            {r.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="pt-3 border-t flex justify-end mt-4" style={{ borderColor: 'var(--color-border)' }}>
              <button
                onClick={() => setShowLedgerModal(false)}
                className="px-4 py-1.5 rounded border text-xs font-medium hover:bg-black/5 transition-colors"
                style={{ borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
