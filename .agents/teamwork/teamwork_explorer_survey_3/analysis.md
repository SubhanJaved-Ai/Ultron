# Survey 3: Unified System Brain Model Routing & Mock Removal Analysis

## Executive Summary

This report documents the architectural investigation into **R5: Unified System Brain Model Routing**, the active LLM inference pipeline of Ultron, the complete inventory of 1990s-style canned mock and regex fallback responses, and the test/backend verification infrastructure.

Currently, user directives submitted through the 3D Hologram interface (via text or voice) do **not** route through the overall Ultron system's configured LLM inference pipeline. Instead:
1. Directives are intercepted by hardcoded regex pattern matching (`execute_real_system_action` in `hologram_routes.py`), which executes hardcoded scripts or creates a synthetic dummy text file (`Ultron new create file.txt`) with an ASCII banner.
2. If unhandled by regex, execution falls back to `request.app.state.system.ask()`, which is `None` in the standard server entry point (`python -m openjarvis.server`).
3. If `system` is `None` or fails, it calls `ultron_brain.generate_response()` in `llm_client.py`. That class is strictly coupled to Google Gemini (`google.genai.Client`) and completely ignores Anthropic Claude, OpenAI, OpenRouter, Groq, DeepSeek, and local Ollama models.
4. If no Gemini API key is present or Gemini calls fail, `UltronBrain` falls back to `_smart_local_reasoning()`, which is a collection of 1990s-style canned strings (e.g. static temperatures in Islamabad/Lahore/Karachi, canned challenge responses, and fixed boilerplate).
5. If the backend fails or times out, the client-side JavaScript in `hologram.html` falls back to `generateContextualResponse()`, producing static canned strings for diagnostics, vocal articulation, and the soul circuit.

This analysis provides verified file paths, line numbers, architecture diagrams, an exact inventory of all mock responses, and an actionable integration blueprint to connect the hologram directly to the user's active configured LLM brain across all providers.

---

## 1. Hologram Directive Pipeline Flow (UI to Backend)

### 1.1 Inbound User Transmission in Hologram Interface
Located in:
- `src/openjarvis/server/static/hologram.html`
- `frontend/public/hologram.html`

The hologram UI accepts user inputs through three modalities:
1. **Command Input Bar**: Submitting form `#command-form` with input `#ultron-input` (line 2735):
   ```javascript
   document.getElementById('command-form').addEventListener('submit', (e) => {
     e.preventDefault();
     const val = inputEl.value.trim();
     if (!val) { toggleListeningMode(); return; }
     handleUserSubmission(val);
     inputEl.value = '';
   });
   ```
2. **Directive Chips**: Pre-set buttons in `.quick-directives-bar` (line 2611):
   Clicking chips like "Diagnostic Scan", "Test Vocal Articulation", "Soul Circuit Status", or "Verify Safety Kernel" calls `handleUserSubmission(promptText)`.
3. **Voice Activation**: The `#btn-mic` button or clicking the canvas triggers `toggleListeningMode()` (line 2652).
   - Uses Web Speech API: `SpeechRecognition` / `webkitSpeechRecognition` (line 2690).
   - Configures microphone audio constraints (`autoGainControl: true`, `echoCancellation: true`, `noiseSuppression: true`).
   - Collects transcript chunks (`finalChunk + interimChunk`).
   - Checks phonetic wake words (`alton`, `oltron`, `ultra`, `ultron`, `jarvis`) (line 2714).
   - Uses `silenceTimer` with `SILENCE_DEBOUNCE_MS = 1600` (line 2719) to invoke `handleUserSubmission(currentSpeech)`.

### 1.2 Submission Handler (`handleUserSubmission`)
Located in:
- `src/openjarvis/server/static/hologram.html` (lines 2196–2268)
- `frontend/public/hologram.html` (lines 2196–2268)

```javascript
async function handleUserSubmission(rawText) {
  const text = (rawText || '').trim();
  if (!text) return;

  const historyItems = loadChatHistory().slice(-8);
  const nowStr = new Date().toTimeString().slice(0, 8);
  appState.chatHistory.push({ role: 'user', time: nowStr, text: text });
  persistChatHistory(appState.chatHistory);
  updateChatLogCount();
  logDirective(`Input: "${text.slice(0, 36)}${text.length > 36 ? '...' : ''}"`);

  emitToHost('USER_TRANSMIT', { text: text, timestamp: Date.now() });

  clearInterval(activeSpeechTimer);
  clearTimeout(activeThinkingTimer);
  setOperationalState('THINKING');
  if (responseTextEl) {
    responseTextEl.textContent = 'SYNTHESIZING QUANTUM NEURAL RESPONSE...';
  }

  try {
    const resp = await fetch('/api/hologram/directive', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(appState.authToken ? { 'Authorization': `Bearer ${appState.authToken}` } : {})
      },
      body: JSON.stringify({
        directive: text,
        history: historyItems
      })
    });

    if (resp.ok) {
      appState.backendConnected = true;
      const data = await resp.json();
      const reply = data.reply || generateContextualResponse(text);
      ...
      streamUltronResponse(reply);
      return;
    }
  } catch (err) {
    // Graceful fallback to standalone engine
  }

  activeThinkingTimer = setTimeout(() => {
    if (appState.operationalState !== 'THINKING') return;
    const reply = generateContextualResponse(text);
    ...
    streamUltronResponse(reply);
  }, 1150);
}
```

---

## 2. Backend Directive Processing Analysis

File: `src/openjarvis/server/hologram_routes.py` (lines 148–750)

Endpoint: `POST /api/hologram/directive`

When `handle_directive(request: Request, payload: dict)` is reached:
1. **Security Guardrail (Prompt Injection)**:
   Lines 574–598: `InjectionScanner().scan(directive)` blocks malicious injection patterns.
2. **User Preference Interception**:
   - Lines 600–613: Matches `"call me ..."` or `"my name is ..."` and calls `set_user_address()`.
   - Lines 615–628: Matches memory queries (`"where is my memory saved"`).
   - Lines 630–647: Matches identity queries (`"who am i"`, `"what is my name"`).
3. **Cancellation Token Registration**:
   Lines 649–665: Registers execution context in `ActiveExecutionContextStore` (`ctx-holo-...`).
4. **Hardcoded Regex Intercept (`execute_real_system_action`)**:
   Lines 668–670:
   ```python
   real_action = execute_real_system_action(directive, user_addr=user_addr)
   if real_action is not None:
       return real_action
   ```
   Inside `execute_real_system_action`:
   - Lines 194–216: Zero-deletion guardrail regex.
   - Lines 219–330: File creation regex. Creates fixed dummy file `D:/Ultron new create file.txt` with a canned template.
   - Lines 334–346: `get_desktop_orchestrator().handle_directive(clean)`
   - Lines 351–414: Browser search regex (`webbrowser.open(url)`).
   - Lines 418–458: Application launcher regex (notepad, calc, cmd, terminal, etc.).
   - Lines 462–485: Desktop screenshot capture regex (`ImageGrab.grab()`).
   - Lines 490–517: Disk space inspection regex (`shutil.disk_usage`).
   - Lines 521–538: Clock and date inspection regex (`datetime.datetime.now()`).
5. **System Brain Execution Step 1 (`system.ask`)**:
   Lines 673–719:
   ```python
   system = getattr(request.app.state, "system", None)
   if system is not None and hasattr(system, "ask"):
       result = await asyncio.to_thread(system.ask, directive, **ask_kwargs)
       ...
       return {
           "reply": result["content"],
           "actions": normalized_actions,
           "status": "executed",
       }
   ```
   **Critical Defect**: In `src/openjarvis/server/__main__.py`, `app = create_app()` is called with **no arguments**. `system` defaults to `None`. Therefore, running the server directly skips `system.ask()` entirely!
6. **System Brain Execution Step 2 (`ultron_brain.generate_response`)**:
   Lines 720–740:
   ```python
   reply = await asyncio.to_thread(
       ultron_brain.generate_response, directive, history=history
   )
   return {"reply": reply, "status": "brain_executed"}
   ```
7. **Static Final Fallback**:
   Lines 742–746:
   ```python
   addr_suffix = f", {user_addr}" if user_addr else ""
   return {
       "reply": f"Directive received: '{directive}'. Ready to execute your operational objective{addr_suffix}. Please specify any target parameters.",
       "status": "fallback",
   }
   ```

---

## 3. Active Configured LLM Inference Pipeline Across Ultron

### 3.1 Credential & Configuration Hierarchy
The overall Ultron system resolves LLM credentials and configuration from the following cascade:

| Source | File / Location | Handled In |
|---|---|---|
| Environment Variables | OS process environment | `os.environ` (highest precedence) |
| Workspace `.env` | `d:\Ultron\.env` | `openjarvis.core.paths._find_source_root()` |
| User Cloud Keys | `~/.openjarvis/cloud-keys.env` | `openjarvis.server.cloud_router._load_keys()` |
| Tool Credentials | `~/.openjarvis/credentials.toml` | `openjarvis.core.credentials.load_credentials()` |
| Main Configuration | `~/.openjarvis/config.toml` | `openjarvis.core.config.load_config()` |
| Active Engine/Model State | `~/.openjarvis/inference.json` | `openjarvis.cli.serve` & Settings UI |

Current `.env` file content at `d:\Ultron\.env`:
```env
GEMINI_API_KEY=AQ.Ab8RN6I46Hjf4xBr3rlOCOzpacOJdw2i3wJZ-_l95_4mM27QlQ
GOOGLE_API_KEY=AQ.Ab8RN6I46Hjf4xBr3rlOCOzpacOJdw2i3wJZ-_l95_4mM27QlQ
```
Template `.env.example` (lines 38–63) documents support for:
- `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Google Gemini)
- `OPENAI_API_KEY` (OpenAI GPT-4o, GPT-5, o3-mini)
- `ANTHROPIC_API_KEY` (Anthropic Claude 3.5 Sonnet, Claude 3.7)
- `OPENROUTER_API_KEY` (OpenRouter unified gateway)
- `GROQ_API_KEY` (Groq LPU ultra-low latency)
- `DEEPSEEK_API_KEY` (DeepSeek-V3, DeepSeek-R1)
- `OLLAMA_HOST` (Local Ollama offline server, default `http://localhost:11434`)

### 3.2 Registered Inference Engines
Registered in `openjarvis.core.registry.EngineRegistry`:
- `cloud`: `CloudEngine` (`src/openjarvis/engine/cloud.py`) supporting OpenAI, Anthropic, Google Gemini, MiniMax, DeepSeek, Atlas Cloud.
- `ollama`: `OllamaEngine` (`src/openjarvis/engine/ollama.py`) for local on-device models.
- `afm`: Apple Foundation Models (`src/openjarvis/engine/apple_fm.py`).
- `litellm`: LiteLLM (`src/openjarvis/engine/litellm.py`).
- `nim`: NVIDIA NIM (`src/openjarvis/engine/nim.py`).
- OpenAI-compatible backends: `vllm`, `llamacpp`, `sglang`, `mlx`, `lmstudio`, `exo`, `nexa`, `uzu`, `lemonade`.
- `multi`: `MultiEngine` (`src/openjarvis/engine/multi.py`) for multi-backend aggregation.

### 3.3 Direct Cloud Streaming Router (`cloud_router.py`)
File: `src/openjarvis/server/cloud_router.py` (lines 1–794)
- Implements direct `httpx` async streaming to cloud providers without external SDK dependencies.
- Provider detection via `get_provider(model)`:
  - `openai`: `gpt-*`, `o1-*`, `o3-*`, `chatgpt-*`
  - `anthropic`: `claude-*`
  - `google`: `gemini-*`
  - `minimax`: `MiniMax-*`
  - `atlascloud`: `atlascloud/*`
  - `openrouter`: any `organization/model` format (e.g. `meta-llama/llama-3-8b`)

### 3.4 System Orchestrator & Autonomous Agent Pipeline
File: `src/openjarvis/system/orchestrator.py` (lines 17–341)
- `QueryOrchestrator.ask(query)`:
  1. Injects long-term memory facts if `context_from_memory` is enabled.
  2. Runs query through an agent (e.g. `native_react`, `react`, `simple`) with registered tools (browser, filesystem, calculator, web search, shell).
  3. Or executes direct completion via `s.engine.generate(messages, model=s.model)`.
  4. Returns:
     ```python
     {
         "content": result.content,
         "tool_results": [...],
         "turns": turns,
         "model": s.model,
         "engine": s.engine_key,
     }
     ```

---

## 4. Comprehensive Inventory of 1990s Canned Mock & Regex Responses

The investigation identified **6 distinct locations** where 1990s-style mock responses and regex fallbacks reside:

| # | File Path | Line Numbers | Mechanism | Verbatim Pattern / Mock Content |
|---|---|---|---|---|
| **M1** | `frontend/public/hologram.html`<br>`src/openjarvis/server/static/hologram.html` | 2179–2194 | JavaScript string matching (`generateContextualResponse`) | - "DIAGNOSTIC COMPLETE: All 12 cortical gyri lobes, 56 branching dendritic pathways, and 3,800+ electronic particle nodes are operating at 99.8% quantum coherence."<br>- "NEURAL RESONANCE ENGAGED: Watch the inner synaptic core and cortical folds pulse with real-time harmonic energy across every spoken syllable."<br>- "SOUL CIRCUIT MATRIX: Synaptic harmonics locked at..."<br>- "SAFETY KERNEL ENFORCED: All tool execution hooks..."<br>- "DIRECTIVE PROCESSED: '{query}' — Synthesizing multi-vector solution across the Ultron Neural Consciousness Matrix." |
| **M2** | `frontend/public/hologram.html`<br>`src/openjarvis/server/static/hologram.html` | 2258–2268 | JavaScript network failure timer | When backend fails or times out, executes `setTimeout(..., 1150)` that calls `generateContextualResponse(text)` and fakes successful completion. |
| **M3** | `src/openjarvis/server/hologram_routes.py` | 219–330 | Python regex intercept in `execute_real_system_action` | Matches `create|make|write...file` or `"ultron new create file"`. Writes hardcoded synthetic file `D:/Ultron new create file.txt` with boilerplate ASCII banner:<br>`"ULTRON AUTONOMOUS SYSTEM - REAL FILE VERIFICATION RECORD\n..."` |
| **M4** | `src/openjarvis/server/hologram_routes.py` | 742–746 | Hardcoded final fallback in `handle_directive` | `f"Directive received: '{directive}'. Ready to execute your operational objective{addr_suffix}. Please specify any target parameters."` |
| **M5** | `src/openjarvis/server/llm_client.py` | 312–416 | Python regex pattern matching in `_smart_local_reasoning` | - Weather query for Pakistan: "In Pakistan, conditions vary across climate zones: Islamabad is currently averaging around 24°C (75°F), Lahore is at 28°C (82°F), and Karachi is around 31°C (88°F) with humid coastal weather."<br>- Weather query for other regions: "Current regional telemetry for {target_loc} indicates moderate conditions with average temperatures around 22°C to 26°C."<br>- Challenge queries ("are you dull", "are you stupid"): "Hardly... I am Ultron—an autonomous digital execution assistant..."<br>- Default fallback: "Understood... I have processed your directive: '{query}'. Ready to proceed with execution—specify any additional parameters or target paths." |
| **M6** | `src/openjarvis/server/autonomous_intelligence.py` | 28–74 & 201–350 | Static dictionary & Wikipedia REST API scraping | `_INSTANT_KNOWLEDGE` dictionary containing fictional Stark Industries references ("Arc Reactor is an advanced clean fusion power generator developed by Stark Industries..."), Wikipedia scraping (`_query_wikipedia_summary`), and regex pattern matching. |

---

## 5. Architectural Blueprint for Unified System Brain Routing

To achieve the requirements of **R5 (Unified System Brain Model Routing)**, the following architectural integration must be implemented:

```
[ Hologram UI: Voice / Text Directive ]
                    │
                    ▼
     POST /api/hologram/directive
                    │
                    ▼
    [ Input Guardrails & Address Memory ]
                    │
                    ▼
┌──────────────────────────────────────────────────────────┐
│          UNIFIED SYSTEM BRAIN ADAPTER                    │
│                                                          │
│  1. Check request.app.state.system (JarvisSystem)        │
│     ├── If wired: system.ask(directive)                  │
│     └── Executes active Agent with Real Tools (Desktop,  │
│         Browser, Shell, Filesystem, Memory)              │
│                                                          │
│  2. If system is None or raises:                         │
│     ├── Check request.app.state.engine (InferenceEngine) │
│     └── engine.generate(messages, model=model)           │
│                                                          │
│  3. If app.state.engine is unconfigured / mock:          │
│     ├── Query get_engine(load_config())                  │
│     └── Connects to user's active configured LLM:        │
│         • Google Gemini (GEMINI_API_KEY / GOOGLE_KEY)    │
│         • Anthropic Claude (ANTHROPIC_API_KEY)           │
│         • OpenAI ChatGPT (OPENAI_API_KEY)                │
│         • OpenRouter Unified (OPENROUTER_API_KEY)        │
│         • Local Ollama / Qwen / Llama (OLLAMA_HOST)      │
│                                                          │
│  4. Return Intelligent LLM Response + Real Tool Actions  │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
        JSON Response to Hologram
  {
    "reply": "Articulate LLM brain answer",
    "actions": [ { "name": "...", "status": "executed", "output": "..." } ],
    "status": "executed"
  }
                    │
                    ▼
[ Hologram Audio Synthesis & Speech Output: /api/tts ]
```

### Key Integration Points:
1. **Refactor `UltronBrain` in `src/openjarvis/server/llm_client.py`**:
   - Upgrade `UltronBrain` from a Gemini-only client to a unified model router.
   - Detect and support all configured providers in `os.environ` / `.env` / `cloud-keys.env`:
     - Gemini (via `google.genai` or `cloud_router`)
     - Anthropic (via `cloud_router._stream_anthropic` or `CloudEngine`)
     - OpenAI (via `cloud_router._stream_openai` or `CloudEngine`)
     - Ollama (via `OllamaEngine` on `http://localhost:11434`)
   - Remove `_smart_local_reasoning`'s canned weather, challenge, and default regex mocks.
2. **Auto-wire `system` in `src/openjarvis/server/app.py`**:
   - In `create_app()`, when `system is None` and `engine is not None`, automatically construct a fallback `JarvisSystem` with the active engine, config, and available tools, ensuring `system.ask()` is always available to `hologram_routes.py`.
3. **Clean up `src/openjarvis/server/hologram_routes.py`**:
   - Remove artificial regex file creation (`D:/Ultron new create file.txt`).
   - Remove static string fallback at lines 742–746.
   - Route directly to `system.ask(directive)` or `ultron_brain.generate_response(directive)`.
4. **Clean up Hologram Frontend (`hologram.html`)**:
   - Remove `generateContextualResponse` (lines 2179–2194).
   - In `handleUserSubmission`, display actual server responses or meaningful connection errors rather than fake canned replies.

---

## 6. Backend, Dev Server, and Test Verification Infrastructure

### 6.1 Server Runtime Architecture
- **Framework**: FastAPI (`^0.110`) with Uvicorn ASGI server.
- **Python Version**: Python 3.12 (Virtualenv at `d:\Ultron\.venv`).
- **Entry Points**:
  - Direct Hologram & API Server:
    ```powershell
    .venv\Scripts\python.exe -m openjarvis.server
    ```
    Binds to `http://0.0.0.0:8000`. Serves Hologram at `/hologram` and `/hologram.html`.
  - CLI Production Server:
    ```powershell
    uv run jarvis serve --hologram --port 8000
    ```
    Initializes full telemetry, scheduler, agent manager, and wires `JarvisSystem`.

### 6.2 Frontend Dev Server & Build Pipeline
- **Directory**: `d:\Ultron\frontend`
- **Framework**: React 19, TypeScript 5.8, Vite 8, Tailwind CSS v4.
- **Commands**:
  - Run dev server:
    ```powershell
    cd frontend; npm run dev
    ```
    Starts on `http://localhost:5173`. Proxies `/v1`, `/api`, `/health` to `http://localhost:8000`.
  - Production build:
    ```powershell
    cd frontend; npm run build
    ```
    Executes `tsc -b && vite build --outDir dist && vite build --outDir ../src/openjarvis/server/static`.
    Copies `frontend/public/hologram.html` into `src/openjarvis/server/static/hologram.html`.

### 6.3 Existing Test Suites & Verification Commands
- **Test Runner**: Pytest (`pytest-9.1.1`) located at `d:\Ultron\.venv\Scripts\pytest.exe`.
- **Hologram & LLM Client Test Execution**:
  ```powershell
  .venv\Scripts\pytest.exe tests/server/test_hologram.py tests/server/test_hologram_theme.py tests/server/test_llm_client.py
  ```
  **Verification Result**:
  - `tests/server/test_hologram.py`: 26 passed
  - `tests/server/test_hologram_theme.py`: 35 passed
  - `tests/server/test_llm_client.py`: 10 passed
  - **Total**: **71 tests passed (0 failures, 100% pass rate)**.
- **Repository Full Test Suite Command (from `Makefile`)**:
  ```powershell
  uv run pytest tests/ -n auto -q --tb=short -m "not live and not cloud and not hub"
  ```
- **Code Linting & Formatting**:
  ```powershell
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  ```

---

## 7. Downstream Recommendations for Implementation Team

1. **Synchronized HTML Files**: Remember that `frontend/public/hologram.html` and `src/openjarvis/server/static/hologram.html` must remain in exact synchronization.
2. **Test Assertions on Theme Buttons**: Note that `tests/server/test_hologram_theme.py` currently asserts `assert 'id="theme-btn-crimson"' in html` and `assert 'id="theme-btn-emerald"' in html`. When implementing R4 (removing Crimson/Emerald buttons for a unified Cyan theme), `test_hologram_theme.py` and `test_hologram.py` must be updated to align with the simplified Cyan accent.
3. **Model Routing Fallback Safety**: While removing 1990s canned responses, ensure that legitimate conversational questions about identity or greeting ("hello", "what is my name") continue to be gracefully handled by the LLM system prompt (`build_system_prompt`) so existing tests like `test_hologram_directive_endpoint` and `test_hologram_ask_question_never_hijacked_by_greeting` continue to pass.
