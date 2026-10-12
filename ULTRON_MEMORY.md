# ULTRON — PROJECT MEMORY & ARCHITECTURE REGISTER
**Document Status:** Living Master Project Memory  
**Location:** `d:\Ultron\ULTRON_MEMORY.md`  
**Last Updated:** October 12, 2026  
**Governing Phase:** Phase 2 of 6 (COMPLETED — Checkpoint Verified on Dedicated Branch)

---

## 1. PROJECT IDENTITY

### 1.1 Purpose & Long-Term Vision
**Ultron** is an autonomous, professional desktop AI assistant designed to provide powerful personal intelligence, system automation, and multi-agent workflow orchestration.
- **Primary Objective:** Deliver a secure, reliable, high-performance desktop assistant distributed to end users completely free of charge.
- **Target Audience:** Everyday users, power operators, and software engineers seeking local autonomy, robust data privacy, and executive-level task execution.
- **Distribution Model:** Free distribution via self-contained native desktop installers (Windows MSI/EXE, macOS DMG, Linux AppImage/DEB) and lightweight local web/PWA interface.
- **Core Philosophy:** Local-first, zero mandatory subscription barriers, privacy-preserving data isolation, and resilient fallback execution.

---

## 2. VERIFIED TECHNICAL ARCHITECTURE

### 2.1 Technology Stack Matrix
| Layer | Technologies & Runtimes | Implementation Location | Verified Status |
| :--- | :--- | :--- | :--- |
| **Backend Service** | Python 3.10–3.13 (Python 3.12.15 active), FastAPI 0.110+, Uvicorn 0.30+, Click 8+, Rich 13+, Pydantic v2 | `src/openjarvis/server/`, `src/openjarvis/cli/` | Verified & Operational |
| **Native Extension** | Rust 2021 edition, PyO3, Maturin | `rust/crates/openjarvis-python/` | Verified (PyO3 bindings for FTS5, loop guard, token math) |
| **Desktop Host** | Tauri v2 (`@tauri-apps/api` 2.12.0), Rust (`frontend/src-tauri/`) | `frontend/src-tauri/` | Tauri v2 configured; multi-platform CI active |
| **Desktop Frontend** | React 19.3.0, TypeScript 5.8+, Vite 8.3.1, TailwindCSS 4.3.3, Base UI, Zustand, Sonner | `frontend/src/` | Active code present; `node_modules` currently uninstalled locally |
| **Hologram Interface** | Single-file WebGL/PWA interface, Three.js, Web Audio API, Web Speech API | `src/openjarvis/server/static/index.html` | Verified & Operational at `/hologram` and `/` |
| **Local Storage** | SQLite 3 (WAL mode, FTS5 full-text search) | `users.db`, `memory.db`, `traces.db`, `sessions.db` | Verified; zero external binary requirements |
| **Cloud Storage** | Pluggable Supabase (PostgreSQL + pgvector) and MongoDB adapters | `src/openjarvis/storage/memory_backend.py` | Verified config loader and credential isolation |
| **Security Core** | PBKDF2-HMAC-SHA256 (600,000 iter), RBAC capabilities, InjectionScanner, Subprocess sandbox | `src/openjarvis/auth/`, `src/openjarvis/security/` | Verified (OWASP standards; 43/43 tests PASS) |

### 2.2 Major Process Boundaries & IPC
1. **Desktop Shell (Tauri v2):**
   - Implemented in `frontend/src-tauri/src/lib.rs` (4,417 lines).
   - Manages the native system tray, global hotkeys, window chrome, and sidecar process lifecycles for Ollama (`port 11434`) and OpenJarvis (`port 8000`).
   - Note on Project Layout: `desktop/src-tauri/` is an incomplete legacy stub containing only `overlay.html` and a Darwin binary; the active, production Tauri v2 configuration resides in `frontend/src-tauri/`.
2. **Server & Engine Runtime (FastAPI):**
   - Bootstrapped via `openjarvis.cli.serve:main` (`jarvis serve`) and `openjarvis.server.app:create_app`.
   - Exposes OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/models`), session APIs (`/v1/sessions`), auth routes (`/api/auth/*`), and Hologram directives (`/api/hologram/directive`, `/api/tts`).
3. **Client Communications:**
   - Desktop frontend connects via HTTP/WebSocket to `http://localhost:8000`.
   - Hologram Web UI communicates directly over HTTP REST and WebSocket (`/api/hologram/ws`, `/ws`).
   - CORS is strictly locked down to loopback origins (`localhost`, `127.0.0.1`) and Tauri protocols (`tauri://localhost`, `http://tauri.localhost`). Wildcard origins with credentials are explicitly refused (`app.py:287`).

---

## 3. EXISTING CAPABILITIES

### 3.1 Fully Implemented & Verified
- **3D Hologram HUD (`index.html`):** Real-time WebGL audio visualizer, live status pill, responsive directive submission, and normalized action telemetry (`EXECUTED` / `FAILED` badges).
- **Frontier LLM Brain (`UltronBrain`):** Integrated with Google Gemini models (`gemini-3.8-flash`, `gemini-3.5-flash`, etc.) via `google-genai` SDK, with multi-turn history formatting and prompt injection defense.
- **Smart Local Reasoning Fallback:** Resilient offline fallback capable of answering weather/temperature queries, identity queries, math calculations, and system status queries without crashing when cloud API keys are absent.
- **Voice Barge-In:** Client-side microphone analysis via Web Audio `AnalyserNode` in `index.html`; automatically silences TTS playback the instant the user speaks.
- **Native Windows TTS (`tts_engine.py`):** Windows SAPI speech synthesis via `cscript` and PowerShell `System.Speech` with in-memory WAV caching.
- **Multi-Tenant Security & Auth:** 600,000-iteration PBKDF2 password hashing, timing-safe verification, transparent re-hash on login, 15-minute account lockout after 5 consecutive failed attempts (HTTP 423), and bootstrap admin privilege guard.
- **Tenant Data Boundaries:** 100% isolation across sessions (`/v1/sessions` anti-enumeration 404), user preferences, workflow directories, and scheduled cron tasks.
- **Autonomous Tool Runtime (`JarvisSystem`):** 45+ registered tools including shell execution, browser automation (Playwright), file I/O, n8n automations, subagent task delegation, and ClawHub skills management.
- **Disaster Recovery:** Verified online hot backup snapshot (`sqlite3.backup`) and point-in-time database restoration (`deploy/staging_rehearsal.py` 8/8 PASS).

### 3.2 Partially Implemented / External Dependency Gated
- **Third-Party Messaging Channels:** Telegram (`telegram.py`) and WhatsApp (`whatsapp.py`) bridges are implemented but operate on mocks during testing; live message delivery requires user-provided bot tokens (`TELEGRAM_BOT_TOKEN`, `WHATSAPP_TOKEN`).
- **Cloud Database Synchronization:** Supabase and MongoDB backend modules exist and mask credentials, but live sync requires valid external connection strings.
- **Tauri Desktop Verification:** The React desktop application code is present, but local dependencies (`frontend/node_modules/`) are uninstalled, leaving local test and compilation checks unexecuted.

### 3.3 Missing Capabilities
- **Reverse Engineer Anything (REA):** Authorized binary/software analysis tooling is not currently present in the codebase.
- **Cross-Platform Local TTS:** `tts_engine.py` is Windows-specific; Linux and macOS currently rely on optional cloud TTS or fallback.

---

## 4. KNOWN RISKS & OUTSTANDING ISSUES

| Issue ID | Severity | File / Component | Verified Finding & Risk | Action Required |
| :--- | :--- | :--- | :--- | :--- |
| **RISK-01** | **RESOLVED** | Git Working Tree | 71 modified files and 15 untracked files safely captured in Checkpoint commit `02d81b1`, documented in `64851e2`, and tagged at `ultron-phase2-checkpoint-2026-10-12` on `recovery/checkpoint-phase2-baseline`. External backup created in `%USERPROFILE%\Ultron-recovery-backups\phase2-baseline-20261012`. Remote branch and tag verified on GitHub `origin`. | RESOLVED & VERIFIED in Phase 2D. |
| **RISK-02** | **HIGH** | `src/openjarvis/server/llm_client.py:30` | Hardcoded historical path `Path("d:/Jarvis 2.0/.env")`. Works locally due to NTFS junction `D:\Jarvis 2.0` -> `D:\Ultron`, but will fail on any other computer. | Replace with portable relative path resolution (`Path(".env")` / config dir). |
| **RISK-03** | **MEDIUM** | `src/openjarvis/traces/store.py:348` | Redefinition of `close(self)` (line 297 and line 348) causes Ruff lint failure `F811`. | Remove the redundant definition at line 297 in Phase 3. |
| **RISK-04** | **MEDIUM** | `.venv/Lib/site-packages/*.pth` | `.venv` has an editable link `_editable_impl_openjarvis.pth` pointing to `D:\Jarvis 2.0\src` via NTFS junction. | Re-link `.venv` directly to `d:\Ultron\src` during foundation cleanup. |
| **RISK-05** | **MEDIUM** | `frontend/` | `frontend/node_modules/` is absent, preventing local frontend build and test checks. | Run `npm ci` during Phase 3 after user authorization. |
| **RISK-06** | **LOW** | `deploy/nginx/openjarvis.conf` | Public internet exposure (`0.0.0.0`) lacks TLS termination and edge rate-limiting without reverse proxy. | Enforce loopback binding until production TLS reverse proxy is deployed. |

*Note on Secrets:* Local `.env` contains `GEMINI_API_KEY` and `GOOGLE_API_KEY`. These keys are strictly excluded from source control by `.gitignore` (line 40) and must NEVER be printed, committed, or exposed.

---

## 5. PERMANENT ENGINEERING RULES

All future development sessions must strictly comply with these rules:
1. **Preserve Existing User Work:** Never discard, overwrite, stash-drop, or reset uncommitted changes.
2. **Review Memory & Progress First:** Always read `ULTRON_MEMORY.md` and `ULTRON_PROGRESS.md` before taking action.
3. **Verify Before Coding:** Inspect existing implementations first to prevent duplicating working code.
4. **Evidence Over Assumptions:** Every conclusion must have concrete evidence (file paths, symbols, command outputs).
5. **Clear Acceptance Criteria:** Every task must have defined criteria and regression tests prior to implementation.
6. **No Phantom Passes:** Never claim that an unexecuted test passed. Run the test and record actual output.
7. **Explicit Approval for Destructive Steps:** Obtain user consent before any deletion, schema drop, reset, or high-risk command.
8. **Never Expose Secrets:** Report variable names and locations only. Never display or commit secret tokens or keys.
9. **Single-Phase Discipline:** Work on exactly one authorized phase at a time. Stop and await review after each phase.
10. **Synchronize Documentation:** Update `ULTRON_MEMORY.md` and `ULTRON_PROGRESS.md` upon completing any approved task.

---

## 6. MAJOR DECISIONS REGISTER

| Date | Decision | Rationale | Impact |
| :--- | :--- | :--- | :--- |
| **2026-10-10** | Evolve Project from Jarvis 2.0 to Ultron | Unify 3D Hologram, Voice Barge-In, Hermes intelligence, and multi-tenancy under the Ultron brand. | Commit `7379e51` (unpushed). Working tree evolution ongoing. |
| **2026-10-11** | Upgrade Password Hashing to 600,000 PBKDF2 Iterations | Meet modern OWASP Password Storage Cheat Sheet standards for brute-force resistance. | Zero-downtime rehash on login for legacy 100k hashes; verified in `test_auth_manager.py`. |
| **2026-10-11** | Implement 15-Minute Account Lockout | Prevent credential stuffing and offline brute-force attacks on multi-user endpoints. | 5 failed consecutive attempts trigger HTTP 423 Locked. |
| **2026-10-11** | Retain Zero-Friction Loopback Default | Ensure local single-user desktop users can run without mandatory API keys or complex setups. | System starts out-of-the-box on loopback with smart local fallback. |
| **2026-10-11** | Adopt Six-Phase Controlled Development Roadmap | Ensure disciplined, verifiable progress without uncontrolled code generation or destructive changes. | Phased progression with review gates between phases. |
| **2026-10-12** | Establish Recovery Checkpoint on Dedicated Branch | Safely preserve all 71 tracked modifications and 15 untracked project files without touching remote `main`. | Checkpoint commit `02d81b17dab80ad35758ec013bcc6c8b599a4bb7` pushed to `origin/recovery/checkpoint-phase2-baseline` and verified. |
| **2026-10-12** | Finalize Checkpoint Tag ultron-phase2-checkpoint-2026-10-12 | Establish an immutable annotated release tag on verified checkpoint commit `64851e282d96b648f9bbb6864dc029ab88257da0`. | Tag pushed to `origin` and verified via `ls-remote`. Remote `main` 100% untouched. |

---

## 7. CURRENT SESSION STATE

- **Current Active Phase:** **Phase 2: GitHub Safety, Recovery and Baseline Checkpoint** (COMPLETED & VERIFIED).
- **Completed in this Session:**
  - Resolved commit-SHA discrepancy: verified `b4f05e244093c8340d877eeb0c969562725ad5aa` was an earlier text transcription artifact; actual local tracking and parent SHA is `b4f05e2562798d3b09ad3a624ef84e2bc1a5d9d3`, matching live remote `origin/main` 100%.
  - Confirmed local HEAD `7379e512cf31cf0d2de620e1e8bfade198b220c7` is a direct single-commit descendant of remote `main`.
  - Created complete external working-state backup outside the repository at `C:\Users\DELL\Ultron-recovery-backups\phase2-baseline-20261012\` containing `tracked_modifications.patch` (238,303 bytes), `untracked_files/` (all 17 files), `HEAD_SHA.txt`, `git_status_original.txt`, and `file_inventory.txt` with SHA256 checksums.
  - Created dedicated branch `recovery/checkpoint-phase2-baseline` from HEAD `7379e51`.
  - Staged and committed all 71 modified tracked files and 15 untracked project files in Checkpoint Commit 1: `02d81b17dab80ad35758ec013bcc6c8b599a4bb7` (`chore(checkpoint): preserve reviewed Ultron working state before production hardening`).
  - Successfully pushed `recovery/checkpoint-phase2-baseline` to GitHub remote `origin` (`https://github.com/Airlucofficial/Jarvis-2.0.git`).
  - Read-only verified via authenticated `ls-remote` that remote `recovery/checkpoint-phase2-baseline` points to `02d81b17dab80ad35758ec013bcc6c8b599a4bb7` and live remote `main` remains untouched at `b4f05e2562798d3b09ad3a624ef84e2bc1a5d9d3`.
  - Governance documents updated and committed in a separate documentation-only commit on the recovery branch.
  - Finalized and pushed annotated tag `ultron-phase2-checkpoint-2026-10-12` targeting commit `64851e282d96b648f9bbb6864dc029ab88257da0`, verified via `ls-remote`.
- **Next Phase:** **Phase 3: Engineering Foundation, Testing and Tooling** (Gated on operator review).
