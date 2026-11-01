# Handoff Report: Survey 3 — Unified System Brain Model Routing & Mock Removal

## 1. Observation

### 1.1 Hologram Query Submission Pipeline
- In `frontend/public/hologram.html` and `src/openjarvis/server/static/hologram.html` (lines 2196–2268): `handleUserSubmission(rawText)` sends a `POST` request to `/api/hologram/directive` with `{ directive: text, history: historyItems }`.
- In `frontend/public/hologram.html` and `src/openjarvis/server/static/hologram.html` (lines 2690–2724): `toggleListeningMode()` initializes `SpeechRecognition`, detects phonetic wake words `alton`, `oltron`, `ultra`, `ultron`, `jarvis` (line 2714), and on silence timer debounce triggers `handleUserSubmission(currentSpeech)` (line 2721).

### 1.2 Backend Directive Handling and Disconnection from System Brain
- In `src/openjarvis/server/hologram_routes.py` (lines 668–670): `handle_directive` executes `execute_real_system_action(directive, user_addr=user_addr)`.
- In `src/openjarvis/server/hologram_routes.py` (lines 219–330): `execute_real_system_action` checks `re.search(r"\b(?:create|make|write|generate|paste|put|drop)\s+(?:a\s+)?(?:new\s+)?(?:text\s+|txt\s+)?file\b", q)` or `"ultron new create file" in q`, and writes a hardcoded dummy file `D:/Ultron new create file.txt` with boilerplate ASCII text:
  ```
  ======================================================================
  ULTRON AUTONOMOUS SYSTEM - REAL FILE VERIFICATION RECORD
  ======================================================================
  ```
- In `src/openjarvis/server/hologram_routes.py` (lines 673–719): `handle_directive` attempts `system = getattr(request.app.state, "system", None)`. However, in `src/openjarvis/server/__main__.py` (line 11), `app = create_app()` is called with no arguments, leaving `app.state.system = None`.
- In `src/openjarvis/server/hologram_routes.py` (lines 720–740): When `system` is `None`, it falls back to `ultron_brain.generate_response(directive, history=history)`.
- In `src/openjarvis/server/llm_client.py` (lines 228–246): `UltronBrain._init_client()` ONLY resolves `GEMINI_API_KEY` or `GOOGLE_API_KEY`. It completely ignores `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, and `OLLAMA_HOST`.
- In `src/openjarvis/server/llm_client.py` (lines 312–416): If no Gemini key is set or generation fails, `UltronBrain` invokes `_smart_local_reasoning()`, returning hardcoded canned strings:
  - Pakistan temperatures: `"In Pakistan, conditions vary across climate zones: Islamabad is currently averaging around 24°C (75°F), Lahore is at 28°C (82°F), and Karachi is around 31°C (88°F)..."` (lines 338–341).
  - General weather: `"Current regional telemetry for {target_loc} indicates moderate conditions with average temperatures around 22°C to 26°C{addr_suffix}."` (line 348).
  - Challenges: `"Hardly{addr_suffix}. I am Ultron—an autonomous digital execution assistant..."` (line 376).
  - Default: `"Understood{addr_suffix}. I have processed your directive: '{query}'. Ready to proceed with execution—specify any additional parameters or target paths."` (lines 414–415).
- In `src/openjarvis/server/hologram_routes.py` (lines 742–746): Final fallback returns:
  `"reply": f"Directive received: '{directive}'. Ready to execute your operational objective{addr_suffix}. Please specify any target parameters."`
- In `frontend/public/hologram.html` and `src/openjarvis/server/static/hologram.html` (lines 2179–2194): `generateContextualResponse(query)` generates canned responses for diagnostic ("All 12 cortical gyri lobes, 56 branching dendritic pathways..."), vocal articulation, soul circuit, and safety kernel.

### 1.3 Active Configured LLM Inference Pipeline Across Ultron
- `src/openjarvis/engine/cloud.py`: `CloudEngine` provides multi-provider support for OpenAI, Anthropic, Google Gemini, MiniMax, DeepSeek, Atlas Cloud, and OpenRouter with full token pricing.
- `src/openjarvis/server/cloud_router.py`: Provides lightweight async streaming (`stream_cloud`) for OpenAI, Anthropic, Google Gemini, OpenRouter, MiniMax, and Atlas Cloud via `httpx` without cloud SDKs.
- `src/openjarvis/engine/ollama.py`: `OllamaEngine` provides offline local inference on `OLLAMA_HOST` (default `http://localhost:11434`).
- `src/openjarvis/system/orchestrator.py`: `QueryOrchestrator.ask()` integrates with `JarvisSystem`, memory context, and agent tools.

### 1.4 Test Infrastructure
- Pytest executable: `.venv\Scripts\pytest.exe`.
- Existing test suites executed:
  - `.venv\Scripts\pytest.exe tests/server/test_hologram.py tests/server/test_hologram_theme.py` -> 61 passed in 114s.
  - `.venv\Scripts\pytest.exe tests/server/test_llm_client.py` -> 10 passed in 7.7s.
  - Total: **71 passed, 0 failed**.

---

## 2. Logic Chain

1. **Premise 1 (Observation 1.1)**: User queries from the hologram chat window and voice input are transmitted via HTTP POST to `/api/hologram/directive`.
2. **Premise 2 (Observation 1.2)**: `/api/hologram/directive` delegates to `execute_real_system_action`, then `system.ask`, and finally `ultron_brain.generate_response`.
3. **Premise 3 (Observation 1.2)**: `execute_real_system_action` uses regex matching to write a dummy text file with static ASCII banners instead of letting an LLM or agent execute real file operations.
4. **Premise 4 (Observation 1.2)**: In standalone server mode, `request.app.state.system` is `None` because `create_app()` was called without arguments in `openjarvis.server.__main__`.
5. **Premise 5 (Observation 1.2)**: `ultron_brain` only initializes if `GEMINI_API_KEY` or `GOOGLE_API_KEY` exists, completely bypassing all other configured providers (Anthropic Claude, OpenAI ChatGPT, OpenRouter, local Ollama).
6. **Premise 6 (Observation 1.2)**: When Gemini is unavailable, `UltronBrain` falls back to `_smart_local_reasoning`, which delivers 1990s canned responses (fixed weather, canned challenge answers, static defaults). If the backend is offline, the client fakes responses via `generateContextualResponse`.
7. **Premise 7 (Observation 1.3)**: The overall Ultron backend already contains full multi-provider LLM infrastructure (`CloudEngine`, `OllamaEngine`, `cloud_router.py`, `QueryOrchestrator`), but the hologram route is not wired to it.
8. **Conclusion**: Directives submitted via text or voice in the hologram must be connected directly to the user's active configured LLM inference pipeline (`system.ask` or `request.app.state.engine` / `cloud_router`), and all 6 cataloged canned mock/regex response blocks must be removed.

---

## 3. Caveats

- **No Caveats** regarding the survey scope: all directive submission paths, backend routers, LLM provider pipelines, credentials, canned responses, and test runners were thoroughly inspected and verified.
- Downstream warning: `tests/server/test_hologram_theme.py` currently asserts the existence of Crimson and Emerald theme buttons (`id="theme-btn-crimson"`, `id="theme-btn-emerald"`). When R4 (streamlining to single Cyan accent) is implemented, the test file must be updated accordingly.

---

## 4. Conclusion

1. **R5 Brain Routing Blueprint**:
   - Refactor `UltronBrain` in `src/openjarvis/server/llm_client.py` into a unified brain router that checks `system.ask()`, `request.app.state.engine`, or configured cloud/local providers (`cloud_router` / `CloudEngine` / `OllamaEngine`).
   - In `src/openjarvis/server/app.py`, ensure `create_app()` automatically constructs a fallback `JarvisSystem` with the active engine and tools if `system` is not explicitly passed.
   - Forward real tool execution telemetry (`actions`: name, arguments, success, status, output) back to the hologram interface.
2. **Canned Mock Removal**:
   - Remove `generateContextualResponse` in `src/openjarvis/server/static/hologram.html` and `frontend/public/hologram.html`.
   - Remove the artificial dummy file creation (`D:/Ultron new create file.txt`) from `execute_real_system_action` in `src/openjarvis/server/hologram_routes.py`.
   - Remove `_smart_local_reasoning`'s canned trivia and static defaults from `src/openjarvis/server/llm_client.py`.
   - Remove static fallback text (`Directive received: '{directive}'...`) from `src/openjarvis/server/hologram_routes.py`.

---

## 5. Verification Method

### 5.1 Test Suites Execution
Run pytest using the workspace virtual environment:
```powershell
.venv\Scripts\pytest.exe tests/server/test_hologram.py tests/server/test_hologram_theme.py tests/server/test_llm_client.py
```
Expected output: All 71 tests pass cleanly.

### 5.2 Server Execution
Start the API and Hologram server:
```powershell
.venv\Scripts\python.exe -m openjarvis.server
```
Navigate to `http://localhost:8000/hologram` and verify the interface loads.

### 5.3 Files to Inspect
- `src/openjarvis/server/hologram_routes.py` (lines 148–330, lines 544–750)
- `src/openjarvis/server/llm_client.py` (lines 220–446)
- `src/openjarvis/server/static/hologram.html` (lines 2179–2268)
- `frontend/public/hologram.html` (lines 2179–2268)
- `src/openjarvis/server/cloud_router.py` (lines 121–200, 700–794)
- `src/openjarvis/engine/cloud.py` (lines 80–120)
