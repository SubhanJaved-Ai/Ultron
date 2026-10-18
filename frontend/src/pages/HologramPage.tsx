import { useNavigate } from 'react-router';
import { MessageSquare, Orbit, ArrowLeft, Radio, Sparkles, ExternalLink } from 'lucide-react';
import { getBase } from '../lib/api';

export function HologramPage() {
  const navigate = useNavigate();
  const apiBase = getBase();
  const hologramUrl = `${apiBase}/hologram.html`;

  return (
    <div className="flex flex-col h-full w-full bg-[#f8fafc] text-slate-800 overflow-hidden relative">
      {/* Top Floating Glassmorphic Nav */}
      <header
        className="flex items-center justify-between px-4 py-2.5 z-20 shrink-0"
        style={{
          background: 'rgba(255, 255, 255, 0.85)',
          backdropFilter: 'blur(20px)',
          borderBottom: '1px solid rgba(226, 232, 240, 0.8)',
          boxShadow: '0 4px 20px rgba(15, 23, 42, 0.05)',
        }}
      >
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer"
            style={{
              background: 'rgba(241, 245, 249, 0.85)',
              border: '1px solid rgba(203, 213, 225, 0.7)',
              color: '#334155',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#ffffff';
              e.currentTarget.style.color = '#0f172a';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(241, 245, 249, 0.85)';
              e.currentTarget.style.color = '#334155';
            }}
            title="Return to standard chat interface"
          >
            <ArrowLeft size={13} />
            <span>Chat</span>
          </button>

          <div className="flex items-center gap-2">
            <span
              className="w-2 h-2 rounded-full animate-ping"
              style={{ background: '#0284c7' }}
            />
            <span
              className="text-xs font-semibold uppercase tracking-wider font-mono"
              style={{ color: '#0284c7', letterSpacing: '0.1em' }}
            >
              Ultron 3D Matrix
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono"
            style={{
              background: 'rgba(5, 150, 105, 0.1)',
              border: '1px solid rgba(5, 150, 105, 0.3)',
              color: '#059669',
            }}
          >
            <Radio size={11} className="animate-pulse" />
            <span>Voice & Audio Reactive</span>
          </div>

          <a
            href={hologramUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer"
            style={{
              background: 'rgba(255, 255, 255, 0.9)',
              border: '1px solid rgba(203, 213, 225, 0.7)',
              color: '#1e293b',
              boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#ffffff';
              e.currentTarget.style.boxShadow = '0 2px 6px rgba(15, 23, 42, 0.08)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.9)';
              e.currentTarget.style.boxShadow = '0 1px 2px rgba(15, 23, 42, 0.04)';
            }}
            title="Open 3D Hologram in full browser window"
          >
            <ExternalLink size={13} />
            <span>Open Fullscreen</span>
          </a>

          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer"
            style={{
              background: 'rgba(2, 132, 199, 0.1)',
              border: '1px solid rgba(2, 132, 199, 0.3)',
              color: '#0284c7',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(2, 132, 199, 0.18)';
              e.currentTarget.style.boxShadow = '0 0 12px rgba(2, 132, 199, 0.25)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(2, 132, 199, 0.1)';
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
      <div className="flex-1 w-full h-full relative overflow-hidden bg-[#f8fafc]">
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
