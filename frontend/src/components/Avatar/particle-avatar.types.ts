export type ParticleVariant = 'neutral' | 'masculine' | 'feminine';
export type ParticleState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface ParticleCoreProps {
  variant: ParticleVariant;
  state?: ParticleState;
  size?: number;
  className?: string;
  themeColor?: string; // Optional hex/rgb override, defaults to cyber cyan
  showReticle?: boolean;
}
