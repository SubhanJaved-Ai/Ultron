<div align="center">
  <h1>⚡ ULTRON</h1>
  <p><b>Autonomous AI Digital Execution Assistant</b></p>
  <p><i>Evolved from OpenJarvis 2.0 with Hermes-Grade Intelligence, n8n-Grade Automations & 3D Holographic Interface.</i></p>

  <p>
    <a href="https://arxiv.org/abs/2605.17172"><img src="https://img.shields.io/badge/arXiv-2605.17172-b31b1b.svg" alt="arXiv"></a>
    <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License">
    <img src="https://img.shields.io/badge/wake_words-Ultron%20%7C%20Jarvis-yellow" alt="Wake Words">
    <img src="https://img.shields.io/badge/memory-Local%20%7C%20Supabase-success" alt="Memory Isolation">
  </p>
</div>

---

> *"I am your digital execution assistant, not just ChatGPT who can just give you the answer. You just give me the task and I will do it."* — **Ultron**

---

## 🏛️ Project Origin, Attribution & Evolution

### A. Project Origin

**Ultron** is an independently maintained downstream derivative of **[OpenJarvis](https://github.com/open-jarvis/OpenJarvis)**, an open-source personal AI agent framework originally developed by **The OpenJarvis Authors** at Stanford University under the [Apache License 2.0](LICENSE).

Ultron is maintained and extended by **Subhan Javed** ([@SubhanJaved-Ai](https://github.com/SubhanJaved-Ai)). It is an independent downstream project and is not an official OpenJarvis release, nor is it endorsed or sponsored by the upstream OpenJarvis authors or Stanford University.

Key provenance and licensing references:
- **Upstream Repository:** [https://github.com/open-jarvis/OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
- **Software License:** [Apache License 2.0](LICENSE) (`Copyright 2025 The OpenJarvis Authors`)
- **Attribution & Notices:** [NOTICE](NOTICE) (`Copyright 2026 Subhan Javed for Ultron-specific modifications`)
- **Foundational Research Paper:** Jon Saad-Falcon et al., *"OpenJarvis: Personal AI, On Personal Devices"*, Stanford SAIL / Hazy Research / Scaling Intelligence Lab ([arXiv:2605.17172](https://arxiv.org/abs/2605.17172))

*Provenance Note on Upstream Git History:* The Ultron repository was initialized from an imported snapshot reflecting OpenJarvis post-release v1.0.2 (May 2026). Because the upstream Git commit graph was not imported during the initial repository setup, no exact upstream commit SHA is claimed or fabricated.

---

### B. Capabilities in the OpenJarvis Baseline

Based on source verification of the imported baseline snapshot, the original OpenJarvis framework provided the following foundational capabilities prior to Ultron-specific development:

1. **Five-Primitives Architecture:** Composable modular architecture separating intelligence into *Intelligence* (`openjarvis.intelligence`), *Engine* (`openjarvis.engine`), *Agents* (`openjarvis.agents`), *Tools & Memory* (`openjarvis.tools`, `openjarvis.memory`), and *Learning* (`openjarvis.learning`).
2. **Python Framework, API Server & CLI:** Core Python backend runtime (`openjarvis`), asynchronous FastAPI server (`openjarvis.server`), and Click-driven terminal CLI (`jarvis`).
3. **Agent, Tool & Evaluation Infrastructure:** Foundational ReAct and planner agent loops, shell/filesystem/search tool primitives, FAISS/ColBERT/BM25 local memory indexing, and research benchmark suites (TauBench, WebChoreArena, ToolCall-15, LifelongAgentBench, PinchBench).
4. **Hardware Energy Telemetry & Rust Extensions:** Real-time hardware energy and FLOPs telemetry across NVIDIA GPUs (NVML) and Apple Silicon (RAPL/ANE via `zeus-apple-silicon`), accompanied by a native Rust workspace (`rust/crates/openjarvis-*`) providing PyO3 bindings for token mathematics, loop guards, and SQLite FTS5 search.
5. **Messaging Connectors & Baseline Skill Sources:** Connectors for Telegram, WhatsApp, Slack, Discord, and iMessage (`openjarvis.channels`), alongside external skill loaders for OpenClaw and Hermes.
6. **Baseline Desktop Shell & Chat Frontend:** Foundational Tauri v2 desktop shell and React chat interface.

---

### C. What Ultron Adds

> **Scope Note:** The comparison below is made specifically against the imported OpenJarvis baseline snapshot. Upstream OpenJarvis continues to evolve independently, and these comparisons do not claim that features are permanently absent from all past, concurrent, or future upstream versions.

| Capability | OpenJarvis Baseline | Ultron-Specific Development |
| :--- | :--- | :--- |
| **3D Holographic WebGL/PWA Interface & Voice Barge-In** | 2D React chat interface and standard settings dashboard (`frontend/src/pages/ChatPage.tsx`). | Single-file 3D WebGL particle core ([`hologram.html`](src/openjarvis/server/static/hologram.html)), offline PWA service worker ([`sw.js`](src/openjarvis/server/static/sw.js)), audio-reactive visualization, ambient wake-word recognition, and real-time voice interruption/barge-in ([`hologram_routes.py`](src/openjarvis/server/hologram_routes.py), [`test_hologram.py`](tests/server/test_hologram.py)). |
| **Global Emergency Stop & Cancellation Architecture** | Ephemeral per-agent cancellation flags within task loops; no centralized process-tree termination. | Dual-mode `CancellationToken` framework (`threading.Event` + `asyncio.Event`), thread-safe `ActiveExecutionContextStore` ([`cancellation.py`](src/openjarvis/server/cancellation.py)), authenticated REST cancellation route ([`cancellation_routes.py`](src/openjarvis/server/cancellation_routes.py)), OS process-tree termination (`kill_process_tree`), browser teardown binding, and native global hotkey hook (`Ctrl+Alt+Escape`) in desktop shell ([`test_cancellation_wiring.py`](tests/server/test_cancellation_wiring.py)). |
| **Ultron Safety Kernel & Execution Guardrails** | AST parsing, basic capability lists, and static tool policy checks. | Centralized `SafetyKernel` with 4-tier risk classification (Tier 0 Safe to Tier 3 Critical), PBKDF2 safety passcodes, safe quarantine fallback, zero-deletion guardrails, and Windows root directory modification blockades ([`kernel.py`](src/openjarvis/security/kernel.py), [`safety_routes.py`](src/openjarvis/server/safety_routes.py), [`test_safety_kernel.py`](tests/security/test_safety_kernel.py)). |
| **Desktop Application Discovery, Catalog RAG & Orchestration** | Standard command-line execution via `shell_exec`. | `SystemCatalogRAG` indexing local installed applications, Chrome profiles, and Start Menu shortcuts ([`catalog_rag.py`](src/openjarvis/desktop/catalog_rag.py)), integrated with `DesktopOrchestrator` for native application launching, window focus management, and desktop automation primitives ([`orchestrator.py`](src/openjarvis/desktop/orchestrator.py), [`test_desktop_orchestrator.py`](tests/server/test_desktop_orchestrator.py)). |
| **Browser Automation & Desktop Runtime Packaging** | Playwright declared as an optional library dependency in `pyproject.toml`. | Integrated Playwright tool loop ([`browser.py`](src/openjarvis/tools/browser.py)) with session-to-cancellation binding, automated Chromium bundling scripts, and standalone Windows desktop packaging with embedded portable Python 3.12 runtime. |
| **Persistent Task Execution & DAG Skill Composition** | In-memory agent loop; task state lost upon process exit or disconnect. | SQLite-backed persistent task runner (`tasks` and `task_steps` tables), state machine lifecycle (`QUEUED` -> `RUNNING` -> `COMPLETED`/`FAILED`) ([`runner.py`](src/openjarvis/tasks/runner.py), [`store.py`](src/openjarvis/tasks/store.py)), DAG skill composition engine with cycle detection ([`composition.py`](src/openjarvis/skills/composition.py)), and dedicated Task Center UI ([`test_persistent_task_runner.py`](tests/tasks/test_persistent_task_runner.py)). |
| **Cloud Usage/Cost Ledger & Resource Controls** | Hardware energy telemetry (NVML / Apple Silicon) and raw token accounting in engine. | Auditable SQLite `cloud_usage_ledger` recording token usage, provider pricing registry (`2026-10-v1`), request-id idempotency, CSV export ([`usage_ledger.py`](src/openjarvis/traces/usage_ledger.py), [`pricing.py`](src/openjarvis/intelligence/pricing.py)), and token-bucket RPM/TPM resource limiter ([`resource_limiter.py`](src/openjarvis/engine/resource_limiter.py), [`test_usage_ledger.py`](tests/traces/test_usage_ledger.py)). |
| **Multilingual Speech Routing & Additional TTS Integrations** | Local Kokoro TTS, Faster-Whisper, and basic voice I/O. | Dynamic multilingual speech router supporting English, Urdu, and Hindi directives with truthful local vs. cloud capability reporting ([`router.py`](src/openjarvis/speech/router.py), [`test_multilingual_router.py`](tests/speech/test_multilingual_router.py)), and ElevenLabs cloud TTS backend ([`elevenlabs_tts.py`](src/openjarvis/speech/elevenlabs_tts.py), [`test_elevenlabs_provider.py`](tests/speech/test_elevenlabs_provider.py)). |
| **Pluggable Supabase/PostgreSQL/MongoDB Memory Adapters** | Local SQLite FTS5 and vector indices (FAISS, BM25). | Pluggable remote database storage adapter for private user-attached Supabase (PostgreSQL with `pgvector`) and MongoDB instances with strict tenant isolation and credential masking ([`memory_backend.py`](src/openjarvis/storage/memory_backend.py), [`memory_backend_manage.py`](src/openjarvis/tools/memory_backend_manage.py), [`test_tenant_isolation.py`](tests/security/test_tenant_isolation.py)). |
| **Additional n8n & Community Skill Integrations** | Built-in local skills and external source loaders (OpenClaw, Hermes). | Inbound event webhooks (`/webhooks/trigger/{slug}`), dedicated n8n automation bridge tool ([`n8n_tool.py`](src/openjarvis/tools/n8n_tool.py)), and ClawHub community skill tools ([`clawhub_tools.py`](src/openjarvis/tools/clawhub_tools.py)). |

---

### D. Design Direction and Difference

While **OpenJarvis** was developed as a foundational personal AI research framework exploring intelligence efficiency, on-device models, energy benchmarking, and primitive composability, **Ultron** directs its architecture toward an action-first personal execution assistant:

- **Action-Oriented Execution:** Prioritizes completing tasks directly via OS tools, subagents, and automations rather than generating conversational explanations.
- **Holographic & Audio-First Presence:** Introduces a lightweight 3D WebGL particle core with natural voice barge-in, allowing seamless conversational interruption.
- **Fail-Closed Execution Safety:** Enforces strict execution guardrails through the Safety Kernel and a global emergency stop mechanism to prevent unauthorized system modifications or runaway operations.
- **Resilient Workflows:** Employs SQLite-persisted task state machines and DAG composition, allowing long-running multi-step jobs to survive disconnects and system restarts.
- **Expanded Ecosystem Integration:** Connects desktop workflows directly to third-party automation tools (n8n, webhooks) and isolated cloud databases (Supabase, MongoDB).

---

### E. Author and Research Attribution

- **Ultron Development & Maintenance:** Ultron's downstream enhancements and ongoing maintenance are conducted by **Subhan Javed** ([@SubhanJaved-Ai](https://github.com/SubhanJaved-Ai) / `AirLuc`). All Ultron-specific additions are copyright 2026 Subhan Javed, subject to original and third-party notices.
- **Original OpenJarvis Collective Copyright:** The underlying OpenJarvis framework is Copyright 2025 The OpenJarvis Authors and is distributed under the [Apache License 2.0](LICENSE). Copyright over inherited OpenJarvis code has not transferred to Subhan Javed.
- **OpenJarvis Research Paper Authors:** The foundational academic work behind OpenJarvis is documented in the research paper *"OpenJarvis: Personal AI, On Personal Devices"* ([arXiv:2605.17172](https://arxiv.org/abs/2605.17172)). The authors of this research publication are:
  > Jon Saad-Falcon, Avanika Narayan, Robby Manihani, Tanvir Bhathal, Herumb Shandilya, Hakki Orhun Akengin, Gabriel Bo, Andrew Park, Matthew Hart, Caia Costello, Chuan Li, Christopher Ré, and Azalia Mirhoseini.
  
  *(Note: This list identifies the authors of the academic research paper affiliated with Stanford SAIL, Hazy Research, and the Scaling Intelligence Lab, and is recognized for academic context. It is not presented as an exhaustive legal register of software copyright holders.)*

For complete licensing terms, see [LICENSE](LICENSE). For full attribution records, see [NOTICE](NOTICE).

---

## ⚡ What is Ultron?

Unlike conventional chatbots that simply generate conversational text, **Ultron** is an autonomous, action-first personal AI system designed to do real work. Ultron speaks concisely, executes tasks directly, delegates to subagents, orchestrates multi-step automations, and runs 24/7 on your own hardware or free cloud instances without paid API lock-in.

### Key Capabilities
- 🎙️ **3D Holographic Interface & Voice Barge-In**: Real-time 3D WebGL core with ChatGPT-style voice interruption. Say *"Okay, okay"*, *"Stop"*, or tap the core to cut Ultron off mid-sentence and switch instantly to listening.
- 🎯 **Action-First & Crisp Persona**: Does not ramble or lecture. Gives to-the-point answers and prioritizes executing tasks via tools.
- 🗣️ **Dynamic Address Learning**: Learns how you prefer to be addressed (*"Call me Alex"*, *"Call me ma'am"*, *"Call me sir"*), storing your preference across all sessions without gender or title assumptions.
- 🧠 **Hermes-Grade Intelligence**: Self-improving skills with mutation ledger and atomic rollback, SQLite FTS5 cross-session recall (`session_search`), single-turn parallel subagent delegation (`delegate_task`), unified cron automation (`cronjob_manage`), and multi-environment sandboxing (Local, Docker, SSH).
- 🔄 **n8n-Grade Automations**: Inbound event webhooks (`/webhooks/trigger/{slug}`), visual multi-node DAG workflows (`workflow_manage`), and external n8n bridge integration (`n8n_manage`).
- 🔒 **100% Private, Isolated Memory**: Stores memory locally by default (SQLite + Markdown). Seamlessly attach your own private **Supabase (PostgreSQL with pgvector)** or MongoDB database—each database is dedicated exclusively to the user with zero data sharing.

---

## 🚀 Quick Start: Make Your Own Ultron Ready

Pick your preferred environment and have Ultron running in under 5 minutes:

### Option A: Local PC / Mac / Linux

```bash
# 1. Clone repository
git clone https://github.com/SubhanJaved-Ai/Ultron.git
cd Ultron

# 2. Install dependencies (using uv or pip)
pip install -e .

# 3. Configure environment
cp .env.example .env
# Set your preferred API key (e.g. GEMINI_API_KEY=... or OPENAI_API_KEY=...)

# 4. Launch Ultron 3D Holographic Interface
jarvis serve --hologram
```
Open **`http://localhost:8000/hologram`** in your browser. Click anywhere to synchronize the neural audio link, say *"Ultron"* or *"Jarvis"*, and assign your task!

---

### Option B: Free 24/7 Oracle Cloud VM (No PC Needed)

Deploy Ultron permanently to an **Always Free Oracle Cloud instance** (4 OCPU ARM, 24 GB RAM):

```bash
# Run the automated Oracle installer
curl -fsSL https://raw.githubusercontent.com/SubhanJaved-Ai/Ultron/main/deploy/oracle/install.sh | bash
```
See our complete [Oracle Cloud Deployment Guide](deploy/oracle/README.md) for step-by-step setup, firewall rules, and systemd service management.

---

## 🛠️ Step-by-Step: Making Ultron Ready for Your Work

### 1. Personalizing Ultron (Your Name & Preferred Title)
Ultron does not make assumptions about your identity or title. You can teach it how you wish to be addressed:
- In the Hologram voice interface or terminal, simply say:
  - *"Call me Alex"*
  - *"Call me ma'am"*
  - *"Call me sir"*
  - *"Call me Boss"*
- Ultron immediately stores your preference in `USER.md` and `user_preferences.json`. All future voice responses, briefings, and telemetry will address you accordingly.

---

### 2. Attaching Your Private Cloud Database (Supabase / PostgreSQL / MongoDB)
By default, Ultron stores all memory and session histories on your local host (SQLite + markdown). 

When deploying to Oracle Cloud or moving across devices, you can attach your own **free, isolated cloud database**:

#### Why Supabase?
- **Free Tier**: 500 MB PostgreSQL database with `pgvector` extension for vector embeddings.
- **Dedicated & Isolated**: Every user creates their own private Supabase project. **Zero multi-tenant data sharing**.

#### How to Attach:
1. Create a free database at [supabase.com](https://supabase.com).
2. Ask Ultron in chat or run the `memory_backend_manage` tool:
   ```bash
   jarvis ask "Attach my Supabase database: postgresql://postgres:[password]@db.[id].supabase.co:5432/postgres"
   ```
3. Check memory status anytime:
   ```bash
   jarvis ask "Where is my memory saved?"
   ```
   > *"Currently saving all memory and session data to your private SUPABASE database. Your data is completely isolated to your account and never shared with other services."*
4. Revert to local storage whenever you want:
   ```bash
   jarvis ask "Switch back to local memory"
   ```

---

### 3. Creating Real Automations & Workflows

Ultron is equipped with production-grade automation mechanics:

- **Inbound Event Webhooks**:
  Trigger Ultron workflows from GitHub, Stripe, or web forms:
  ```bash
  curl -X POST http://localhost:8000/webhooks/trigger/deploy-check \
    -H "Content-Type: application/json" \
    -d '{"event": "code_pushed", "repo": "main"}'
  ```
- **Visual & DAG Workflows**:
  Build multi-step execution graphs using `workflow_manage` with automated tool sequences, subagent steps, conditional branching, and full execution traces.
- **n8n Bridge Integration**:
  Connect Ultron to external n8n workflows via `n8n_manage` to trigger webhooks and automate third-party SaaS services.
- **Unified Scheduled Cronjobs**:
  Schedule tasks that run autonomously in the background:
  ```bash
  jarvis ask "Schedule a cron job to check system status every morning at 9 AM"
  ```

---

### 4. Self-Improving Skills & Subagent Delegation

Ultron features a mutation ledger with atomic rollbacks:
- **Patch & Rollback**: When optimizing code or skills, Ultron records full audit diffs in `.skill_ledger.jsonl` with content-addressed backups. If a modification breaks tests, it atomically rolls back.
- **Parallel Subagent Delegation**: Uses `delegate_task` to spawn worker pools for heavy search, scraping, or code analysis, rolling up results in a single turn.

---

### 5. CLI & Chat Commands

```bash
---

## 🏗️ Architecture & System Components

Ultron is structured as a modular, fail-closed system comprising five core components:

```mermaid
graph TD
    Client[Web & Desktop Clients<br/>React + Vite / Tauri v2 / 3D Argon Hologram] --> API[FastAPI Server Engine<br/>Security Headers, AuthMiddleware, WebSockets]
    API --> Safety[Safety Kernel & Policy Engine<br/>Sandboxing, Approval Gate, Resource Attribution]
    API --> AgentMgr[Agent Scheduler & Orchestrator<br/>DAG Runner, Retries, Channel Bridge]
    API --> MCP[MCP Adapter & Tool Registry<br/>StreamableHTTP / Stdio with SSRF & Shell Protection]
    AgentMgr --> Engines[Inference Engines<br/>Gemini, OpenAI, Claude, Local Ollama]
    AgentMgr --> Memory[Memory & Knowledge Engine<br/>Local SQLite FTS5 / Vector DB / Supabase]
```

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **Core Server** | FastAPI, Uvicorn, Python 3.12 | REST & WebSocket API, session handling, authentication middleware, streaming events |
| **Argon 3D Hologram** | Three.js / WebGL, Web Audio API | Live 3D matrix visualization, real-time voice barge-in, consciousness state FSM |
| **Web Dashboard** | React 19, TypeScript, Tailwind CSS, Lucide | Chat interface, persistent Task Center, MCP configuration, telemetry & memory browsing |
| **Safety Kernel** | Python Policy Guard, AST validators | Tool execution sandboxing, dangerous command blocking, emergency stop interrupt |
| **MCP Client & Adapter** | StreamableHTTPTransport, StdioTransport | Model Context Protocol integration, dynamic tool discovery, SSRF prevention |
| **Desktop Wrapper** | Tauri v2, Rust | Lightweight native desktop shell for Windows, macOS, and Linux |

---

## 💻 Prerequisites & Development Setup

### System Prerequisites
- **Python**: `>=3.10, <3.14` (Python 3.12 recommended).
- **Node.js**: `>=20.0.0` (Node 22 LTS recommended) and `npm >= 10`.
- **Rust** *(Desktop builds only)*: Stable Rust toolchain (`rustc`, `cargo`) + platform C++ build tools (MSVC on Windows, Xcode on macOS, build-essential on Linux).
- **LLM Provider**: At least one active API key (Google Gemini, OpenAI, Anthropic, OpenRouter) or a locally running [Ollama](https://ollama.com) instance.

### Development Workflow

1. **Clone and Virtual Environment**:
   ```bash
   git clone https://github.com/SubhanJaved-Ai/Ultron.git
   cd Ultron
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -e ".[dev,server,inference-cloud,browser]"
   cd frontend && npm install && cd ..
   ```

3. **Configure Environment Safely**:
   ```bash
   cp .env.example .env
   # Edit .env with your preferred keys (GEMINI_API_KEY, etc.)
   # Never commit .env or secrets to Git.
   ```

4. **Running the Servers**:
   - **Backend API & Hologram**:
     ```bash
     python -m openjarvis.cli serve --host 127.0.0.1 --port 8000 --hologram
     ```
     Access backend at `http://127.0.0.1:8000` and Hologram at `http://127.0.0.1:8000/hologram`.
   - **Frontend Development Server**:
     ```bash
     cd frontend
     npm run dev
     ```
     Access development frontend at `http://localhost:5173`.
   - **Production Frontend Build**:
     ```bash
     cd frontend
     npm run build
     ```
     Builds static assets into `src/openjarvis/server/static/` served directly by FastAPI.

---

## 🧪 Automated Testing & Verification

Ultron includes automated test suites covering backend routes, MCP security, multi-agent orchestration, and frontend components:

```bash
# 1. MCP Configuration, Security & Route Regression Tests
pytest tests/server/test_mcp_routes.py -v

# 2. Hologram & Channel API Tests
pytest tests/server/test_hologram.py tests/test_hologram_routes.py -v

# 3. Multi-Agent & Orchestrator Integration Tests
pytest tests/integration/test_orchestrator_integration.py -v

# 4. Frontend Unit & Component Tests
npm --prefix frontend test

# 5. Frontend TypeScript Typecheck & Production Build
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

---

## 🛡️ Safe Model Context Protocol (MCP) Configuration

Ultron integrates with external tools and agents via the Model Context Protocol (MCP). The implementation enforces strict security controls:

### Security Boundaries
- **SSRF Prevention**: Link-local addresses (`169.254.0.0/16`, `fe80::/10`) and cloud provider metadata services (`169.254.169.254`, `metadata.google.internal`, `100.100.100.200`, `fd00:ec2::254`) are strictly blocked.
- **Port Restrictions**: Non-HTTP privileged/internal service ports (e.g. 21, 22, 23, 25, 445, 1433, 3306, 3389, 5432, 6379) are disallowed.
- **Command Disallowlist**: Arbitrary shell execution via stdio transport is prevented by rejecting system shells and dangerous binaries (`cmd.exe`, `powershell`, `bash`, `sh`, `curl`, `wget`, `rm`, `del`).
- **Credential Masking & Sanitization**: Authorization tokens and passwords are redacted from server listings, browser UI, and diagnostics errors (`[REDACTED]`).
- **Authorization**: Configuration mutations and connection diagnostics require administrator privileges (`Role.ADMIN`).

### Testing MCP Connections Safely
In the web dashboard under **Settings → MCP Servers**, you can verify protocol connectivity:
- **Deterministic Mock Server**: Set URL to `http://127.0.0.1:8000/api/mcp/mock-server`. Click **Test Connection** to verify JSON-RPC `initialize` and `tools/list` handshake with zero external dependencies.
- **Remote HTTP Server**: Enter valid HTTPS endpoint and optional bearer token.
- **Local Stdio Server**: Enter a dedicated tool binary (e.g. `npx`, `python`) and safe argument list.

---

## 🔧 Troubleshooting Guide

### 1. Unavailable LLM Providers
- **Symptom**: `AuthenticationError` or `Provider API key not configured`.
- **Remedy**: Ensure `GEMINI_API_KEY` (or `OPENAI_API_KEY`) is set in `.env` without surrounding quotes or trailing whitespace. Alternatively, start a local [Ollama](https://ollama.com) instance on `http://127.0.0.1:11434` for 100% offline local inference.

### 2. MCP Connection Failures & Timeouts
- **Symptom**: Red `Unreachable` badge or `Failed to connect to MCP server`.
- **Remedy**:
  - Verify that the target server is active and reachable on the specified port.
  - If connecting locally, ensure the target is bound to `127.0.0.1` or `localhost`.
  - Check that the destination port is not in the restricted port list (e.g. avoid port 22, 25, 445).
  - Cloud metadata addresses (`169.254.169.254`) are blocked by design.

### 3. Optional Document Parsers & Speech Backends
- **PDF Extraction**: If `pdfplumber` is not installed, install via `pip install ".[pdf]"`.
- **Local Kokoro TTS**: Requires `pip install ".[voice]"`. On Linux/macOS, `espeak-ng` should be installed on PATH for out-of-dictionary phonemes. If unavailable, Ultron gracefully falls back to browser Web Speech API.

---

## 🖥️ Desktop Build & Verification Status

| Platform | Target | Build Status | Runtime Verification Status |
|----------|--------|--------------|-----------------------------|
| **Windows x64** | `x86_64-pc-windows-msvc` | Verified via GitHub Actions CI (`desktop.yml`) | **PASS (Standalone Bundle)**: Self-contained portable Python 3.12 runtime and native binary packaged in `openjarvis-desktop-windows-x64`. Local build requires manual Rust toolchain installation. |
| **Linux x64** | `x86_64-unknown-linux-gnu` | Verified via GitHub Actions CI (`ubuntu-22.04`) | **PASS (CI Runner)**: WebKit2GTK + GTK3 native build verified in CI. Not run locally on Windows host. |
| **macOS Universal** | `universal-apple-darwin` (`aarch64` + `x86_64`) | Verified via GitHub Actions CI (`macos-14`) | **PASS (CI Runner)**: Universal binary with automated Apple notarization preflight. Not run locally on Windows host. |

---

## ⚠️ Known Limitations

1. **Local Windows Compilation**: Building native desktop installers (`.msi` / `.exe`) directly on a local Windows machine requires installing Rust (`rustup`), Cargo, and Visual Studio C++ Build Tools. In environments without Rust installed, use the pre-built GitHub Actions standalone bundle or run the Python server with the web frontend.
2. **Platform-Specific Shell Tasks**: Persistent DAG tasks planned by autonomous agents generate commands tailored to the target operating system. Windows hosts should use PowerShell/cmd-compatible directives (e.g. `hostname`, `dir`, `ipconfig`) rather than Linux-specific utilities (`free`, `df`).
3. **Optional Channel Integrations**: Third-party messaging connectors (SendBlue, Telegram, Slack, Discord) require valid external provider API keys to establish live outbound webhooks. Unconfigured channels remain in inactive/standby mode.

---

## Community

## About

OpenJarvis is part of [Intelligence Per Watt](https://www.intelligence-per-watt.ai/), a research initiative studying the intelligence efficiency of AI systems. The project is developed at [Hazy Research](https://hazyresearch.stanford.edu/) and the [Scaling Intelligence Lab](https://scalingintelligence.stanford.edu/) at [Stanford SAIL](https://ai.stanford.edu/).

## Sponsors

<p>
  <a href="https://www.laude.org/">Laude Institute</a> &bull;
  <a href="https://datascience.stanford.edu/marlowe">Stanford Marlowe</a> &bull;
  <a href="https://cloud.google.com/">Google Cloud Platform</a> &bull;
  <a href="https://lambda.ai/">Lambda Labs</a> &bull;
  <a href="https://ollama.com/">Ollama</a> &bull;
  <a href="https://research.ibm.com/">IBM Research</a> &bull;
  <a href="https://hai.stanford.edu/">Stanford HAI</a>
</p>

## Citation
```bibtex
@misc{saadfalcon2026openjarvispersonalaipersonal,
      title={OpenJarvis: Personal AI, On Personal Devices}, 
      author={Jon Saad-Falcon and Avanika Narayan and Robby Manihani and Tanvir Bhathal and Herumb Shandilya and Hakki Orhun Akengin and Gabriel Bo and Andrew Park and Matthew Hart and Caia Costello and Chuan Li and Christopher Ré and Azalia Mirhoseini},
      year={2026},
      eprint={2605.17172},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/2605.17172}, 
}
```

## License

This project is licensed under the [Apache License 2.0](LICENSE).  
See the [NOTICE](NOTICE) file for original OpenJarvis attribution, Stanford research acknowledgments, and Ultron-specific copyright notices.

