# Jarvis 2.0 — Architecture, Vision & System Design Notes

> **Document Purpose**: Preserves the complete architectural analysis, design decisions, security specifications, and answers discussed regarding the Jarvis 2.0 platform, its relation to OpenClaw, Oracle Cloud deployment, and 24/7 autonomous cloud-computer operation.

---

## 1. Jarvis 2.0 vs. OpenClaw: Detailed Comparison

| Dimension | **Jarvis 2.0 (OpenJarvis)** | **OpenClaw** |
| :--- | :--- | :--- |
| **Origin & Focus** | Research and systems platform (Stanford SAIL / Hazy Research). Built around **Intelligence Per Watt**, hardware energy telemetry, and persistent autonomous operators. | Community personal assistant gateway. Built around **omnichannel messaging connectivity** and personal automation. |
| **Tech Stack** | **Python 3.12 + Rust (PyO3) + React / Tauri**. Optimized for AI primitives, system calls, and hardware efficiency. | **Node.js / TypeScript**. Event-driven single-threaded JavaScript runtime. |
| **Channels** | Built-in native connectors for Telegram, WhatsApp, Discord, Slack, iMessage, BlueBubbles, Signal, Matrix, and WebChat. | Wide chat integrations (WhatsApp, Telegram, Discord, Slack, iMessage, Signal, Matrix). |
| **Skills & Extensibility** | Native tool registry, background operators, plus built-in **`OpenClawResolver`** (`src/openjarvis/skills/sources/openclaw.py`). | **ClawHub** (~13,700 community skills using the `SKILL.md` format). |
| **Unique Strengths** | 1. Joules/token & FLOPs telemetry (NVML, RAPL).<br>2. Persistent stateful operators with memory compaction.<br>3. Local-Cloud collaboration (Minions protocol).<br>4. Built-in Playwright browser automation suite. | 1. Large community skill repository.<br>2. Established chat protocol integrations.<br>3. Lightweight Node.js event loop. |

### Key Decision: Do We Need to Run OpenClaw Separately?
**No.** 
- Jarvis 2.0 already includes [`OpenClawResolver`](file:///d:/Jarvis%202.0/src/openjarvis/skills/sources/openclaw.py). Running `jarvis skill sync openclaw` pulls ClawHub skills directly into Jarvis.
- Jarvis 2.0 already has native Python connectors for Telegram, WhatsApp, Discord, and Slack in [`src/openjarvis/channels/`](file:///d:/Jarvis%202.0/src/openjarvis/channels/).
- **Benefit**: We avoid running two heavy daemons (Node.js + Python), saving memory and CPU, keeping Jarvis ultra-lightweight.

---

## 2. Core Product Vision

1. **Distinctive Visual & Auditory Persona**:
   - An audio-reactive, animated Jarvis holographic HUD / orb rendered via HTML5/WebGL.
   - Cinematic custom voice clone (classic British butler Jarvis) via user-provided **ElevenLabs API** key.
   - Low-latency real-time bidirectional conversation via **Gemini Multimodal Live API**.
   - Built-in free fallbacks (Kokoro neural TTS, Microsoft Edge TTS) requiring zero API keys.

2. **Omnichannel Remote Control**:
   - Interact via a voice-first **Mobile PWA / Companion App**.
   - Remote control via **WhatsApp** and **Telegram**: send text or audio notes; receive text or synthetic voice note responses.

3. **Dual Execution Environment**:
   - **Virtual Cloud Computer**: Jarvis operates its own headless browser and virtual display in the cloud (zero installation needed on the user's home computer).
   - **Optional Local PC Node**: A lightweight worker daemon (`jarvis-node`, ~30MB) running in the Windows system tray to execute tasks directly on the user's physical desktop when needed.

---

## 3. Production Technical Specifications

### A. Authentication Architecture (Hub-to-Node Identity System)
- **Node Registration**: `jarvis-node` generates an **Ed25519 keypair** locally. `device_id` is the SHA-256 fingerprint of the public key. Displays a 6-digit one-time code approved via WhatsApp/Telegram.
- **Token Issuance**: Cloud Hub issues an Ed25519-signed Device JWT containing `user_id`, `device_id`, and capability scopes.
- **Token Rotation**: 1-hour access tokens paired with 30-day sliding refresh tokens rotated on use; revoked tokens tracked in Hub blacklist.
- **Multi-Device Routing**: Registry table in SQLite (`user_devices`) maps multiple computers per user. Users can target specific machines (`@home-pc open youtube`) or default to the active node.

### B. Secrets & API Keys Storage (Vault & Encryption)
- **At-Rest Encryption**: Fernet authenticated symmetric encryption (AES-128-CBC + HMAC-SHA256). Master decryption key saved with restricted OS permissions (`0o600`).
- **Pointer Referencing**: Configuration files never store plaintext API keys; they use pointer URIs (`vault://ELEVENLABS_API_KEY`).
- **Memory & Log Scrubbing**: Decrypted values are tagged `TaintLabel.SECRET`. All logs pass through `credential_stripper.py` to prevent leakages.

### C. Granular Agent Permission Model (RBAC)
- **Tier 0 (Safe / Autonomous)**: `file:read` (workspace-scoped), `memory:read`, `network:fetch` (GET only), `web:search`.
- **Tier 1 (Controlled Writes)**: `file:write`, `schedule:create`, `browser:navigate`.
- **Tier 2 (High-Impact)**: `code:execute` (Python/PowerShell), `package:install`, `browser:session` (cookies/logins). Requires user approval push notification.
- **Tier 3 (Critical / Destruction)**: `file:delete`, `system:admin` (registry, sudo, disk writes), credential export. Hard stop requiring 2-factor OTP via WhatsApp/Telegram.

### D. 3-Layer Prompt Injection Defense
- **Layer 1 (Static Regex Scanner)**: `injection_scanner.py` inspects all external text for override patterns (`prompt_override`, `identity_override`, `code_injection`). Flagged payloads are quarantined.
- **Layer 2 (Taint Tracking)**: Web scraped text is marked with `TaintLabel.EXTERNAL` via `taint.py`.
- **Layer 3 (Sink Policy Blockade)**: `SINK_POLICY` strictly forbids data bearing `TaintLabel.EXTERNAL` from being passed into execution sinks (`file_write`, `code_interpreter`, terminal exec).

### E. Observability & Cryptographic Audit Trail
- **Security Audit**: Persisted to `audit.db` using an **append-only Merkle hash chain**; any deletion or alteration invalidates the chain.
- **Execution Telemetry**: `traces.db` records `trace_id`, `step_index`, `tool_name`, `latency_ms`, tokens, Joules consumed, and error codes.

### F. Job Queue, Recovery & Retry System
- **State Machine**: Tasks progress through `QUEUED` $\rightarrow$ `RUNNING` $\rightarrow$ `PAUSED` $\rightarrow$ `COMPLETED` / `FAILED` / `RECOVERING`.
- **Persistent Checkpoints**: Session states and tool results are snapshotted to SQLite per tick.
- **Crash Recovery**: If the cloud instance restarts, `OperatorManager` loads the last checkpoint and resumes without duplicating completed tool actions.
- **Exponential Backoff**: Jittered backoff ($T = 2^n + \text{jitter}$) up to 3 retries for transient network issues.

### G. Database Architecture
- **State Store**: SQLite (`state.db`) for task queues, node registries, and operator checkpoints.
- **Memory Store**: SQLite with **FTS5 full-text indexing** (`memory.db`) for long-term fact storage and BM25 recall.
- **Vector Store**: Embedded `sqlite-vec` or ChromaDB for multi-hop semantic document search.

### H. Empirical Number Validation
- All footprint numbers (RAM usage, skill parse counts, latency) are treated as hypotheses to be verified via `psutil` profiling and automated test scripts during implementation.

---

## 4. Why Host on Cloud if PC is Off?

1. **24/7 Persistent Autonomy**: Runs continuous monitoring, scrapes web sources, and performs multi-hour research while personal hardware is off.
2. **Virtual Cloud Browser**: Operates its own headless Chromium display directly on the cloud VM (zero home PC install required).
3. **Datacenter Reliability**: Permanent 1 Gbps connection, zero home electricity use, and zero battery drain.

---

## 5. Implementation Roadmap (All Steps Completed & Verified)

1. **Step 1 — ElevenLabs Voice & Speech Engine** `[COMPLETED & VERIFIED]`:
   - Core: [`src/openjarvis/speech/elevenlabs_tts.py`](file:///d:/Jarvis%202.0/src/openjarvis/speech/elevenlabs_tts.py)
   - Integration: Registered in speech registry and TTS discovery.
   - Tests: [`tests/speech/test_elevenlabs.py`](file:///d:/Jarvis%202.0/tests/speech/test_elevenlabs.py) (7/7 passed).

2. **Step 2 — WhatsApp & Telegram Voice Note Loop** `[COMPLETED & VERIFIED]`:
   - Audio Bridge: [`src/openjarvis/speech/voice_channel_bridge.py`](file:///d:/Jarvis%202.0/src/openjarvis/speech/voice_channel_bridge.py)
   - Channels: [`src/openjarvis/channels/telegram.py`](file:///d:/Jarvis%202.0/src/openjarvis/channels/telegram.py) and [`src/openjarvis/channels/whatsapp.py`](file:///d:/Jarvis%202.0/src/openjarvis/channels/whatsapp.py)
   - Tests: [`tests/channels/test_voice_channels.py`](file:///d:/Jarvis%202.0/tests/channels/test_voice_channels.py) (17/17 passed).

3. **Step 3 — Cloud Virtual Computer / Headless Browser** `[COMPLETED & VERIFIED]`:
   - Core: [`src/openjarvis/tools/browser.py`](file:///d:/Jarvis%202.0/src/openjarvis/tools/browser.py)
   - Cloud Hardening: Added `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu` for 1GB RAM cloud instances.
   - Tests: [`tests/tools/test_browser.py`](file:///d:/Jarvis%202.0/tests/tools/test_browser.py) (76/76 passed).

4. **Step 4 — 3D Hologram Web UI & Mobile PWA** `[COMPLETED & VERIFIED]`:
   - Web App & Shader: [`src/openjarvis/server/static/index.html`](file:///d:/Jarvis%202.0/src/openjarvis/server/static/index.html)
   - Service Worker & Manifest: [`sw.js`](file:///d:/Jarvis%202.0/src/openjarvis/server/static/sw.js), [`manifest.webmanifest`](file:///d:/Jarvis%202.0/src/openjarvis/server/static/manifest.webmanifest)
   - Router: [`src/openjarvis/server/hologram_routes.py`](file:///d:/Jarvis%202.0/src/openjarvis/server/hologram_routes.py)
   - Tests: [`tests/server/test_hologram.py`](file:///d:/Jarvis%202.0/tests/server/test_hologram.py) (3/3 passed).

5. **Step 5 — Local Node Worker & Tunneling Architecture** `[COMPLETED & VERIFIED]`:
   - Hub Manager: [`src/openjarvis/server/node_manager.py`](file:///d:/Jarvis%202.0/src/openjarvis/server/node_manager.py)
   - WebSocket Tunnel: [`src/openjarvis/server/node_routes.py`](file:///d:/Jarvis%202.0/src/openjarvis/server/node_routes.py)
   - Desktop Daemon: [`src/openjarvis/daemon/node_worker.py`](file:///d:/Jarvis%202.0/src/openjarvis/daemon/node_worker.py)
   - Tests: [`tests/server/test_node_tunnel.py`](file:///d:/Jarvis%202.0/tests/server/test_node_tunnel.py) (8/8 passed).

6. **Step 6 — 1-Click Oracle Cloud Deployment** `[COMPLETED & VERIFIED]`:
   - Automated Installer: [`deploy/oracle/install.sh`](file:///d:/Jarvis%202.0/deploy/oracle/install.sh)
   - Deployment Guide: [`deploy/oracle/README.md`](file:///d:/Jarvis%202.0/deploy/oracle/README.md)
   - Verified 100% compatible with Oracle Always-Free tier (1GB AMD & 24GB ARM).
