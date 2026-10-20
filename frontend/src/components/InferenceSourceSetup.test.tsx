import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  CredentialRecoveryCard,
  CustomEndpointSetup,
  GeminiSetup,
  InferenceRecoveryButton,
  InferenceSourceChooser,
  OllamaConsent,
  ProviderBusyCard,
  inferenceSetupReducer,
  persistAndStartInferenceSource,
  type InferenceSourceSubmission,
} from './InferenceSourceSetup';

describe('first-run inference source navigation', () => {
  it('requires a second, explicit confirmation before local setup', () => {
    expect(inferenceSetupReducer('choose', 'choose_ollama')).toBe('ollama');
    expect(inferenceSetupReducer('ollama', 'back')).toBe('choose');
  });

  it('navigates to Google Gemini cloud setup and back safely', () => {
    expect(inferenceSetupReducer('choose', 'choose_gemini')).toBe('gemini');
    expect(inferenceSetupReducer('gemini', 'back')).toBe('choose');
  });

  it('lets custom endpoint setup cancel safely back to the chooser', () => {
    expect(inferenceSetupReducer('choose', 'choose_custom')).toBe('custom');
    expect(inferenceSetupReducer('custom', 'back')).toBe('choose');
  });

  it('renders all three provider options without claiming any has started', () => {
    const html = renderToStaticMarkup(<InferenceSourceChooser onChoose={vi.fn()} />);

    expect(html).toContain('Local Ollama');
    expect(html).toContain('Google Gemini');
    expect(html).toContain('OpenAI-compatible server');
    expect(html).toContain('Nothing is installed, started, or downloaded until you confirm');
    expect(html).not.toContain('Starting local setup');
  });

  it('discloses the model download and offers a no-op back path', () => {
    const html = renderToStaticMarkup(
      <OllamaConsent onBack={vi.fn()} onConfirm={vi.fn()} />,
    );

    expect(html).toContain('may download one model');
    expect(html).toContain('several gigabytes');
    expect(html).toContain('Going back leaves Ollama stopped');
    expect(html).toContain('Use Ollama and continue');
    expect(html).toContain('Back');
  });

  it('renders explicit Google Gemini setup with official endpoint and model defaults', () => {
    const html = renderToStaticMarkup(
      <GeminiSetup onCancel={vi.fn()} onConfirm={vi.fn()} />,
    );

    expect(html).toContain('Connect Google Gemini');
    expect(html).toContain('https://generativelanguage.googleapis.com/v1beta/openai/');
    expect(html).toContain('gemini-3.8-flash');
    expect(html).toMatch(/aria-label="API key"[^>]*required/);
    expect(html).toMatch(/aria-label="Model ID"[^>]*required/);
    expect(html).toMatch(/aria-label="Server URL"[^>]*required/);
    expect(html).toContain('Windows Credential Manager');
    expect(html).toContain('Cancel');
  });

  it('requires endpoint coordinates and keeps Google Gemini in server type dropdown', () => {
    const html = renderToStaticMarkup(
      <CustomEndpointSetup onCancel={vi.fn()} onConfirm={vi.fn()} />,
    );

    expect(html).toContain('Server URL');
    expect(html).toContain('Model ID');
    expect(html).toContain('Google Gemini');
    expect(html).toContain('LM Studio');
    expect(html).toContain('vLLM');
    expect(html).toMatch(/aria-label="Server URL"[^>]*required/);
    expect(html).toMatch(/aria-label="Model ID"[^>]*required/);
    expect(html).toContain('Ollama will not start or download models');
    expect(html).toContain('Cancel');
  });

  it('renders a source-change recovery action with a guarded busy state', () => {
    const ready = renderToStaticMarkup(
      <InferenceRecoveryButton recovering={false} onChange={vi.fn()} />,
    );
    const stopping = renderToStaticMarkup(
      <InferenceRecoveryButton recovering onChange={vi.fn()} />,
    );

    expect(ready).toContain('Change inference source');
    expect(ready).not.toMatch(/ disabled(?:=""|>)/);
    expect(stopping).toContain('Stopping setup...');
    expect(stopping).toMatch(/ disabled(?:=""|>)/);
  });
});

describe('first-run inference source persistence', () => {
  it('persists the exact choice before requesting backend startup', async () => {
    const calls: string[] = [];
    const persist = vi.fn(async (source: InferenceSourceSubmission) => {
      calls.push(`persist:${source.kind}`);
    });
    const start = vi.fn(async () => {
      calls.push('start');
    });

    await persistAndStartInferenceSource(
      { kind: 'custom', host: 'http://localhost:1234', model: 'local-model', engine: 'lmstudio' },
      persist,
      start,
    );

    expect(calls).toEqual(['persist:custom', 'start']);
    expect(persist).toHaveBeenCalledWith({
      kind: 'custom',
      host: 'http://localhost:1234',
      model: 'local-model',
      engine: 'lmstudio',
    });
  });

  it('persists Google Gemini endpoint selection with api key', async () => {
    const persist = vi.fn(async () => {});
    const start = vi.fn(async () => {});

    await persistAndStartInferenceSource(
      {
        kind: 'custom',
        host: 'https://generativelanguage.googleapis.com/v1beta/openai/',
        model: 'gemini-3.8-flash',
        engine: 'gemini',
        apiKey: 'test-gemini-key',
      },
      persist,
      start,
    );

    expect(persist).toHaveBeenCalledWith({
      kind: 'custom',
      host: 'https://generativelanguage.googleapis.com/v1beta/openai/',
      model: 'gemini-3.8-flash',
      engine: 'gemini',
      apiKey: 'test-gemini-key',
    });
    expect(start).toHaveBeenCalled();
  });

  it('does not start anything when persistence fails', async () => {
    const persist = vi.fn(async () => {
      throw new Error('secure storage unavailable');
    });
    const start = vi.fn(async () => {});

    await expect(
      persistAndStartInferenceSource({ kind: 'ollama' }, persist, start),
    ).rejects.toThrow('secure storage unavailable');
    expect(start).not.toHaveBeenCalled();
  });

  it('rolls a staged choice back when startup rejects', async () => {
    const calls: string[] = [];
    const persist = vi.fn(async () => {
      calls.push('persist');
    });
    const start = vi.fn(async () => {
      calls.push('start');
      throw new Error('endpoint unavailable');
    });
    const rollback = vi.fn(async () => {
      calls.push('rollback');
    });

    await expect(
      persistAndStartInferenceSource(
        { kind: 'custom', host: 'http://localhost:1234', model: 'missing' },
        persist,
        start,
        rollback,
      ),
    ).rejects.toThrow('endpoint unavailable');
    expect(calls).toEqual(['persist', 'start', 'rollback']);
  });
});

describe('credential recovery card', () => {
  it('renders Google Gemini recovery details with masked input and error alert', () => {
    const html = renderToStaticMarkup(
      <CredentialRecoveryCard
        provider="gemini"
        keyName="GEMINI_API_KEY"
        savedModel="gemini-3.8-flash"
        savedHost="https://generativelanguage.googleapis.com/v1beta/openai"
        error="Authentication failed: your API key is invalid or has been revoked."
        onSubmit={vi.fn()}
        onResetSource={vi.fn()}
      />,
    );

    expect(html).toContain('Update Google Gemini API Key');
    expect(html).toContain('Configured model:');
    expect(html).toContain('gemini-3.8-flash');
    expect(html).toContain('Authentication failed: your API key is invalid or has been revoked.');
    expect(html).toMatch(/aria-label="Replacement API key"[^>]*type="password"/);
    expect(html).toMatch(/aria-label="Replacement API key"[^>]*placeholder="AIzaSy\.\.\."/);
    expect(html).toContain('Update Key &amp; Connect');
    expect(html).toContain('Change inference source');
  });

  it('renders general provider recovery details when non-gemini provider requires key', () => {
    const html = renderToStaticMarkup(
      <CredentialRecoveryCard
        provider="openai"
        keyName="OPENAI_API_KEY"
        savedModel="gpt-4o"
        error="An API key is required to connect to openai."
        onSubmit={vi.fn()}
        onResetSource={vi.fn()}
      />,
    );

    expect(html).toContain('Update Openai API Key');
    expect(html).toContain('gpt-4o');
    expect(html).toContain('An API key is required to connect to openai.');
    expect(html).toMatch(/aria-label="Replacement API key"[^>]*placeholder="sk-\.\.\."/);
  });
});

describe('provider busy card', () => {
  it('renders temporary provider failure card and preserves retry path without reset', () => {
    const html = renderToStaticMarkup(
      <ProviderBusyCard
        provider="gemini"
        error="The inference provider is temporarily unavailable (HTTP 503)."
        onRetry={vi.fn()}
        onResetSource={vi.fn()}
      />,
    );

    expect(html).toContain('Google Gemini Temporarily Unavailable');
    expect(html).toContain('Your configuration has been safely preserved.');
    expect(html).toContain('HTTP 503');
    expect(html).toContain('Retry Connection');
    expect(html).toContain('Change inference source');
  });
});
