import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, CheckCircle2, XCircle, Globe, Cpu } from 'lucide-react';
import type { ToolCallInfo } from '../../types';
import { serializeToolCallArguments } from '../../lib/tool-call';


interface Props {
  toolCall: ToolCallInfo;
}

const statusConfig = {
  running: { icon: Loader2, color: 'var(--color-accent)' },
  success: { icon: CheckCircle2, color: 'var(--color-success)' },
  error: { icon: XCircle, color: 'var(--color-error)' },
};

function previewArgs(raw: string): string {
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      const entries = Object.entries(parsed);
      if (entries.length === 0) return '';
      const [k, v] = entries[0];
      const valStr = typeof v === 'string' ? v : JSON.stringify(v);
      const trimmed = valStr.length > 40 ? `${valStr.slice(0, 40)}…` : valStr;
      return entries.length === 1 ? `${k}: ${trimmed}` : `${k}: ${trimmed}, …`;
    }
  } catch {
    /* fall through */
  }
  return raw.length > 60 ? `${raw.slice(0, 60)}…` : raw;
}

/** Extract a URL from tool arguments if this is a browser/navigation tool. */
function extractBrowserUrl(toolName: string, argsText: string): string | null {
  const isBrowserTool = /browser|navigate|visit|open_url|goto|screenshot/i.test(toolName);
  if (!isBrowserTool) return null;
  try {
    const parsed = JSON.parse(argsText);
    const url = parsed.url || parsed.href || parsed.link || parsed.address;
    if (typeof url === 'string' && url.startsWith('http')) return url;
  } catch {/* ignore */}
  return null;
}

/** True if the string looks like a base64-encoded image. */
function isBase64Image(s: string): boolean {
  return /^data:image\/[a-z]+;base64,/.test(s) ||
    (s.length > 200 && /^[A-Za-z0-9+/]+=*$/.test(s.slice(0, 100)));
}

function ScreenshotThumb({ data }: { data: string }) {
  const [big, setBig] = useState(false);
  const src = data.startsWith('data:') ? data : `data:image/png;base64,${data}`;
  return (
    <div className="mt-1.5">
      <div style={{ color: 'var(--color-text-tertiary)', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
        screenshot
      </div>
      <img
        src={src}
        alt="Tool screenshot"
        onClick={() => setBig(!big)}
        style={{
          maxHeight: big ? 400 : 140,
          width: '100%',
          objectFit: 'contain',
          borderRadius: 4,
          cursor: 'zoom-in',
          border: '1px solid var(--color-border)',
          background: '#000',
          transition: 'max-height 0.2s ease',
        }}
      />
      <div style={{ color: 'var(--color-text-tertiary)', fontSize: 9.5, marginTop: 2 }}>
        {big ? 'Click to collapse' : 'Click to expand'}
      </div>
    </div>
  );
}

export function ToolCallCard({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const config = statusConfig[toolCall.status];
  const StatusIcon = config.icon;
  // Persisted conversations may contain the pre-fix object payload despite
  // the TypeScript contract, so normalize again at the final render boundary.
  const argumentsText = serializeToolCallArguments(toolCall.arguments);
  const preview = previewArgs(argumentsText);
  const browserUrl = extractBrowserUrl(toolCall.tool, argumentsText);
  const hasScreenshot = toolCall.result ? isBase64Image(toolCall.result) : false;
  const resultText = hasScreenshot ? null : toolCall.result;
  const modelShort = toolCall.model ? toolCall.model.split('/').pop()!.split(':')[0] : null;

  return (
    <div
      className="rounded-md text-xs overflow-hidden"
      style={{
        border: '1px solid var(--color-border-subtle, var(--color-border))',
        background: 'var(--color-bg-tertiary, var(--color-bg-secondary))',
        fontFamily:
          'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-2.5 py-1.5 cursor-pointer text-left"
        style={{ background: 'transparent' }}
      >
        {expanded ? (
          <ChevronDown size={11} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
        ) : (
          <ChevronRight size={11} style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
        )}
        <StatusIcon
          size={11}
          style={{ color: config.color, flexShrink: 0 }}
          className={toolCall.status === 'running' ? 'animate-spin' : ''}
        />
        <span style={{ color: 'var(--color-text)', fontWeight: 600, flexShrink: 0 }}>
          {toolCall.tool}
        </span>
        {/* Always-visible "Used this tool" label */}
        <span style={{ color: 'var(--color-accent)', fontSize: 9.5, fontWeight: 500, flexShrink: 0, letterSpacing: '0.03em' }}>
          Used
        </span>
        {modelShort && (
          <span className="flex items-center gap-0.5" style={{ color: 'var(--color-text-tertiary)', fontSize: 9.5, flexShrink: 0 }}>
            <Cpu size={8} />
            {modelShort}
          </span>
        )}
        {preview && !expanded && (
          <span
            className="truncate"
            style={{ color: 'var(--color-text-tertiary)', fontSize: 10.5 }}
          >
            {preview}
          </span>
        )}
        <div className="flex-1" />
        {toolCall.latency != null && (
          <span style={{ color: 'var(--color-text-tertiary)', fontSize: 10, flexShrink: 0 }}>
            {toolCall.latency < 1000
              ? `${Math.round(toolCall.latency)}ms`
              : `${(toolCall.latency / 1000).toFixed(1)}s`}
          </span>
        )}
      </button>
      {expanded && (
        <div
          className="px-2.5 pb-2 pt-0.5"
          style={{ borderTop: '1px solid var(--color-border-subtle, var(--color-border))' }}
        >
          {/* Proof-of-execution annotation */}
          {toolCall.model && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <Cpu size={10} style={{ color: 'var(--color-accent)', flexShrink: 0 }} />
              <span style={{ color: 'var(--color-text-tertiary)', fontSize: 10 }}>
                Dispatched by{' '}
                <span style={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>{toolCall.model}</span>
                {' '}— Real execution, not memory
              </span>
            </div>
          )}

          {/* Browser URL */}
          {browserUrl && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <Globe size={10} style={{ color: 'var(--color-accent)', flexShrink: 0 }} />
              <a href={browserUrl} target="_blank" rel="noreferrer"
                style={{ color: 'var(--color-accent)', fontSize: 10.5, wordBreak: 'break-all' }}>
                {browserUrl}
              </a>
            </div>
          )}
          {argumentsText && (
            <div className="mt-1.5">
              <div style={{ color: 'var(--color-text-tertiary)', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>
                args
              </div>
              <pre
                className="p-1.5 rounded overflow-auto"
                style={{ background: 'var(--color-code-bg, rgba(0,0,0,0.2))', color: 'var(--color-text-secondary)', fontSize: 11, lineHeight: 1.4, maxHeight: 120, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
              >
                {formatJson(argumentsText)}
              </pre>
            </div>
          )}

          {/* Screenshot thumbnail */}
          {hasScreenshot && toolCall.result && <ScreenshotThumb data={toolCall.result} />}

          {resultText && (
            <div className="mt-1.5">
              <div style={{ color: 'var(--color-text-tertiary)', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>
                result
              </div>
              <pre
                className="p-1.5 rounded overflow-auto"
                style={{ background: 'var(--color-code-bg, rgba(0,0,0,0.2))', color: 'var(--color-text-secondary)', fontSize: 11, lineHeight: 1.4, maxHeight: 180, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
              >
                {resultText}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}
