export type ParticleVariant = 'neutral';
export type ParticleState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface ParticleCoreProps {
  /** Variant is kept for backwards compatibility but Ultron is always the canonical Electron */
  variant?: ParticleVariant | string;
  state?: ParticleState;
  size?: number;
  className?: string;
  themeColor?: string; // Optional hex/rgb override, defaults to cyber cyan
  showReticle?: boolean;
}
