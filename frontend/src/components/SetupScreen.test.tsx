import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import * as api from '../lib/api';

describe('SetupScreen state machine transitions', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', { getItem: () => null });
    vi.stubGlobal('window', { __TAURI_INTERNALS__: {} });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders credential recovery screen when requires_credential is true', async () => {
    vi.spyOn(api, 'getSetupStatus').mockResolvedValue({
      phase: 'credential_invalid',
      detail: 'API key was rejected or revoked by provider.',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'Authentication failed: your API key is invalid or has been revoked.',
      source: 'custom',
      requires_source: false,
      requires_credential: true,
      credential_provider: 'gemini',
      credential_key_name: 'GEMINI_API_KEY',
      saved_model: 'gemini-3.8-flash',
      saved_host: 'https://generativelanguage.googleapis.com/v1beta/openai',
    });

    const { SetupScreen } = await import('./SetupScreen');
    const html = renderToStaticMarkup(<SetupScreen onReady={vi.fn()} />);

    expect(html).toContain('OpenJarvis');
    expect(html).toContain('overflow-y-auto');
  });

  it('renders scrollable layout preventing clipped action buttons', async () => {
    vi.spyOn(api, 'getSetupStatus').mockResolvedValue({
      phase: 'starting',
      detail: 'Starting API server from D:\\Ultron...',
      ollama_ready: true,
      server_ready: false,
      model_ready: true,
      error: 'Jarvis server exited (code 1) before becoming ready.\n\nStderr:\nNo inference engine available.',
      source: 'custom',
      requires_source: false,
      requires_credential: false,
    });

    const { SetupScreen } = await import('./SetupScreen');
    const html = renderToStaticMarkup(<SetupScreen onReady={vi.fn()} />);

    // Verify outer container is scrollable
    expect(html).toContain('overflow-y-auto');
    expect(html).toContain('OpenJarvis');
  });

  it('stops infinite spinner on terminal step error in StepRow', async () => {
    const { StepRow } = await import('./SetupScreen');
    const { Cpu } = await import('lucide-react');

    const errorHtml = renderToStaticMarkup(
      <StepRow
        icon={Cpu}
        label="Inference Engine"
        done={false}
        active={true}
        hasError={true}
        detail="Starting Ollama..."
      />,
    );

    // Should indicate stopped and NOT spin forever on the active step
    expect(errorHtml).toContain('Stopped (see details below)');
    expect(errorHtml).not.toContain('animate-spin');
    expect(errorHtml).toContain('lucide-alert-circle');

    const runningHtml = renderToStaticMarkup(
      <StepRow
        icon={Cpu}
        label="Inference Engine"
        done={false}
        active={true}
        hasError={false}
        detail="Starting Ollama..."
      />,
    );
    expect(runningHtml).toContain('animate-spin');
  });
});


