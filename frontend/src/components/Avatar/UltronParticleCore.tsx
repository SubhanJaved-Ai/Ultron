import { useEffect, useRef } from 'react';
import type { ParticleCoreProps, ParticleVariant, ParticleState } from './particle-avatar.types';

interface ParticleNode {
  // Canonical Electron base coordinates (Neural cortical sphere)
  baseX: number;
  baseY: number;
  baseZ: number;

  size: number;
  phase: number;
  speed: number;
  brightness: number;
}

const PARTICLE_COUNT = 1100;

function createParticleMatrix(): ParticleNode[] {
  const particles: ParticleNode[] = [];

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    // Canonical Electron Neural Orb (Sphere with cortical brain fold undulations)
    const u = Math.random();
    const v = Math.random();
    const theta = u * 2.0 * Math.PI;
    const phi = Math.acos(2.0 * v - 1.0);
    const rBase = 0.72 + Math.random() * 0.16;
    const corticalDisplace =
      0.08 * Math.sin(theta * 3.0) * Math.cos(phi * 2.5) +
      0.04 * Math.cos(theta * 5.0 + phi * 3.0);
    const rFinal = rBase + corticalDisplace;

    const baseX = rFinal * Math.sin(phi) * Math.cos(theta);
    const baseY = rFinal * Math.cos(phi);
    const baseZ = rFinal * Math.sin(phi) * Math.sin(theta);

    particles.push({
      baseX,
      baseY,
      baseZ,
      size: 1.0 + Math.random() * 1.8,
      phase: Math.random() * Math.PI * 2.0,
      speed: 0.8 + Math.random() * 0.6,
      brightness: 0.35 + Math.random() * 0.65,
    });
  }

  return particles;
}

export function UltronParticleCore({
  variant = 'neutral',
  state = 'idle',
  size = 460,
  className = '',
  themeColor = '#00e5ff',
  showReticle = true,
}: ParticleCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const particlesRef = useRef<ParticleNode[]>([]);
  const animFrameRef = useRef<number | null>(null);
  const rotAngleRef = useRef<number>(0);
  const reticleAngleRef = useRef<number>(0);

  // Initialize particles once
  if (particlesRef.current.length === 0) {
    particlesRef.current = createParticleMatrix();
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let isMounted = true;
    let lastTime = performance.now();

    const render = (time: number) => {
      if (!isMounted) return;

      const dt = Math.min((time - lastTime) / 1000, 0.1);
      lastTime = time;

      // Dynamic motion parameters based on assistant state
      let speedMultiplier = 1.0;
      let pulseAmplitude = 0.03;
      let audioWobble = 0.0;
      let coreGlowAlpha = 0.4;
      let jitter = 0.0;

      switch (state) {
        case 'listening':
          speedMultiplier = 1.35;
          pulseAmplitude = 0.06;
          coreGlowAlpha = 0.65;
          break;
        case 'thinking':
          speedMultiplier = 2.4;
          pulseAmplitude = 0.09;
          coreGlowAlpha = 0.8;
          break;
        case 'speaking':
          speedMultiplier = 1.6;
          pulseAmplitude = 0.08;
          audioWobble = Math.sin(time * 0.016) * 0.06;
          coreGlowAlpha = 0.9;
          break;
        case 'error':
          speedMultiplier = 0.4;
          pulseAmplitude = 0.02;
          jitter = (Math.random() - 0.5) * 4.0;
          coreGlowAlpha = 0.3;
          break;
        case 'idle':
        default:
          speedMultiplier = 0.9;
          pulseAmplitude = 0.025;
          coreGlowAlpha = 0.45;
          break;
      }

      rotAngleRef.current += dt * 0.48 * speedMultiplier;
      reticleAngleRef.current += dt * 0.12 * speedMultiplier;

      const rot = rotAngleRef.current;
      const cosR = Math.cos(rot);
      const sinR = Math.sin(rot);

      const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
      const width = canvas.clientWidth || size;
      const height = canvas.clientHeight || size;

      if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
      }

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      const centerX = width / 2 + jitter;
      const centerY = height / 2;
      const renderRadius = Math.min(width, height) * 0.42;

      // =====================================================================
      // 1. Circular Cyber Reticle & Calibration HUD
      // =====================================================================
      if (showReticle) {
        const reticleRadius = renderRadius * 1.05;
        const retAngle = reticleAngleRef.current;

        ctx.save();
        ctx.translate(centerX, centerY);

        // Faint outer orbital ring
        ctx.beginPath();
        ctx.arc(0, 0, reticleRadius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(2, 132, 199, 0.18)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Inner dotted reticle ring
        ctx.beginPath();
        ctx.setLineDash([2, 6]);
        ctx.arc(0, 0, reticleRadius * 0.93, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(2, 132, 199, 0.28)';
        ctx.stroke();
        ctx.setLineDash([]);

        // Perimeter angle tick notches (every 10 degrees)
        const tickCount = 48;
        for (let i = 0; i < tickCount; i++) {
          const a = (i / tickCount) * Math.PI * 2 + retAngle;
          const isMajor = i % 12 === 0;
          const tickLen = isMajor ? 9 : 4;
          const r1 = reticleRadius + 1;
          const r2 = reticleRadius + 1 + tickLen;

          ctx.beginPath();
          ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
          ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
          ctx.strokeStyle = isMajor
            ? 'rgba(0, 229, 255, 0.65)'
            : 'rgba(2, 132, 199, 0.22)';
          ctx.lineWidth = isMajor ? 1.5 : 1;
          ctx.stroke();
        }

        // Active State Radar Indicator ring
        if (state === 'listening' || state === 'speaking') {
          const pulse = (Math.sin(time * 0.006) + 1) * 0.5;
          ctx.beginPath();
          ctx.arc(0, 0, reticleRadius * (0.85 + pulse * 0.15), 0, Math.PI * 2);
          ctx.strokeStyle =
            state === 'speaking'
              ? `rgba(0, 229, 255, ${0.4 * (1 - pulse)})`
              : `rgba(2, 132, 199, ${0.35 * (1 - pulse)})`;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        ctx.restore();
      }

      // =====================================================================
      // 2. White-Hot Central Synaptic Singularity Nexus
      // =====================================================================
      const corePulse = (Math.sin(time * 0.005) + 1) * 0.5;
      const coreSize = 14 + corePulse * 6 + (state === 'speaking' ? 8 : 0);

      const grad = ctx.createRadialGradient(
        centerX,
        centerY,
        0,
        centerX,
        centerY,
        coreSize * 2.5
      );
      grad.addColorStop(0.0, 'rgba(255, 255, 255, 0.95)');
      grad.addColorStop(0.25, 'rgba(195, 250, 255, 0.7)');
      grad.addColorStop(0.55, `rgba(0, 229, 255, ${coreGlowAlpha})`);
      grad.addColorStop(1.0, 'rgba(2, 132, 199, 0.0)');

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, coreSize * 2.5, 0, Math.PI * 2);
      ctx.fill();

      // =====================================================================
      // 3. 3D Particle Matrix (Canonical Electron Orb)
      // =====================================================================
      const particles = particlesRef.current;
      const breathe = Math.sin(time * 0.003) * pulseAmplitude;

      // Pre-sort particles by rotated Z depth for accurate volumetric shading
      const renderNodes: {
        sx: number;
        sy: number;
        size: number;
        alpha: number;
        rotZ: number;
      }[] = [];

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Apply breathing & audio resonance to canonical Electron base coordinates
        const rScale = 1.0 + breathe + audioWobble * Math.sin(p.phase + time * 0.008);
        const curX = p.baseX * rScale;
        const curY = p.baseY * rScale;
        const curZ = p.baseZ * rScale;

        // Y-axis 3D rotation
        const rotX = curX * cosR - curZ * sinR;
        const rotY = curY;
        const rotZ = curX * sinR + curZ * cosR;

        // Perspective depth projection
        const fov = 2.4;
        const depth = fov / (fov + rotZ);
        const screenX = centerX + rotX * renderRadius * depth;
        const screenY = centerY - rotY * renderRadius * depth;

        // Volumetric depth brightness
        const depthAlpha = Math.max(0.12, Math.min(1.0, (rotZ + 1.1) * 0.55));
        const finalAlpha = depthAlpha * p.brightness;
        const finalSize = Math.max(0.7, p.size * depth * 1.1);

        renderNodes.push({
          sx: screenX,
          sy: screenY,
          size: finalSize,
          alpha: finalAlpha,
          rotZ,
        });
      }

      // Sort back-to-front
      renderNodes.sort((a, b) => a.rotZ - b.rotZ);

      // Draw all particles
      for (let i = 0; i < renderNodes.length; i++) {
        const node = renderNodes[i];
        ctx.beginPath();
        ctx.arc(node.sx, node.sy, node.size, 0, Math.PI * 2);

        // Core highlight vs outer cyan particles
        if (node.rotZ > 0.4 && node.alpha > 0.6) {
          ctx.fillStyle = `rgba(255, 255, 255, ${node.alpha * 0.95})`;
        } else {
          ctx.fillStyle = `rgba(0, 229, 255, ${node.alpha * 0.85})`;
        }
        ctx.fill();
      }

      ctx.restore();
      animFrameRef.current = requestAnimationFrame(render);
    };

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      isMounted = false;
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [variant, state, size, showReticle, themeColor]);

  return (
    <div
      className={`relative flex items-center justify-center select-none overflow-hidden ${className}`}
      style={{ width: `${size}px`, height: `${size}px` }}
    >
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block' }}
        title={`Ultron Electron — canonical particle core, state: ${state}`}
      />
    </div>
  );
}
