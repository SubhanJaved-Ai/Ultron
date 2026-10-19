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

  it('renders canvas element with proper dimensions and title', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore variant="neutral" state="idle" size={320} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('320px');
    expect(html).toContain('neutral presentation');
    expect(html).toContain('state: idle');
  });

  it('renders masculine presentation variant correctly', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore variant="masculine" state="thinking" size={400} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('masculine presentation');
    expect(html).toContain('state: thinking');
  });

  it('renders feminine presentation variant correctly', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore variant="feminine" state="speaking" size={400} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('feminine presentation');
    expect(html).toContain('state: speaking');
  });

  it('renders error state correctly', () => {
    const html = renderToStaticMarkup(
      <UltronParticleCore variant="neutral" state="error" size={280} />
    );

    expect(html).toContain('<canvas');
    expect(html).toContain('state: error');
  });
});
