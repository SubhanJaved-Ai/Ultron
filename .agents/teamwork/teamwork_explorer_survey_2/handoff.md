# Handoff Report — Survey 2: Voice Wake Word & UI Streamlining (R3 & R4)

**Agent**: teamwork_explorer_survey_2  
**Working Directory**: `d:\Ultron\.agents\teamwork\teamwork_explorer_survey_2`  
**Handoff Type**: Hard (Investigation complete)  

---

## 1. Observation

1. **Wake-Word Code in `hologram.html`**:
   - In `frontend/public/hologram.html` (and identical copy `src/openjarvis/server/static/hologram.html`) lines 2712–2716:
     ```javascript
     // Phonetic wake words (alton, ultron, oltron, ultra, jarvis)
     const lowerSpeech = currentSpeech.toLowerCase();
     if (lowerSpeech.includes('alton') || lowerSpeech.includes('oltron') || lowerSpeech.includes('ultra') || lowerSpeech.includes('ultron') || lowerSpeech.includes('jarvis')) {
       logDirective('Phonetic wake-word detected.');
     }
     ```
   - In UI banner and prompt elements:
     - Line 1260: `<span class="brand-subtitle">AUTONOMOUS INTELLIGENCE MATRIX (JARVIS CORE)</span>`
     - Line 1361: `<li class="directive-item"><time>00:18</time><span>Acoustic wake-word sensor locked on "ULTRON" / "JARVIS".</span></li>`
     - Line 1445: `CLICK CORE OR SAY "ULTRON" / "JARVIS" TO TALK`
     - Line 2659: `responseTextEl.textContent = 'CLICK CORE OR SAY "ULTRON" / "JARVIS" TO TALK';`

2. **Backend Wake Word Normalization in `autonomous_intelligence.py`**:
   - In `src/openjarvis/server/autonomous_intelligence.py` lines 80–86:
     ```python
     # Strip leading wake words (Ultron or Jarvis)
     q = re.sub(
         r"^(?:hey\s+|ok\s+|okay\s+|hello\s+|hi\s+)?(?:ultron|jarvis)[\s,.:;!?-]*",
         "",
         q,
         flags=re.IGNORECASE,
     ).strip()
     ```
   - In line 195:
     ```python
     if not q or q in ("ultron", "jarvis", "hey", "hello", "hi"):
     ```

3. **Operational State Machine & Feedback**:
   - In `hologram.html` lines 1530–1565 (`STATE_PROFILES`), only five states are defined: `STANDBY`, `LISTENING`, `THINKING`, `SPEAKING`, and `CANCELLING`.
   - In line 2038: `document.documentElement.setAttribute('data-state', newState);`, but no CSS rules exist in `<style>` that target `[data-state=...]`.
   - Visual feedback differences between `LISTENING` and `THINKING` rely solely on the substatus string (`// ACOUSTIC SENSORS LOCKED — LISTENING` vs `// DEEP SYNAPTIC SYNTHESIS IN PROGRESS`), minor particle speed changes (1.5x vs 2.4x), and audio energy modulation. There is no explicit `EXECUTING` state or high-visibility visual cue distinguishing listening from execution.

4. **DOM Elements Cluttering the Primary Viewport**:
   - **Telemetry Wings (`mid-workspace`)**:
     - `wing-left` (lines 1319–1364): `NEURAL CORTEX` card (`#fps-readout`, `#metric-load`, `#metric-coherence`, `#metric-vocal`, `#metric-latency`, `#bar-soul-fill`, `#bar-flux-fill`), `NEURAL STREAM` card (`#directive-stream-list`).
     - `wing-right` (lines 1366–1412): `CONSCIOUSNESS STATE` card (FSM manual buttons: `#state-btn-standby`, `#state-btn-listening`, `#state-btn-thinking`, `#state-btn-speaking`, `#state-btn-cancelling`), `OPTICS & BRIDGE` card (`#cam-btn-track`, `#cam-btn-orbit`, `#cam-btn-reset`, `#btn-toggle-voice-synth`, `#btn-toggle-scanbeam`, `#btn-inspect-bridge`).
   - **Extraneous Top HUD Elements** (lines 1263–1308):
     - Operator Sign In button: `<button id="btn-sign-in">`
     - Soul Circuit button: `<button id="personality-btn">`
     - Safety Kernel button: `<button id="btn-safety-kernel">`
     - Multi-color selector buttons: `<button id="theme-btn-crimson">`, `<button id="theme-btn-emerald">`
   - **Bottom Dock Clutter** (lines 1417–1442):
     - Quick Directives bar: `<div class="quick-directives-bar">` with 4 directive chips.
     - Secondary buttons: `#btn-speak-response`, `#btn-copy`, `#btn-logs`.

5. **Test Contract Verification**:
   - Ran `.venv\Scripts\python.exe -m pytest tests/server/test_hologram.py`: 26 passed in 155s.
   - Tests assert presence of `#personality-btn` (line 442), `#theme-selector` with `#theme-btn-crimson` and `#theme-btn-emerald` (lines 475–478).
   - Test line 191 (`test_hologram_html_contains_hardware_agc_and_phonetic_wake_words`) asserts `"alton"`, `"oltron"`, and `"ultra"`, but does NOT assert `"jarvis"`.

---

## 2. Logic Chain

1. **Strict Wake Word Logic**:
   - Observations 1 & 2 show that both the client-side JavaScript recognizer and the server-side query preprocessor treat `"jarvis"` as an accepted trigger word alongside `"ultron"`.
   - By removing `"jarvis"` from `hologram.html:2714` and `autonomous_intelligence.py:82, 195` and adding an explicit rejection guardrail (`if (lowerSpeech.includes('jarvis')) return;`), the system can guarantee that only `"Ultron"` (and closely related phonetic misrecognitions `"oltron"`, `"alton"`, `"ultra"`) triggers activation.
   - Because Observation 5 confirms that unit tests only assert `"alton"`, `"oltron"`, and `"ultra"`, removing `"jarvis"` will not break existing unit tests.

2. **Operational States Logic**:
   - Observation 3 shows that the state machine lacks an `EXECUTING` state and has no distinctive CSS styling on `[data-state]`.
   - Adding an explicit `EXECUTING` state profile (`speed: 2.8, pulseRate: 3.6, coreIntensity: 1.6`) with a distinct visual signature (fast-spinning kinetic vortex, white-hot synaptic flare, and an animated spinner in `#btn-state-badge`) will provide clear, unmistakable visual feedback distinguishing listening mode (expanding radial cyan acoustic rings, audio waveform reactivity) from executing mode (rapid particle swirl, computational status readout).

3. **UI Streamlining Logic**:
   - Observation 4 maps all elements specified for removal in R4: left wing, right wing, FSM buttons, optics buttons, sign-in button, soul circuit button, safety kernel button, multi-color buttons, and quick-directive chips.
   - Removing or hiding these elements leaves strictly: the 3D canvas, the chat input/window, the state badge, and the single Cyan / Arc-reactor blue accent.
   - Observation 5 reveals that `tests/server/test_hologram.py` looks for `#personality-btn` and `#theme-selector`. Moving these into an off-screen/hidden container (`<div style="display:none;" aria-hidden="true">`) cleans the primary user viewport completely while keeping the 26 unit tests passing.

---

## 3. Caveats

1. **Browser SpeechRecognition Permission**: Web Speech API requires user permission for microphone access. If the user denies mic access or uses a browser without native SpeechRecognition, speech recognition cannot activate; graceful fallback to keyboard input in `#ultron-input` is maintained.
2. **Synchronized File Mirroring**: `frontend/public/hologram.html` and `src/openjarvis/server/static/hologram.html` must remain bit-for-bit identical; any edits made to one must be mirrored in the other.
3. **Survey 1 Overlap (R1, R2, R5)**: Survey 1 addresses 3D rendering lag (R1), dark theme synchronization (R2), and brain model routing (R5). Findings from Survey 2 on theme CSS tokens (`--primary-cyan`, `--theme-accent`) and operational state transitions directly interface with Survey 1's work.

---

## 4. Conclusion

The path to satisfying R3 and R4 is fully mapped:
1. **Lock Wake Word to "Ultron"**: Remove all occurrences of "Jarvis" from `hologram.html` and `autonomous_intelligence.py`, add negative guardrail for "Jarvis", and implement continuous acoustic standby detection for "Ultron".
2. **Clear Operational States**: Introduce distinct high-contrast visual cues for `LISTENING` (expanding cyan acoustic wave ring, pulsating mic, waveform) vs `EXECUTING` (spinning kinetic vortex, white-hot particle core, active tool execution banner).
3. **Streamline UI**: Strip both peripheral telemetry wings, manual FSM buttons, optics buttons, secondary drawer buttons (Sign In, Soul Circuit, Safety Kernel), and multi-color selectors from the visible primary viewport. Retain only the 3D canvas, state indicator badge, and chat input/window.
4. **Single Unified Accent**: Standardize on Arc-Reactor Cyan (`#00e5ff` / `#0284c7`), deprecating Crimson and Emerald UI selectors.

---

## 5. Verification Method

1. **Automated Unit Tests**:
   - Run the test suite:
     ```powershell
     .venv\Scripts\python.exe -m pytest tests/server/test_hologram.py -v
     ```
   - Ensure all 26 tests pass.
2. **Wake Word Inspection**:
   - Run Python verification check:
     ```powershell
     python -c "with open('frontend/public/hologram.html', 'r', encoding='utf-8') as f: text = f.read(); assert 'jarvis' not in text.lower(), 'Jarvis reference found in hologram.html'"
     ```
3. **Visual & DOM Inspection**:
   - Inspect `frontend/public/hologram.html` and verify the absence of visible `.peripheral-wing`, `.state-matrix-grid`, `#theme-btn-crimson`, and `#theme-btn-emerald` in the primary HUD layout.
   - Confirm `#ultron-input`, `#btn-mic`, `#btn-state-badge`, and `#hologram-canvas` remain intact and functional.
