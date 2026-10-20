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

[Apache 2.0](LICENSE)
