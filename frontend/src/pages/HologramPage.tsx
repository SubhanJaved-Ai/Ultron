import { useNavigate } from 'react-router';
import { MessageSquare, Orbit, ArrowLeft, Radio, Sparkles } from 'lucide-react';
import { getBase } from '../lib/api';

export function HologramPage() {
  const navigate = useNavigate();
  const apiBase = getBase();
  const hologramUrl = `${apiBase}/hologram`;

  return (
    <div className="flex flex-col h-full w-full bg-[#02050c] text-slate-100 overflow-hidden relative">
      {/* Top Floating Glassmorphic Nav */}
      <header
        className="flex items-center justify-between px-4 py-2.5 z-20 shrink-0"
        style={{
          background: 'rgba(6, 8, 14, 0.75)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(56, 189, 248, 0.2)',
          boxShadow: '0 4px 24px rgba(0, 0, 0, 0.5)',
        }}
      >
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              color: 'var(--color-text-secondary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.12)';
              e.currentTarget.style.color = '#fff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)';
              e.currentTarget.style.color = 'var(--color-text-secondary)';
            }}
            title="Return to standard chat interface"
          >
            <ArrowLeft size={13} />
            <span>Chat</span>
          </button>

          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full animate-ping"
              style={{ background: '#38bdf8' }}
            />
            <span
              className="text-xs font-semibold uppercase tracking-wider font-mono"
              style={{ color: '#38bdf8', letterSpacing: '0.1em' }}
            >
              Ultron 3D Matrix
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono"
            style={{
              background: 'rgba(16, 185, 129, 0.12)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              color: '#10b981',
            }}
          >
            <Radio size={11} className="animate-pulse" />
            <span>Voice & Audio Reactive</span>
          </div>

          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer"
            style={{
              background: 'rgba(56, 189, 248, 0.15)',
              border: '1px solid rgba(56, 189, 248, 0.4)',
              color: '#38bdf8',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(56, 189, 248, 0.25)';
              e.currentTarget.style.boxShadow = '0 0 14px rgba(56, 189, 248, 0.4)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(56, 189, 248, 0.15)';
              e.currentTarget.style.boxShadow = 'none';
            }}
            title="Switch back to Chat interface"
          >
            <MessageSquare size={13} />
            <span>Switch to Chat</span>
          </button>
        </div>
      </header>

      {/* Hologram Matrix Canvas Viewport */}
      <div className="flex-1 w-full h-full relative overflow-hidden bg-[#02050c]">
        <iframe
          src={hologramUrl}
          title="Ultron 3D Quantum Hologram"
          className="w-full h-full border-0 absolute inset-0"
          allow="microphone; camera; display-capture; autoplay"
          style={{ width: '100%', height: '100%' }}
        />
      </div>
    </div>
  );
}
