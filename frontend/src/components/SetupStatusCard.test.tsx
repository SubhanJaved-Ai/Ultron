import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  SetupStatusCard,
  classifySetupError,
} from './SetupStatusCard';
import type { SetupStatus } from '../lib/api';

describe('classifySetupError', () => {
  it('identifies 401 and rejected key as credential error', () => {
    const status: SetupStatus = {
      phase: 'credential_invalid',
      detail: 'Auth check failed',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'HTTP 401: API key was rejected or revoked by provider.',
      source: 'custom',
      requires_source: false,
      requires_credential: true,
      credential_provider: 'gemini',
    };

    const classified = classifySetupError(status);
    expect(classified.category).toBe('credential');
    expect(classified.title).toBe('API Key Rejected or Missing');
    expect(classified.canUpdateKey).toBe(true);
    expect(classified.canChangeProvider).toBe(true);
    expect(classified.canRetry).toBe(false);
    expect(classified.recommendation).toContain('Google AI Studio');
  });

  it('identifies network errors and connection timeouts distinctly', () => {
    const status: SetupStatus = {
      phase: 'network_error',
      detail: 'Connecting...',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'ConnectError: Connection timed out to generativelanguage.googleapis.com',
      source: 'custom',
      requires_source: false,
      requires_credential: false,
      credential_provider: 'gemini',
    };

    const classified = classifySetupError(status);
    expect(classified.category).toBe('network');
    expect(classified.title).toBe('Connection Timed Out');
    expect(classified.canRetry).toBe(true);
    expect(classified.canUpdateKey).toBe(false);
    expect(classified.canChangeProvider).toBe(true);
    expect(classified.recommendation).toContain('internet connection');
  });

  it('identifies provider rate limiting and busy states (429/503)', () => {
    const status: SetupStatus = {
      phase: 'provider_busy',
      detail: 'Waiting for capacity...',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'HTTP 429: Rate limit exceeded or quota reached.',
      source: 'custom',
      requires_source: false,
      requires_credential: false,
      credential_provider: 'gemini',
    };

    const classified = classifySetupError(status);
    expect(classified.category).toBe('rate_limit');
    expect(classified.title).toBe('Provider Temporarily Busy');
    expect(classified.canRetry).toBe(true);
    expect(classified.canUpdateKey).toBe(false);
    expect(classified.canChangeProvider).toBe(true);
    expect(classified.recommendation).toContain('Wait a moment');
  });

  it('identifies 404 model not found or invalid endpoint', () => {
    const status: SetupStatus = {
      phase: 'starting',
      detail: 'Probing...',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'HTTP 404: The requested model does not exist or endpoint is unsupported.',
      source: 'custom',
      requires_source: false,
      requires_credential: false,
      credential_provider: 'custom',
    };

    const classified = classifySetupError(status);
    expect(classified.category).toBe('endpoint');
    expect(classified.title).toBe('Model or Endpoint Not Supported');
    expect(classified.canChangeProvider).toBe(true);
    expect(classified.recommendation).toContain('Switch to a supported model');
  });

  it('defaults to backend service error for process failures', () => {
    const status: SetupStatus = {
      phase: 'failed',
      detail: 'Failed to start',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'Child process exited with code 1. Stderr: Failed to bind to port 8000',
      source: 'ollama',
      requires_source: false,
      requires_credential: false,
    };

    const classified = classifySetupError(status);
    expect(classified.category).toBe('backend');
    expect(classified.title).toBe('Backend Service Startup Error');
    expect(classified.canRetry).toBe(true);
    expect(classified.canChangeProvider).toBe(true);
  });
});

describe('SetupStatusCard component rendering', () => {
  it('renders credential error with Update API Key and Change Provider buttons', () => {
    const status: SetupStatus = {
      phase: 'credential_invalid',
      detail: 'Rejected key',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: 'HTTP 401: API key was rejected or revoked by provider.',
      source: 'custom',
      requires_source: false,
      requires_credential: true,
      credential_provider: 'gemini',
    };

    const html = renderToStaticMarkup(
      <SetupStatusCard
        status={status}
        onRetry={vi.fn()}
        onUpdateCredential={vi.fn()}
        onChangeProvider={vi.fn()}
      />,
    );

    expect(html).toContain('API Key Rejected or Missing');
    expect(html).toContain('Recommended action:');
    expect(html).toContain('Update API Key');
    expect(html).toContain('Change Provider');
    expect(html).not.toContain('Retry Connection');
  });

  it('redacts sensitive API keys from diagnostic details', () => {
    const rawKey = 'AIzaSyA_REAL_SENSITIVE_KEY_1234567890';
    const status: SetupStatus = {
      phase: 'credential_invalid',
      detail: 'Rejected key',
      ollama_ready: false,
      server_ready: false,
      model_ready: false,
      error: `Failed with Bearer ${rawKey} on endpoint https://googleapis.com/?key=${rawKey}`,
      source: 'custom',
      requires_source: false,
      requires_credential: true,
      credential_provider: 'gemini',
    };

    const html = renderToStaticMarkup(
      <SetupStatusCard
        status={status}
        onChangeProvider={vi.fn()}
      />,
    );

    // Raw key should never appear anywhere in the rendered HTML
    expect(html).not.toContain(rawKey);
    expect(html).toContain('Show diagnostic details');
  });
});
