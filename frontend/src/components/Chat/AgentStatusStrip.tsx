import { Globe, Cpu, Loader2, Sparkles, CheckCircle2, Wrench, Camera } from 'lucide-react';
import type { StreamState } from '../../types';

interface Props {
  streamState: StreamState;
}

export function AgentStatusStrip({ streamState }: Props) {
  if (!streamState.isStreaming) return null;

  const runningTool = streamState.activeToolCalls?.find((t) => t.status === 'running');
  const completedTools = streamState.activeToolCalls?.filter((t) => t.status !== 'running') ?? [];
  const model = streamState.activeModel || 'ai';
  const elapsedSec = (streamState.elapsedMs / 1000).toFixed(1);

  // Determine stage icon & label
  let toolLabel = runningTool?.tool;
  let isBrowser = false;
  let isScreenshot = false;
  let targetUrl: string | null = null;

  if (runningTool) {
    const tLower = typeof runningTool.tool === 'string' ? runningTool.tool.toLowerCase() : '';
    isBrowser = /browser|navigate|visit|open_url|goto/i.test(tLower);
    isScreenshot = /screenshot|capture/i.test(tLower);
    if (runningTool.arguments) {
      try {
        const parsed = JSON.parse(runningTool.arguments);
        targetUrl = parsed.url || parsed.href || parsed.link || parsed.address;
      } catch {}
    }
  }

  return (
    <div
      className="mb-2 px-3 py-1.5 rounded-xl flex items-center justify-between text-xs transition-all"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      }}
    >
      <div className="flex items-center gap-2 min-w-0">
        {/* Pulsing state icon */}
        {runningTool ? (
          isScreenshot ? (
            <Camera size={13} className="animate-pulse" style={{ color: 'var(--color-accent)' }} />
          ) : isBrowser ? (
            <Globe size={13} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
          ) : (
            <Wrench size={13} className="animate-pulse" style={{ color: 'var(--color-accent)' }} />
          )
        ) : (
          <Sparkles size={13} className="animate-pulse" style={{ color: 'var(--color-accent)' }} />
        )}

        {/* State progression */}
        <div className="flex items-center gap-1.5 truncate">
          <span
            style={{
              color: !runningTool && streamState.phase.includes('thinking') ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              fontWeight: 500,
            }}
          >
            Thinking
          </span>

          {completedTools.length > 0 && (
            <>
              <span style={{ color: 'var(--color-text-tertiary)' }}>→</span>
              <span className="flex items-center gap-1" style={{ color: 'var(--color-success)' }}>
                <CheckCircle2 size={11} />
                {completedTools.length} {completedTools.length === 1 ? 'tool' : 'tools'} used
              </span>
            </>
          )}

          {runningTool && (
            <>
              <span style={{ color: 'var(--color-text-tertiary)' }}>→</span>
              <span className="flex items-center gap-1 font-semibold truncate" style={{ color: 'var(--color-accent)' }}>
                <Loader2 size={11} className="animate-spin shrink-0" />
                <span className="truncate">
                  {isBrowser && targetUrl
                    ? `Visiting ${targetUrl.replace(/^https?:\/\/(www\.)?/, '').slice(0, 28)}...`
                    : isScreenshot
                    ? 'Capturing screenshot...'
                    : `Running ${toolLabel}...`}
                </span>
              </span>
            </>
          )}

          {!runningTool && streamState.phase.includes('Generating') && (
            <>
              <span style={{ color: 'var(--color-text-tertiary)' }}>→</span>
              <span style={{ color: 'var(--color-accent)', fontWeight: 500 }}>
                Writing response
              </span>
            </>
          )}
        </div>
      </div>

      {/* Model badge + live timer */}
      <div className="flex items-center gap-2 pl-2 shrink-0 font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
        {model && (
          <span className="flex items-center gap-1 px-1.5 py-0.5 rounded" style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)' }}>
            <Cpu size={10} style={{ color: 'var(--color-accent)' }} />
            {model.split('/').pop()?.split(':')[0]}
          </span>
        )}
        <span className="tabular-nums font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          {elapsedSec}s
        </span>
      </div>
    </div>
  );
}
