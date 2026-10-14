import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ModelInfo } from '../types';

class MemoryStorage {
  private store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

const model = (id: string): ModelInfo => ({
  id,
  object: 'model',
  created: 0,
  owned_by: 'openjarvis',
});

beforeEach(() => {
  vi.resetModules();
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage =
    new MemoryStorage();
});

afterEach(() => {
  (globalThis as unknown as { localStorage?: MemoryStorage }).localStorage =
    undefined;
});

describe('setModels', () => {
  it('does not select an embedding-only model', async () => {
    const { useAppStore } = await import('./store');

    useAppStore.getState().setModels([model('nomic-embed-text')]);

    expect(useAppStore.getState().selectedModel).toBe('');
  });

  it('clears a missing selection when no chat fallback exists', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('deleted-chat-model');

    useAppStore.getState().setModels([model('nomic-embed-text')]);

    expect(useAppStore.getState().selectedModel).toBe('');
  });

  it('replaces an embedding selection with an available chat model', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('all-minilm:latest');

    useAppStore.getState().setModels([
      model('all-minilm:latest'),
      model('qwen3.5:4b'),
    ]);

    expect(useAppStore.getState().selectedModel).toBe('qwen3.5:4b');
  });
});

describe('setServerInfo model synchronization', () => {
  it('synchronizes selectedModel when empty', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('');

    useAppStore.getState().setServerInfo({
      model: 'gemini-3.8-flash',
      engine: 'gemini',
      agent: 'jarvis',
    });

    expect(useAppStore.getState().selectedModel).toBe('gemini-3.8-flash');
  });

  it('migrates stale gemini-2.5 selection when server engine is gemini', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('gemini-2.5-flash');

    useAppStore.getState().setServerInfo({
      model: 'gemini-3.8-flash',
      engine: 'gemini',
      agent: 'jarvis',
    });

    expect(useAppStore.getState().selectedModel).toBe('gemini-3.8-flash');
  });

  it('preserves user selection when non-gemini or custom model is active', async () => {
    const { useAppStore } = await import('./store');
    useAppStore.getState().setSelectedModel('custom-llm-model');

    useAppStore.getState().setServerInfo({
      model: 'qwen3.5:4b',
      engine: 'ollama',
      agent: 'jarvis',
    });

    expect(useAppStore.getState().selectedModel).toBe('custom-llm-model');
  });
});
