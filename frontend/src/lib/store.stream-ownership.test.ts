import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class MemoryStorage {
  private store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }
}

beforeEach(() => {
  vi.resetModules();
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage =
    new MemoryStorage();
});

afterEach(() => {
  (globalThis as unknown as { localStorage?: MemoryStorage }).localStorage =
    undefined;
});

async function freshStore() {
  return (await import('./store')).useAppStore;
}

describe('conversation stream ownership', () => {
  it('persists background stream updates without replacing the active messages', async () => {
    const store = await freshStore();
    const sourceId = store.getState().createConversation('test-model');
    store.getState().addMessage(sourceId, {
      id: 'assistant',
      role: 'assistant',
      content: '',
      timestamp: 1,
    });

    const activeId = store.getState().createConversation('test-model');
    store.getState().setStreamState({
      conversationId: sourceId,
      isStreaming: true,
      content: 'streamed response',
    });
    store.getState().updateLastAssistant(sourceId, 'streamed response');

    expect(store.getState().activeId).toBe(activeId);
    expect(store.getState().messages).toEqual([]);

    store.getState().selectConversation(sourceId);
    expect(store.getState().messages).toHaveLength(1);
    expect(store.getState().messages[0].content).toBe('streamed response');
  });

  it('keeps the stream-owning conversation until generation stops', async () => {
    const store = await freshStore();
    const sourceId = store.getState().createConversation('test-model');
    const activeId = store.getState().createConversation('test-model');
    store.getState().setStreamState({
      conversationId: sourceId,
      isStreaming: true,
    });

    store.getState().deleteConversation(sourceId);
    expect(
      store.getState().conversations.map((conversation) => conversation.id),
    ).toContain(sourceId);
    expect(store.getState().activeId).toBe(activeId);

    store.getState().resetStream();
    store.getState().deleteConversation(sourceId);
    expect(
      store.getState().conversations.map((conversation) => conversation.id),
    ).not.toContain(sourceId);
  });

  it('defers synchronous localStorage disk writes during streaming chunks', async () => {
    const storeModule = await import('./store');
    const store = storeModule.useAppStore;
    const convId = store.getState().createConversation('test-model');
    store.getState().addMessage(convId, {
      id: 'assistant-live',
      role: 'assistant',
      content: '',
      timestamp: 1,
    });

    const setItemSpy = vi.spyOn(localStorage, 'setItem');
    setItemSpy.mockClear();

    // Simulate 20 fast streaming token flushes
    for (let i = 1; i <= 20; i++) {
      store.getState().updateLastAssistant(convId, `token ${i}`, undefined, undefined, undefined, undefined, undefined, undefined, false);
    }

    // Must NOT have written to localStorage 20 times!
    expect(setItemSpy).not.toHaveBeenCalled();

    // Active in-memory state is immediately updated
    expect(store.getState().messages[0].content).toBe('token 20');

    // Final completion flush writes immediately to disk
    store.getState().updateLastAssistant(convId, 'token 20 final', undefined, undefined, undefined, undefined, undefined, undefined, true);
    expect(setItemSpy).toHaveBeenCalledTimes(1);

    const stored = JSON.parse(localStorage.getItem('openjarvis-conversations')!);
    expect(stored.conversations[convId].messages[0].content).toBe('token 20 final');
  });
});
