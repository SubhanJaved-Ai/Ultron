import { useRef, useEffect, useState } from 'react';
import { Copy, Trash2, Wrench, MessageSquare, Cpu, Search, CheckCircle2 } from 'lucide-react';
import { useAppStore } from '../lib/store';

const LEVEL_COLORS: Record<string, string> = {
  info: 'var(--color-text)',
  warn: 'var(--color-warning)',
  error: 'var(--color-error)',
};

const CATEGORY_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  tool: {
    label: 'TOOL · REAL EXECUTION',
    color: 'var(--color-accent)',
    bg: 'var(--color-accent-subtle)',
  },
  chat: {
    label: 'CHAT',
    color: 'var(--color-text-secondary)',
    bg: 'transparent',
  },
  server: {
    label: 'SERVER',
    color: 'var(--color-text-tertiary)',
    bg: 'transparent',
  },
  model: {
    label: 'MODEL',
    color: 'var(--color-success)',
    bg: 'rgba(16, 185, 129, 0.1)',
  },
};

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function LogsPage() {
  const logEntries = useAppStore((s) => s.logEntries);
  const clearLogs = useAppStore((s) => s.clearLogs);
  const [filter, setFilter] = useState<'all' | 'tool' | 'chat' | 'server'>('all');
  const bottomRef = useRef<HTMLDivElement>(null);

  const toolCount = logEntries.filter((e) => e.category === 'tool').length;
  const chatCount = logEntries.filter((e) => e.category === 'chat').length;
  const serverCount = logEntries.filter((e) => e.category === 'server').length;

  const filteredEntries = logEntries.filter(
    (e) => filter === 'all' || e.category === filter,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [filteredEntries.length]);

  const handleCopy = async () => {
    const text = filteredEntries
      .map((e) => `${formatTime(e.timestamp)} [${e.level}] [${e.category}] ${e.message}`)
      .join('\n');
    await navigator.clipboard.writeText(text);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden px-6 py-10">
      <div className="max-w-4xl mx-auto w-full flex flex-col flex-1 overflow-hidden">
        <header className="mb-4 shrink-0">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
              Session Logs & Audits
            </h1>
            <div className="flex items-center gap-2">
              <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                {filteredEntries.length} of {logEntries.length} entries
              </span>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
              >
                <Copy size={12} /> Copy All
              </button>
              <button
                onClick={clearLogs}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }}
              >
                <Trash2 size={12} /> Clear
              </button>
            </div>
          </div>
          <p className="text-sm mt-1 max-w-2xl" style={{ color: 'var(--color-text-secondary)' }}>
            Real-time audit log of model dispatches, browser actions, and live tool executions.
          </p>

          {/* Filter tabs */}
          <div className="flex items-center gap-2 mt-4">
            <button
              onClick={() => setFilter('all')}
              className="px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer"
              style={{
                background: filter === 'all' ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
                color: filter === 'all' ? 'var(--color-on-accent)' : 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
            >
              All ({logEntries.length})
            </button>
            <button
              onClick={() => setFilter('tool')}
              className="px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              style={{
                background: filter === 'tool' ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
                color: filter === 'tool' ? 'var(--color-on-accent)' : 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
            >
              <Wrench size={11} />
              Tool Executions ({toolCount})
            </button>
            <button
              onClick={() => setFilter('chat')}
              className="px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              style={{
                background: filter === 'chat' ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
                color: filter === 'chat' ? 'var(--color-on-accent)' : 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
            >
              <MessageSquare size={11} />
              Chat ({chatCount})
            </button>
            <button
              onClick={() => setFilter('server')}
              className="px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
              style={{
                background: filter === 'server' ? 'var(--color-accent)' : 'var(--color-bg-secondary)',
                color: filter === 'server' ? 'var(--color-on-accent)' : 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
            >
              <Cpu size={11} />
              Server ({serverCount})
            </button>
          </div>
        </header>

        {/* Log entries */}
        <div
          className="flex-1 overflow-y-auto rounded-xl p-4 font-mono text-xs leading-relaxed"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
        >
          {filteredEntries.length === 0 ? (
            <div className="text-center py-12" style={{ color: 'var(--color-text-tertiary)' }}>
              No log entries match the selected filter.
            </div>
          ) : (
            filteredEntries.map((entry, i) => {
              const isTool = entry.category === 'tool';
              const cfg = CATEGORY_CONFIG[entry.category];
              return (
                <div
                  key={i}
                  className={`py-1 px-1.5 rounded transition-colors ${isTool ? 'my-0.5' : ''}`}
                  style={{
                    background: isTool ? 'rgba(56, 189, 248, 0.04)' : 'transparent',
                    borderLeft: isTool ? '2px solid var(--color-accent)' : '2px solid transparent',
                  }}
                >
                  <span style={{ color: 'var(--color-text-tertiary)' }}>{formatTime(entry.timestamp)}</span>
                  {' '}
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    style={{
                      color: cfg?.color || LEVEL_COLORS[entry.level] || 'var(--color-text)',
                      background: cfg?.bg || 'transparent',
                    }}
                  >
                    [{cfg?.label || entry.category.toUpperCase()}]
                  </span>
                  {' '}
                  <span style={{ color: LEVEL_COLORS[entry.level] || 'var(--color-text)' }}>
                    {entry.message}
                  </span>
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
