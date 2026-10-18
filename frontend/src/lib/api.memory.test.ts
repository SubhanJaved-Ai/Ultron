import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.fn<typeof fetch>();

class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('VITE_API_URL', '');
  fetchMock.mockReset();
  globalThis.fetch = fetchMock;
  (globalThis as unknown as { localStorage: MemoryStorage }).localStorage = new MemoryStorage();
});

afterEach(() => {
  vi.unstubAllEnvs();
  (globalThis as unknown as { localStorage?: MemoryStorage }).localStorage = undefined;
});

describe('getMemoryStats', () => {
  it('shows the server detail and HTTP status for a backend failure', async () => {
    fetchMock.mockResolvedValue(new Response(
      JSON.stringify({ detail: 'openjarvis_rust is missing from the serving environment' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    ));
    const { getMemoryStats } = await import('./api');

    await expect(getMemoryStats()).rejects.toThrow(
      'openjarvis_rust is missing from the serving environment (HTTP 503)',
    );
  });

  it('keeps the HTTP status when a failed response has no JSON detail', async () => {
    fetchMock.mockResolvedValue(new Response('Internal Server Error', { status: 500 }));
    const { getMemoryStats } = await import('./api');

    await expect(getMemoryStats()).rejects.toThrow('Memory status request failed (HTTP 500)');
  });

  it('retries successfully against the updated API URL after a connection failure', async () => {
    localStorage.setItem('openjarvis-settings', JSON.stringify({ apiUrl: 'http://localhost:8000' }));
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    fetchMock.mockResolvedValueOnce(new Response(
      JSON.stringify({ backend: 'sqlite', entries: 3 }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const { getMemoryStats } = await import('./api');

    await expect(getMemoryStats()).rejects.toThrow(/Check the server status and API URL/);
    localStorage.setItem('openjarvis-settings', JSON.stringify({ apiUrl: 'http://localhost:8010' }));
    await expect(getMemoryStats()).resolves.toEqual({ backend: 'sqlite', entries: 3 });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/v1/memory/stats',
      'http://localhost:8010/v1/memory/stats',
    ]);
  });
});

describe('validateCompositeSkill', () => {
  it('calls POST /api/skills/composite/validate and returns validation result', async () => {
    fetchMock.mockResolvedValue(new Response(
      JSON.stringify({
        valid: true,
        errors: [],
        required_capabilities: ['code:execute'],
        dependencies: ['test_child'],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const { validateCompositeSkill } = await import('./api');
    const res = await validateCompositeSkill({
      name: 'test_composite',
      steps: [{ skill_name: 'test_child', arguments_template: '{}', output_key: 'out' }],
    });
    expect(res.valid).toBe(true);
    expect(res.required_capabilities).toEqual(['code:execute']);
    expect(res.dependencies).toEqual(['test_child']);
  });

  it('throws descriptive error on validation API failure', async () => {
    fetchMock.mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Circular dependency detected' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    ));
    const { validateCompositeSkill } = await import('./api');
    await expect(validateCompositeSkill({
      name: 'test_composite',
      steps: [{ skill_name: 'test_child' }],
    })).rejects.toThrow('Circular dependency detected');
  });
});

describe('createCompositeSkill', () => {
  it('calls POST /api/skills/composite and returns created skill in pending status', async () => {
    fetchMock.mockResolvedValue(new Response(
      JSON.stringify({
        status: 'created',
        skill: {
          name: 'test_composite',
          approval_status: 'pending_review',
          steps_count: 1,
          is_composite: true,
          required_capabilities: ['code:execute'],
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    const { createCompositeSkill } = await import('./api');
    const res = await createCompositeSkill({
      name: 'test_composite',
      steps: [{ skill_name: 'test_child' }],
      require_approval: true,
    });
    expect(res.status).toBe('created');
    expect(res.skill.approval_status).toBe('pending_review');
    expect(res.skill.is_composite).toBe(true);
  });

  it('throws descriptive error on creation API failure', async () => {
    fetchMock.mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Child skill not found or unapproved' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    ));
    const { createCompositeSkill } = await import('./api');
    await expect(createCompositeSkill({
      name: 'test_composite',
      steps: [{ skill_name: 'missing_child' }],
    })).rejects.toThrow('Child skill not found or unapproved');
  });
});
