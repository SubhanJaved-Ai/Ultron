# Project: Ultron 3D Hologram Production Polish & Brain Integration

## Architecture
The Ultron 3D Hologram interface consists of a high-performance 3D neural consciousness visualization canvas, integrated within the Ultron web frontend and backed by the FastAPI Ultron server and multi-model LLM engine.

```
                      ┌──────────────────────────────────────────┐
                      │        Ultron React Frontend             │
                      │    (HologramPage.tsx, useAppStore)       │
                      └────────────────────┬─────────────────────┘
                                           │ postMessage / ?mode=
                                           ▼
                      ┌──────────────────────────────────────────┐
                      │      3D Hologram Canvas Interface        │
                      │             (hologram.html)              │
                      │  - Zero-allocation 3D Projection Engine  │
                      │  - Arc-Reactor Cyan Theme (#00e5ff)      │
                      │  - Strict "Ultron" SpeechRecognition     │
                      │  - Visual States: LISTENING vs EXECUTING │
                      │  - Streamlined HUD (Canvas + Chat + Badge│
                      └────────────────────┬─────────────────────┘
                                           │ POST /api/hologram/directive
                                           ▼
                      ┌──────────────────────────────────────────┐
                      │          FastAPI Backend Router          │
                      │          (hologram_routes.py)            │
                      └────────────────────┬─────────────────────┘
                                           │
                                           ▼
                      ┌──────────────────────────────────────────┐
                      │    Unified System Brain / LLM Engine     │
                      │  - JarvisSystem / QueryOrchestrator      │
                      │  - CloudEngine / cloud_router.py         │
                      │    (Gemini, OpenAI, Claude, OpenRouter)  │
                      │  - OllamaEngine (local models)           │
                      │  - Real Tool Execution & Telemetry       │
                      └──────────────────────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | F1. Zero-Allocation 3D Projection | Eliminate ~44k-50k heap allocations/frame in `project3D` and batch segments using static buffers | M1 | Survey 1 (R1) |
| 2 | F2. Mathematical Cortex Preservation | Preserve all 12 cortical lobes, harmonic `corticalFoldDisplacement` gyri, dendritic filaments, and particle matrix without distortion | M1 | Survey 1 (R1) |
| 3 | F3. Canvas Render Loop Optimization | Replace `Math.pow` hot-loop with polynomial approximation, batch path strokes, reduce redundant drawImage calls | M1 | Survey 1 (R1) |
| 4 | F4. Hologram CSS Dark Theme Tokens | Add `.dark` and `[data-theme-mode="dark"]` CSS tokens (`--bg-void: #060b13`), dark vignette and stage gradients | M1 | Survey 1 (R2) |
| 5 | F5. React & Iframe Theme Synchronization | Synchronize `useAppStore` theme with iframe via URL query `?mode=` and bidirectional `postMessage({ type: 'SET_THEME_MODE', mode })` | M1 | Survey 1 (R2) |
| 6 | F6. Strict "Ultron" Wake Word Locking | Reject "Jarvis" in client-side speech recognizer and server preprocessor; activate strictly on "Ultron" (and close phonetic variants) | M2 | Survey 2 (R3) |
| 7 | F7. Operational State Machine & Indicators | Add explicit `LISTENING` (expanding cyan acoustic wave ring, pulsating mic) and `EXECUTING` (kinetic spinning vortex, synaptic flare) states | M2 | Survey 2 (R3) |
| 8 | F8. HUD Clutter Elimination | Remove peripheral wings (Neural Cortex, Neural Stream), FSM manual buttons, optics buttons, top HUD drawer buttons, and quick directives bar | M2 | Survey 2 (R4) |
| 9 | F9. Single Cyan / Arc-Reactor Accent | Remove Crimson and Emerald selectors, standardizing the entire hologram view on Arc-Reactor Cyan (`#00e5ff`) | M2 | Survey 2 (R4) |
| 10 | F10. Multi-Provider LLM Brain Routing | Route `/api/hologram/directive` to active system LLM provider (Gemini, Claude, OpenAI, OpenRouter, or Ollama) via JarvisSystem / CloudEngine | M3 | Survey 3 (R5) |
| 11 | F11. Canned Mock & Fallback Removal | Remove client `generateContextualResponse`, dummy file generation (`D:/Ultron new create file.txt`), and `_smart_local_reasoning` canned strings | M3 | Survey 3 (R5) |
| 12 | F12. Real Tool Execution Telemetry | Stream real tool actions, parameters, status, and output back to the hologram interface | M3 | Survey 3 (R5) |
| 13 | F13. 100% E2E Test Suite Pass (Tiers 1-4) | Pass all opaque-box requirement tests across performance, theming, wake-word, UI streamlining, and brain routing | M4 | Dual Track |
| 14 | F14. Adversarial Coverage Hardening (Tier 5)| Stress-test edge cases, boundary conditions, rapid theme switching, concurrent directives, and speech misrecognitions | M4 | Dual Track |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | 3D Hologram Performance & Theme Synchronization | F1, F2, F3, F4, F5 | none | IN_PROGRESS |
| M2 | Strict Wake Word, Operational States & UI Streamlining | F6, F7, F8, F9 | M1 | PLANNED |
| M3 | Unified Brain Routing & Mock Elimination | F10, F11, F12 | none | PLANNED |
| M4 | Full Integration, 100% E2E Pass & Adversarial Hardening | F13, F14 | M1, M2, M3, E2E Track | PLANNED |

## Interface Contracts

### Contract 1: React Parent ↔ Hologram Iframe Theme Sync
- Message payload: `{ type: 'SET_THEME_MODE', mode: 'light' | 'dark' }`
- URL initialization: `/hologram?mode=dark` or `/hologram.html?mode=dark`
- CSS attribute: `document.documentElement.setAttribute('data-theme-mode', mode)`
- React wrapper: `HologramPage.tsx` passes active `settings.theme` ('light' | 'dark' | system resolved) and listens for DOM theme changes.

### Contract 2: Hologram Client ↔ Backend Directive Endpoint
- Endpoint: `POST /api/hologram/directive`
- Request: `{ directive: string, history?: Array<{ role: string, content: string }>, mode?: string }`
- Response:
  ```json
  {
    "reply": "string (intelligent response from active LLM engine)",
    "status": "success" | "error",
    "state": "EXECUTING" | "SPEAKING" | "STANDBY",
    "actions": [
      {
        "tool": "string",
        "parameters": {},
        "status": "completed" | "failed",
        "output": "string"
      }
    ],
    "model": "string (active provider/model name, e.g. gemini-2.5-pro, gpt-4o, claude-3-5-sonnet, or local)"
  }
  ```

### Contract 3: Wake Word & State Transitions
- Wake words accepted: `"ultron"`, `"oltron"`, `"alton"`, `"ultra"`
- Wake words rejected with early return: `"jarvis"` (and any utterance containing `"jarvis"`)
- States:
  - `STANDBY`: Idle ambient undulating brain, breathing core intensity 1.0.
  - `LISTENING`: Acoustic sensor active, radial expanding cyan sonic rings, pulsating microphone badge, core intensity 1.3.
  - `EXECUTING`: Directive submitted to brain, kinetic rotating particle vortex, white-hot synaptic discharge, core intensity 1.8, spinning progress badge.
  - `SPEAKING`: Vocalizing response, audio reactive frequency modulation.

## Code Layout
- Frontend Static Hologram Engine: `src/openjarvis/server/static/hologram.html` (mirrored in `frontend/public/hologram.html` and `frontend/dist/hologram.html`)
- Frontend React Container: `frontend/src/pages/HologramPage.tsx`, `frontend/src/lib/store.ts`
- Backend API Router: `src/openjarvis/server/hologram_routes.py`
- Backend LLM Client & Brain: `src/openjarvis/server/llm_client.py`
- Server App Wiring: `src/openjarvis/server/app.py`, `src/openjarvis/server/__main__.py`
- Server Autonomous Speech: `src/openjarvis/server/autonomous_intelligence.py`
- Test Suites:
  - Unit / Server Tests: `tests/server/test_hologram.py`, `tests/server/test_hologram_theme.py`, `tests/server/test_llm_client.py`
  - E2E Test Suite: `tests/e2e/test_hologram_production_e2e.py`
