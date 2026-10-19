# ULTRON — NEXT PHASE ROADMAP & IMPLEMENTATION PLAN

## Overview
Following the successful completion of the **Cinematic Onboarding Wizard**, **Personalization & Persona Directives**, **Cyber Web Audio Synthesizer**, and **3D Electron-Particle Avatar Core**, this document outlines the roadmap for subsequent phases of the Ultron system.

---

## Phase 1: High-Fidelity Audio & Local Speech Expansion

### Objectives
1. **Bundled Offline Urdu TTS Model (Piper / Sherpa-ONNX)**
   - *Current State*: Standard Windows SAPI5 lacks an offline Urdu speech synthesizer, requiring cloud API keys (ElevenLabs / OpenAI) for spoken Urdu.
   - *Next Phase*: Package an ultra-lightweight offline neural model (such as a quantised 16kHz Urdu Piper or Sherpa-ONNX voice model, ~35MB) bundled within the local desktop runtime so full Urdu speech synthesis functions 100% offline at zero cost.
2. **Audio Reactive Lip-Sync / Frequency Visualizer**
   - *Current State*: The 3D particle avatar enters a synthetic orbital oscillation when the assistant state is `'speaking'`.
   - *Next Phase*: Attach an `AudioContext.createAnalyser()` node to the active speech playback stream. Feed real-time FFT frequency bands directly into the particle shader/canvas loop so the particle orb expands and pulses in direct synchronization with real speech harmonics.

---

## Phase 2: Desktop Packaging & Native Tauri Hardening

### Objectives
1. **Tauri v2 Desktop App Compilation**
   - Run `cargo tauri build` in `src-tauri/` to produce native Windows installer (`.msi` / `.exe`) with embedded WebView2.
   - Verify hardware acceleration for WebGL / 2D Canvas rendering on discrete and integrated GPUs.
2. **Native System Tray & Global Cyber Shortcuts**
   - Integrate global hotkey (e.g. `Ctrl + Space` or `Win + Alt + U`) to toggle a floating cyber hologram HUD overlay from the system tray.
   - Provide native system notifications using `@tauri-apps/plugin-notification` with cyber sound cues.

---

## Phase 3: Advanced Hologram UI & Avatar Variant Shaders

### Objectives
1. **Three.js / WebGL Custom Shaders for Electron Avatar**
   - Elevate the 2D canvas 3D-projection engine to a hardware-accelerated WebGL shader pass.
   - Introduce chromatic aberration, bloom post-processing, and particle glow sprites.
2. **Additional Persona Avatars**
   - Develop distinct geometric morph targets for specific persona archetypes:
     - `Ultron Core`: Geodesic dodecahedron with rotating crimson energy rings.
     - `Jarvis`: Multi-layered holographic gyroscope rings with cyan luminescence.
     - `Mentor`: Concentric expanding fractal lattice.

---

## Phase 4: Full Multi-Modal & Tool-Assisted Interaction

### Objectives
1. **Voice-Activated Interruption (Barge-In)**
   - Implement continuous local VAD (Voice Activity Detection) using Silero VAD.
   - When the user begins speaking while Ultron is synthesizing speech, instantly halt audio playback and transition the particle core to `listening`.
2. **Live Vision / Screen Context**
   - Provide one-click desktop screenshot analysis paired with persona-tailored commentary.

---

## Phase 5: Verification & Quality Assurance Suite

### Execution Plan
1. **Automated End-to-End Suite**:
   - Establish Playwright desktop E2E tests covering first-launch, onboarding completion, persona switching, and settings persistence.
2. **Regression Gate**:
   - Mandatory test gate: Python pytest (`pytest tests/`) + Vitest (`npm test`) + Tauri build check (`cargo check --manifest-path src-tauri/Cargo.toml`).
