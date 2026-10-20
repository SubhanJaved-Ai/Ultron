import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { UltronParticleCore } from './UltronParticleCore';

describe('UltronParticleCore', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      devicePixelRatio: 2,
      requestAnimationFrame: (cb: any) => setTimeout(cb, 16),
      cancelAnimationFrame: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders canvas element with proper dimensions and canonical Electron title', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore variant="neutral" state="idle" size={320} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('320px');
    expect(html).toContain('Ultron Electron — canonical particle core, state: idle');
  });

  it('renders thinking state on canonical Electron correctly', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore state="thinking" size={400} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('Ultron Electron — canonical particle core, state: thinking');
  });

  it('renders speaking state and safely handles legacy variant without altering canonical Electron identity', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore variant="masculine" state="speaking" size={400} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('Ultron Electron — canonical particle core, state: speaking');
  });

  it('renders error state correctly on canonical Electron', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore state="error" size={280} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('Ultron Electron — canonical particle core, state: error');
  });
});
