import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router';
import {
  MessageSquare,
  Plus,
  BarChart3,
  Settings,
  Search,
  PanelLeftClose,
  PanelLeft,
  Cpu,
  Rocket,
  Bot,
  Sun,
  Moon,
  Monitor,
  Loader2,
  ScrollText,
  Database,
  DollarSign,
  Orbit,
  ListTodo,
  Brain,
} from 'lucide-react';
import { ConversationList } from './ConversationList';
import { useAppStore } from '../../lib/store';
import { calculateModelCost } from '../../lib/model-pricing';

function fmtCost(n: number): string {
  if (n >= 1000) return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n >= 1) return '$' + n.toFixed(2);
  if (n >= 0.01) return '$' + n.toFixed(3);
  if (n > 0) return '$' + n.toFixed(4);
  return '$0.00';
}

function getAllTimeCost(currentSessionCost: number): number {
  try {
    const key = 'openjarvis-alltime-cost';
    const stored = parseFloat(localStorage.getItem(key) || '0');
    const lastSessionKey = 'openjarvis-last-session-cost';
    const lastSession = parseFloat(sessionStorage.getItem(lastSessionKey) || '0');
    const delta = Math.max(0, currentSessionCost - lastSession);
    const updated = stored + delta;
    if (delta > 0) {
      localStorage.setItem(key, updated.toFixed(6));
      sessionStorage.setItem(lastSessionKey, currentSessionCost.toString());
    }
    return updated;
  } catch {
    return currentSessionCost;
  }
}

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState('');

  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const savings = useAppStore((s) => s.savings);
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const modelLoading = useAppStore((s) => s.modelLoading);
  const deepResearch = useAppStore((s) => s.deepResearch);

  const serverModel = typeof serverInfo?.model === 'string' ? serverInfo.model : '';
  const currentSelected = typeof selectedModel === 'string' ? selectedModel : '';
  const isConfirmed =
    !!serverModel &&
    (currentSelected === serverModel || !currentSelected);
  const isPending =
    !!serverModel &&
    !!currentSelected &&
    currentSelected !== serverModel;

  const rawModel = currentSelected || serverModel;
  const activeModelId = rawModel || 'Local Model';
  const promptTokens = savings?.total_prompt_tokens ?? 0;
  const completionTokens = savings?.total_completion_tokens ?? 0;
  const costResult = calculateModelCost(activeModelId, promptTokens, completionTokens, savings?.local_cost ?? 0);
  const sessionCost = costResult.cost;

  const allTimeCost = getAllTimeCost(sessionCost);

  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);

  const ThemeIcon = settings.theme === 'light' ? Sun : settings.theme === 'dark' ? Moon : Monitor;
  const nextTheme = settings.theme === 'light' ? 'dark' : settings.theme === 'dark' ? 'system' : 'light';

  const messages = useAppStore((s) => s.messages);
  const handleNewChat = () => {
    // Don't create a new chat if the current one is empty
    if (messages.length === 0) {
      navigate('/');
      return;
    }
    createConversation(selectedModel);
    navigate('/');
  };

  const navItems = [
    { path: '/', icon: MessageSquare, label: 'Chat' },
    { path: '/tasks', icon: ListTodo, label: 'Tasks' },
    { path: '/memory-skills', icon: Brain, label: 'Memory & Skills' },
    { path: '/hologram', icon: Orbit, label: '3D Hologram' },
    { path: '/dashboard', icon: BarChart3, label: 'Dashboard' },
    { path: '/data-sources', icon: Database, label: 'Data Sources' },
    { path: '/agents', icon: Bot, label: 'Agents' },
    { path: '/logs', icon: ScrollText, label: 'Logs' },
    { path: '/settings', icon: Settings, label: 'Settings' },
    { path: '/get-started', icon: Rocket, label: 'Get Started' },
  ];

  return (
    <>
      {/* Collapse button when sidebar is closed */}
      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="fixed top-3 left-3 z-30 p-2 rounded-lg transition-colors cursor-pointer"
          style={{ color: 'var(--color-text-secondary)', background: 'var(--color-bg-secondary)' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
        >
          <PanelLeft size={18} />
        </button>
      )}

      <aside
        className={`
          flex flex-col h-full shrink-0 transition-all duration-200 ease-in-out overflow-hidden
          fixed md:relative z-30
          ${sidebarOpen ? 'w-[260px]' : 'w-0'}
        `}
        style={{
          background: 'var(--color-sidebar)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderRight: sidebarOpen ? '1px solid var(--color-border)' : 'none',
        }}
      >
        <div className="flex flex-col h-full w-[260px]">
          {/* Header */}
          <div className="flex items-center justify-between px-3 pt-3 pb-2">
            <button
              onClick={toggleSidebar}
              className="p-2 rounded-lg transition-colors cursor-pointer"
              style={{ color: 'var(--color-text-secondary)' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <PanelLeftClose size={18} />
            </button>
            <div className="flex items-center gap-1">
              <button
                onClick={() => updateSettings({ theme: nextTheme })}
                className="p-2 rounded-lg transition-colors cursor-pointer"
                style={{ color: 'var(--color-text-secondary)' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                title={`Theme: ${settings.theme} (click for ${nextTheme})`}
              >
                <ThemeIcon size={16} />
              </button>
              <button
                onClick={handleNewChat}
                className="p-2 rounded-lg transition-colors cursor-pointer"
                style={{ color: 'var(--color-text-secondary)' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                title="New chat"
              >
                <Plus size={18} />
              </button>
            </div>
          </div>

          {/* Model badge (Phase 3A: with live connection status dot) */}
          <button
            onClick={() => setCommandPaletteOpen(true)}
            className="mx-3 mb-1.5 flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors cursor-pointer"
            style={{
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text-secondary)',
              border: '1px solid var(--color-border)',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
          >
            {modelLoading ? (
              <Loader2 size={14} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
            ) : (
              <Cpu size={14} />
            )}
            <div className="flex-1 min-w-0 flex items-center gap-1.5">
              <span
                className="truncate block text-left"
                style={{ color: deepResearch ? 'var(--color-accent)' : 'var(--color-text)' }}
              >
                {deepResearch
                  ? 'Deep Research'
                  : currentSelected || serverModel || 'Select model'}
              </span>
              {!modelLoading && (
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{
                    background: isConfirmed ? '#10b981' : isPending ? '#f59e0b' : 'var(--color-text-tertiary)',
                    boxShadow: isConfirmed
                      ? '0 0 5px rgba(16, 185, 129, 0.6)'
                      : isPending
                      ? '0 0 5px rgba(245, 158, 11, 0.6)'
                      : 'none',
                  }}
                  title={
                    isConfirmed
                      ? `Active & Confirmed (${serverModel})`
                      : isPending
                      ? `Selected: ${currentSelected} (Server: ${serverModel || 'unknown'})`
                      : 'Connecting to server...'
                  }
                />
              )}
              {modelLoading && (
                <span className="text-[10px] block text-left" style={{ color: 'var(--color-accent)' }}>
                  Loading...
                </span>
              )}
            </div>
            {!modelLoading && (
              <kbd
                className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-tertiary)' }}
              >
                ⌘K
              </kbd>
            )}
          </button>

          {/* Cost summary badge (Phase 3B) */}
          <div
            onClick={() => navigate('/dashboard')}
            className="mx-3 mb-2 px-2.5 py-1.5 rounded-lg flex items-center justify-between text-xs transition-colors cursor-pointer"
            style={{
              background: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border)',
            }}
            title="Click to view full telemetry & savings dashboard"
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
          >
            <div className="flex items-center gap-1.5" style={{ color: 'var(--color-text-tertiary)' }}>
              <DollarSign size={12} style={{ color: 'var(--color-success)' }} />
              <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>Cost</span>
            </div>
            <div className="flex items-center gap-2 font-mono text-[10.5px]">
              <span title="Session cost" style={{ color: 'var(--color-text-secondary)' }}>
                Sess: <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>{fmtCost(sessionCost)}</span>
              </span>
              <span style={{ color: 'var(--color-border)' }}>|</span>
              <span title="All-time cumulative cost" style={{ color: 'var(--color-text-secondary)' }}>
                All: <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>{fmtCost(allTimeCost)}</span>
              </span>
            </div>
          </div>

          {/* Search */}
          <div className="px-3 mb-2">
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
            >
              <Search size={14} style={{ color: 'var(--color-text-tertiary)' }} />
              <input
                type="text"
                placeholder="Search chats..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-transparent outline-none text-sm"
                style={{ color: 'var(--color-text)' }}
              />
            </div>
          </div>

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto px-2">
            <ConversationList searchQuery={searchQuery} />
          </div>

          {/* Bottom nav */}
          <nav className="px-2 pb-3 pt-2 flex flex-col gap-0.5" style={{ borderTop: '1px solid var(--color-border)' }}>
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className="relative flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors w-full text-left cursor-pointer"
                  style={{
                    background: isActive ? 'var(--color-accent-subtle)' : 'transparent',
                    color: isActive ? 'var(--color-text)' : 'var(--color-text-secondary)',
                    fontWeight: isActive ? 500 : 400,
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.background = 'var(--color-bg-secondary)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  {isActive && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full"
                      style={{
                        background: 'var(--color-accent)',
                        boxShadow: '0 0 8px var(--color-accent-glow)',
                      }}
                    />
                  )}
                  <item.icon size={16} style={isActive ? { color: 'var(--color-accent)' } : undefined} />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>
      </aside>
    </>
  );
}
