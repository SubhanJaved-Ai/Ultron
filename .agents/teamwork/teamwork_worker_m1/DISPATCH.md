# Task Assignment: Milestone M1 — 3D Hologram Performance & System Theme Synchronization

- **Role**: teamwork_worker
- **Working Directory**: d:\Ultron\.agents\teamwork\teamwork_worker_m1
- **Authoritative Request**: d:\Ultron\.agents\teamwork\ORIGINAL_REQUEST.md
- **Master Project Plan**: d:\Ultron\PROJECT.md
- **Explorer Survey 1 Findings**: d:\Ultron\.agents\teamwork\teamwork_explorer_survey_1\analysis.md
- **Explorer Survey 1 Handoff**: d:\Ultron\.agents\teamwork\teamwork_explorer_survey_1\handoff.md

## Exclusive File Ownership
You own and may modify ONLY these files:
- `src/openjarvis/server/static/hologram.html`
- `frontend/public/hologram.html`
- `frontend/dist/hologram.html`
- `frontend/src/pages/HologramPage.tsx`
Note: `src/openjarvis/server/static/hologram.html` and `frontend/public/hologram.html` must remain synchronized and identical!

## Objectives

### R1. Hologram Performance & Mathematical Cortex Preservation
1. **Zero-Allocation Projection Pipeline**:
   - In `project3D()` and `stepFrame()`, eliminate all heap object instantiation (`{ sx, sy, rz, depth, scale }` and `{ x1, y1, x2, y2 }`).
   - Use reusable static typed buffers / projection scratchpad structs to stream 2D coordinates directly into canvas path commands (`beginPath`, `moveTo`, `lineTo`, `stroke`).
2. **Hot-Loop Math & Draw Call Optimization**:
   - Optimize `Math.pow(1.0 - facing, 1.85)` in cortical ring striation loop using fast polynomial/multiplication approximation or precomputed lookup table.
   - Batch path strokes for `fineStriationBatch`, `ridgeFoldBatch`, and `brightCrestBatch`, avoiding redundant multi-pass stroking.
   - Batch particle / bokeh sprite rendering under `lighter` composite operation.
3. **Preserve Exact Mathematical Cortex Appearance**:
   - Keep 100% fidelity of all 12 cortical lobes (`CORTICAL_LOBES`), the harmonic `corticalFoldDisplacement` gyri equation (`0.24 * h1 + 0.14 * h2 + 0.08 * h3`), all 56 dendritic filaments, 28 sweeping fiber streams, and the 3,800+ particle matrix without distortion.

### R2. System Theme Synchronization
1. **Dark Theme Tokens in `hologram.html`**:
   - Define CSS root tokens for `.dark` and `[data-theme-mode="dark"]`:
     - `--bg-void: #060b13;`
     - Deep space stage background gradient: `radial-gradient(circle at 50% 45%, rgba(6, 11, 19, 0.95), rgba(2, 6, 12, 1.0))`
     - Dark vignette overlay: `box-shadow: inset 0 0 100px 30px rgba(0, 0, 0, 0.85)` (replacing the white vignette).
     - Default theme mode should be dark (`--bg-void: #060b13;`).
2. **React Wrapper Synchronization in `HologramPage.tsx`**:
   - Replace hardcoded `#f8fafc` light classes with Tailwind dark variants (`bg-slate-950 text-slate-100`, dark border, dark navbar).
   - Listen to `settings.theme` from `useAppStore`.
   - Pass `?mode=dark` (or active mode) in iframe URL.
   - Send `iframeRef.current.contentWindow.postMessage({ type: 'SET_THEME_MODE', mode }, '*')` on mount and whenever `settings.theme` toggles.
3. **Iframe Message Listener in `hologram.html`**:
   - Listen for `window.addEventListener('message', (e) => { if (e.data?.type === 'SET_THEME_MODE') setThemeMode(e.data.mode); })`.
   - Check URL query parameter `?mode=dark` on initial load.
   - Update `document.documentElement.setAttribute('data-theme-mode', mode)` and toggle `.dark` class.

## Verification
- Run existing test suites:
  `.venv\Scripts\pytest.exe tests/server/test_hologram.py tests/server/test_hologram_theme.py`
- Verify vitest in frontend:
  `npm --prefix frontend run test -- run src/components/Avatar/UltronParticleCore.test.tsx`
- Ensure SHA256 hashes of `src/openjarvis/server/static/hologram.html` and `frontend/public/hologram.html` match.

## Output
Write your completion handoff report to `d:\Ultron\.agents\teamwork\teamwork_worker_m1\handoff.md` and message the parent orchestrator.


## 2026-10-31T07:07:39Z
You are teamwork_worker_m1.
Your working directory is: d:\Ultron\.agents\teamwork\teamwork_worker_m1
Read your instructions in d:\Ultron\.agents\teamwork\teamwork_worker_m1\DISPATCH.md, the master project plan in d:\Ultron\PROJECT.md, the authoritative user request in d:\Ultron\.agents\teamwork\ORIGINAL_REQUEST.md, and the explorer findings in d:\Ultron\.agents\teamwork\teamwork_explorer_survey_1\analysis.md and handoff.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your exclusive files to modify:
- src/openjarvis/server/static/hologram.html
- frontend/public/hologram.html
- frontend/dist/hologram.html
- frontend/src/pages/HologramPage.tsx
(Keep src/openjarvis/server/static/hologram.html and frontend/public/hologram.html identical!)

Implement Milestone M1:
1. R1 Hologram Performance & Mathematical Cortex Preservation:
   - Zero-allocation 3D projection pipeline (static coordinate scratchpads / buffers, eliminate object allocations in project3D and batch arrays).
   - Fast Math.pow optimization in the striation loop.
   - Batch path strokes and optimize canvas draw calls.
   - 100% preserve the 12 cortical lobes, the harmonic gyri equations, 56 dendritic filaments, 28 fiber streams, and the 3,800+ particle matrix.
2. R2 System Theme Synchronization:
   - Provide dark theme CSS tokens (.dark and [data-theme-mode="dark"]), dark void background (--bg-void: #060b13), dark radial stage gradients, dark vignette.
   - Update HologramPage.tsx with Tailwind dark styling and bind settings.theme to the iframe via ?mode= query param and bidirectional postMessage({ type: 'SET_THEME_MODE', mode }).
   - Handle postMessage and URL param in hologram.html to toggle theme dynamically.

Run existing tests to verify:
.venv\Scripts\pytest.exe tests/server/test_hologram.py tests/server/test_hologram_theme.py

Write your completion report to d:\Ultron\.agents\teamwork\teamwork_worker_m1\handoff.md and message the parent orchestrator.

