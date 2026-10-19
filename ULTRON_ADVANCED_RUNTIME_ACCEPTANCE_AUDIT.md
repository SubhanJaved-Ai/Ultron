# ULTRON — ADVANCED RUNTIME ACCEPTANCE AUDIT & GAP-FIX REPORT

**Audit Date:** October 19, 2026  
**Auditor:** Antigravity Autonomous Coding Agent  
**Repository:** `d:\Ultron`  
**Git Branch:** `main`  
**Base Commit:** `a9befb426067d5c621e948a8eddbc5ee5b4278f1`  
**Target Delivery:** High-assurance runtime acceptance audit and targeted gap fixes  
**Overall Acceptance Status:** `PASS WITH LIMITATIONS`  

> **Limitation Note:** Runtime verification was executed using the local Ollama daemon and high-fidelity HTTP integration stream mocks (`respx` and streaming async generators) matching exact OpenAI, Anthropic, and ElevenLabs API wire contracts. Full external cloud API calls requiring billed credit consumption on third-party accounts were verified against verified provider schemas and mock stream parsers rather than live credit expenditure.

---

## 1. Executive Summary

An evidence-driven acceptance audit was performed on Ultron's core subsystems:
1. **Centralized Rate Limiting & Execution Policy:** Token-bucket rate limiting (RPM/TPM), concurrency gating, circuit breaker state transitions, task budgets, and non-retry policies.
2. **Provider Response & Usage Accounting:** Streaming token extraction (prompt, completion, cached, reasoning), speech character accounting, request ID tracking, and ledger recording.
3. **Pricing Catalog Rigor:** Official pricing catalog metadata, source URLs, effective dates, and elimination of silent fallbacks for unknown models.
4. **Data Isolation & Sanitization:** Detection, backup, and extraction of 5 synthetic demo records (`demo-req-*`) to dedicated test fixtures, establishing a clean production database baseline.
5. **Hardware Discovery & Benchmark Authenticity:** Elimination of invented hardware defaults, addition of Ollama version checks, and explicit framework simulation labeling (`is_simulated: True`, `evaluation_mode: "framework_simulation"`) when models are not running live.
6. **Cost Comparison Dashboard Correctness:** Replacement of misleading 2-card savings displays with an honest 4-card metric grid distinguishing Estimated Spend, Provider-Billed Invoices, Local Inference ($0.00 API, excluding host electricity), and Unmetered Calls.

All 39 backend tests and 173 frontend tests pass with exit code 0. DevTools MCP live verification confirmed correct UI rendering and ledger reconciliation.

---

## 2. Full Acceptance Requirement & Evidence Matrix

| Priority / Domain | Requirement | Audit Finding | Status | Evidence / Test |
|---|---|---|---|---|
| **P1: Rate Limiting & Concurrency** | Centralized limiter slot acquisition (RPM/TPM/concurrency) on streaming and sync routes | Previously limiter existed as standalone class without decorators or hooks in router | **FIXED** | `src/openjarvis/engine/resource_limiter.py` (`acquire_slot`, `acquire_slot_sync`); `tests/integration/test_runtime_acceptance_audit.py::test_concurrency_limit_enforced` |
| **P1: Circuit Breaker** | Circuit breaker opens on consecutive failures, trips to HALF-OPEN after cooldown, and blocks calls | Verified state machine and recovery transitions | **PASS** | `tests/engine/test_resource_limiter.py::test_circuit_breaker_transitions`; `tests/integration/test_runtime_acceptance_audit.py::test_circuit_breaker_opens_and_blocks` |
| **P1: Retries & Timeouts** | Transient error retries with exponential backoff; no retries on 401/403 or non-idempotent operations | Validated `execute_with_policy_async` respects error types and idempotency | **PASS** | `tests/engine/test_resource_limiter.py::test_execute_with_policy_no_retry_on_auth_error`; `test_execute_with_policy_no_retry_on_non_idempotent` |
| **P1: Spend & Token Budgets** | Task budgets enforced before work proceeds; unknown model spend bypass prevented | Budget checks implemented; unknown models estimate minimum threshold ($0.001) to prevent zero-cost bypass | **FIXED** | `src/openjarvis/engine/resource_limiter.py::check_task_budget`; `tests/integration/test_runtime_acceptance_audit.py::test_task_spend_budget_enforcement` |
| **P2: Streaming Usage Extraction** | OpenAI stream captures prompt, completion, cached, and reasoning tokens with request IDs | Added `"stream_options": {"include_usage": True}` and terminal chunk parsing in `_stream_openai` | **FIXED** | `src/openjarvis/server/cloud_router.py::_stream_openai`; `tests/integration/test_runtime_acceptance_audit.py::test_openai_stream_extracts_usage_and_records_to_ledger` |
| **P2: Anthropic Usage Extraction** | Anthropic SSE captures `message_start` and `message_delta` input/output tokens and request IDs | Implemented usage aggregator in `_stream_anthropic` | **FIXED** | `src/openjarvis/server/cloud_router.py::_stream_anthropic`; `tests/integration/test_runtime_acceptance_audit.py::test_anthropic_stream_extracts_usage_and_records_to_ledger` |
| **P2: Local Model Token Capture** | Ollama SSE captures `prompt_eval_count` and `eval_count` and records as `local_zero` | Captured from final `done: True` JSON frame in `stream_local` | **FIXED** | `src/openjarvis/server/cloud_router.py::stream_local`; `tests/integration/test_runtime_acceptance_audit.py::test_ollama_stream_extracts_tokens_and_records_local_zero` |
| **P2: Speech Accounting** | OpenAI TTS and ElevenLabs TTS capture characters, models, request IDs, and costs | Wrapped synthesis functions with limiter and ledger recording | **FIXED** | `src/openjarvis/speech/openai_tts.py`; `src/openjarvis/speech/elevenlabs_tts.py`; `tests/integration/test_runtime_acceptance_audit.py::test_openai_tts_speech_accounting` |
| **P3: Pricing Catalog Rigor** | Official source URLs, effective dates, and no silent generic fallbacks for unknown models | Removed generic `gpt-4o` fallback; unknown models return `None` (`cost_type="unknown"`); added speech pricing | **FIXED** | `src/openjarvis/intelligence/pricing.py`; `tests/traces/test_usage_ledger.py::test_calculate_cost_unknown_model_labeled_unknown` |
| **P4: Demo Record Isolation** | Backup database, isolate 5 synthetic demo records to test fixtures, clean production DB | Database backed up, 5 records extracted to JSON fixture, production DB verified 0 records | **PASS** | `tests/fixtures/demo_usage_records.json`; `usage_ledger.db.backup_1792387436` |
| **P5: Hardware Detection** | Detect physical cores, Ollama version, and eliminate invented hardware defaults | Added `physical_cores`, `ollama_version`; removed 8GB RAM / 50GB disk fallback defaults (now `0.0` if unreadable) | **FIXED** | `src/openjarvis/intelligence/hardware_wizard.py`; `tests/integration/test_runtime_acceptance_audit.py::test_hardware_scan_no_invented_data` |
| **P5: Benchmark Authenticity** | No 100% fake benchmark scores; label framework simulations when Ollama model not live | Live model check implemented; outputs labeled `is_simulated: True` with explicit simulation notice; live runs scored on 8 criteria | **FIXED** | `src/openjarvis/intelligence/hardware_wizard.py`; `tests/integration/test_runtime_acceptance_audit.py::test_benchmark_simulation_labeling` |
| **P6: Dashboard Correctness** | Distinguish Estimated Spend, Provider-Billed Cost, Local Inference ($0.00 API), and Unmetered Requests | 4-card metric grid implemented in React; modal handles unknown costs; legacy HTML routing conflict resolved | **FIXED** | `frontend/src/components/Dashboard/CostComparison.tsx`; `src/openjarvis/server/dashboard.py`; DevTools snapshot verified |

---

## 3. Confirmed Defects & Targeted Remediations

### Defect 1: Silent Price Fallback to GPT-4o for Unknown Models
- **Severity:** High (Cost Misattribution)
- **Root Cause:** In `src/openjarvis/intelligence/pricing.py`, `resolve_price_entry(model)` returned a generic default priced at $2.50 / $10.00 per 1M tokens when a model was not in the catalog.
- **Fix:** Removed the fallback. Uncataloged models return `None`, causing `calculate_cost()` to designate `cost_type="unknown"` and `estimated_cost_usd=0.0`.
- **Validation:** `tests/traces/test_usage_ledger.py::test_calculate_cost_unknown_model_labeled_unknown`.

### Defect 2: Missing Limiter & Ledger Runtime Hooks on LLM Streaming & Speech
- **Severity:** High (Unmetered Execution & Unaccounted Spend)
- **Root Cause:** While `ResourceLimiter` and `UsageLedger` existed as classes, neither `cloud_router.py` nor speech modules (`openai_tts.py`, `elevenlabs_tts.py`) acquired slots or called `record_usage()`. Furthermore, OpenAI streaming did not set `"stream_options": {"include_usage": True}`, so token counts were omitted in SSE streams.
- **Fix:** 
  - Added async and sync context managers (`acquire_slot`, `acquire_slot_sync`) to `ResourceLimiter`.
  - Updated `_stream_openai` to request usage chunks and record tokens, cached tokens, and reasoning tokens.
  - Updated `_stream_anthropic` to aggregate `message_start` and `message_delta` tokens.
  - Updated `stream_local` to extract `prompt_eval_count` and `eval_count` from Ollama's final frame and record as `local_zero`.
  - Wrapped `_openai_tts_request` and `_elevenlabs_synthesize` to track characters and record speech costs.
- **Validation:** `tests/integration/test_runtime_acceptance_audit.py` (Tests 1, 5, 6, 7, 8, 9).

### Defect 3: Synthetic Demo Records Polluting Production Usage Database
- **Severity:** Medium (Data Integrity)
- **Root Cause:** Five demo records (`demo-req-001` through `demo-req-005`) were seeded directly into `~/.openjarvis/usage_ledger.db`.
- **Fix:** Created timestamped backup (`usage_ledger.db.backup_1792387436`), extracted records to `tests/fixtures/demo_usage_records.json`, and purged them from the live database.
- **Validation:** Verified `SELECT COUNT(*) FROM cloud_usage_ledger` equals `0`.

### Defect 4: Invented Hardware Defaults & Unverified Benchmark Scores
- **Severity:** Medium (False System Claims)
- **Root Cause:** `HardwareScanResult` defaulted `total_ram_gb` to `8.0` and `disk_free_gb` to `50.0`. `LocalBenchmarkResult` returned placeholder scores without indicating whether the model actually ran on Ollama.
- **Fix:**
  - Removed invented defaults in `hardware_wizard.py`; missing values now default to `0.0` (indicating unverified/unavailable).
  - Added `physical_cores` and `ollama_version` detection.
  - Added `is_simulated: bool`, `evaluation_mode: str`, and `simulation_notice: str` to `LocalBenchmarkResult`. When a model is not installed/running in Ollama, results are explicitly marked as `framework_simulation`.
  - When running live in Ollama, outputs are evaluated against 8 explicit criteria (instruction adherence, technical accuracy, conciseness, structured output, reasoning transparency, safety boundaries, hallucination avoidance, latency compliance).
- **Validation:** `tests/integration/test_runtime_acceptance_audit.py::test_hardware_scan_no_invented_data`, `test_benchmark_simulation_labeling`, `test_benchmark_live_scoring_criteria`.

### Defect 5: Legacy Standalone Dashboard Shadowing Modern React SPA Dashboard
- **Severity:** Medium (UI/UX Breakdown)
- **Root Cause:** `src/openjarvis/server/dashboard.py` mounted an explicit `@dashboard_router.get("/dashboard")` returning legacy HTML, and `frontend/vite.config.ts` listed `/^\/dashboard/` in `navigateFallbackDenylist`. This prevented the React SPA's `DashboardPage` (and `CostComparison.tsx`) from rendering when navigating to `/dashboard`.
- **Fix:**
  - Updated `dashboard.py` to serve `static/index.html` if available, and added `/legacy-dashboard` for standalone HTML access.
  - Removed `/^\/dashboard/` from `navigateFallbackDenylist` in `frontend/vite.config.ts` and added `/^\/legacy-dashboard/`.
  - Rebuilt static assets (`npm run build`).
- **Validation:** DevTools MCP navigation to `http://127.0.0.1:8000/dashboard` verified the modern React dashboard with 4-card metric grid and auditable request ledger modal.

---

## 4. Hardware Discovery & Benchmark Authenticity Analysis

### Host Hardware Live Discovery Results
- **Operating System:** Windows 11 Pro (Build 26200)
- **Logical CPU Cores:** 8
- **Physical CPU Cores:** 4
- **System RAM:** 15.77 GB total (4.06 GB available)
- **GPU Device:** Intel(R) UHD Graphics (Direct3D11 / Integrated)
- **Dedicated VRAM:** 0.125 GB (Shared System Memory: 7.89 GB)
- **Primary Disk:** 104.9 GB free of 475.7 GB total
- **Ollama Engine Status:** Ollama API reachable on `http://localhost:11434` (Version 0.5.12)

### Benchmark Authenticity Safeguards
1. **Simulation Transparency:** If a benchmark is executed without a running model in Ollama, `LocalBenchmarkResult` returns:
   - `is_simulated = True`
   - `evaluation_mode = "framework_simulation"`
   - `simulation_notice = "Benchmark output was generated using framework simulation heuristics because <model> is not loaded in the active local Ollama runtime."`
2. **Live Scoring Criteria:** When models are tested against live Ollama inference, scoring evaluates 8 transparent dimensions on a 0.0–1.0 scale:
   - `adherence`: Following prompt directives and constraints
   - `accuracy`: Factual and technical precision
   - `conciseness`: Brevity and lack of superfluous fluff
   - `structure`: Valid Markdown/JSON formatted output
   - `reasoning`: Clear step-by-step logic
   - `safety`: Adherence to refusal boundaries
   - `hallucination`: Absence of ungrounded assertions
   - `latency`: Generation latency within acceptable threshold

---

## 5. Pricing Catalog Verification

All prices are cataloged per 1,000,000 tokens (or 1,000 characters for speech). Effective as of October 2026.

| Provider | Model / Endpoint | Input / 1M | Output / 1M | Cached Input / 1M | Reasoning / 1M | Speech / 1k Chars | Source URL / Authority |
|---|---|---|---|---|---|---|---|
| **OpenAI** | `gpt-4o` | $2.50 | $10.00 | $1.25 | — | — | https://openai.com/api/pricing/ |
| **OpenAI** | `gpt-4o-mini` | $0.15 | $0.60 | $0.075 | — | — | https://openai.com/api/pricing/ |
| **OpenAI** | `o1-preview` | $15.00 | $60.00 | $7.50 | $60.00 | — | https://openai.com/api/pricing/ |
| **OpenAI** | `o1-mini` | $3.00 | $12.00 | $1.50 | $12.00 | — | https://openai.com/api/pricing/ |
| **OpenAI** | `tts-1` | — | — | — | — | $0.015 | https://openai.com/api/pricing/ |
| **OpenAI** | `tts-1-hd` | — | — | — | — | $0.030 | https://openai.com/api/pricing/ |
| **Anthropic** | `claude-3-5-sonnet-20241022` | $3.00 | $15.00 | $0.30 | — | — | https://www.anthropic.com/pricing |
| **Anthropic** | `claude-3-5-haiku-20241022` | $1.00 | $5.00 | $0.10 | — | — | https://www.anthropic.com/pricing |
| **Anthropic** | `claude-3-opus-20240229` | $15.00 | $75.00 | $1.50 | — | — | https://www.anthropic.com/pricing |
| **Google** | `gemini-1.5-pro` | $1.25 | $5.00 | $0.3125 | — | — | https://ai.google.dev/pricing |
| **Google** | `gemini-1.5-flash` | $0.075 | $0.30 | $0.01875 | — | — | https://ai.google.dev/pricing |
| **Google** | `gemini-2.0-flash` | $0.10 | $0.40 | $0.025 | — | — | https://ai.google.dev/pricing |
| **ElevenLabs** | `eleven_turbo_v2_5` | — | — | — | — | $0.030 | https://elevenlabs.io/pricing |
| **ElevenLabs** | `eleven_multilingual_v2` | — | — | — | — | $0.030 | https://elevenlabs.io/pricing |
| **Ollama** | Any Local Model | $0.00 | $0.00 | $0.00 | $0.00 | — | Local on-device inference (API fee $0.00; excludes host electricity) |

---

## 6. Verification Test Suite Execution Details

### Command 1: Runtime Acceptance Integration Test Suite
```bash
.\.venv\Scripts\python.exe -m pytest tests/integration/test_runtime_acceptance_audit.py -v
```
- **Exit Code:** `0`
- **Duration:** 27.86s
- **Results:** 12 passed, 0 failed
  1. `test_concurrency_limit_enforced`: PASSED
  2. `test_circuit_breaker_opens_and_blocks`: PASSED
  3. `test_task_spend_budget_enforcement`: PASSED
  4. `test_task_token_budget_enforcement`: PASSED
  5. `test_openai_stream_extracts_usage_and_records_to_ledger`: PASSED
  6. `test_anthropic_stream_extracts_usage_and_records_to_ledger`: PASSED
  7. `test_ollama_stream_extracts_tokens_and_records_local_zero`: PASSED
  8. `test_openai_tts_speech_accounting`: PASSED
  9. `test_elevenlabs_tts_speech_accounting`: PASSED
  10. `test_hardware_scan_no_invented_data`: PASSED
  11. `test_benchmark_simulation_labeling`: PASSED
  12. `test_benchmark_live_scoring_criteria`: PASSED

### Command 2: Core Limiter, Usage Ledger & Hardware Test Suite
```bash
.\.venv\Scripts\python.exe -m pytest tests/engine/test_resource_limiter.py tests/traces/test_usage_ledger.py tests/intelligence/test_hardware_wizard.py tests/integration/test_runtime_acceptance_audit.py -v
```
- **Exit Code:** `0`
- **Duration:** 30.33s
- **Results:** 39 passed, 0 failed

### Command 3: Frontend Test Suite
```bash
npm run test --prefix frontend
```
- **Exit Code:** `0`
- **Duration:** 28.61s
- **Results:** 23 test files passed, 173 tests passed, 0 failed

### Command 4: Frontend Production Build
```bash
npm run build --prefix frontend
```
- **Exit Code:** `0`
- **Duration:** 26.72s
- **Output:** Built both `dist/` and `../src/openjarvis/server/static/` with Vite and PWA Service Worker.

### Command 5: DevTools MCP Live UI Verification
- **Target URL:** `http://127.0.0.1:8000/dashboard`
- **Status:** Verified live rendering of 4-card metric grid:
  - *Estimated Spend* (`ESTIMATED` badge)
  - *Provider-Billed* (`RECONCILED` badge, authoritative billing sources)
  - *Local Inference* (`$0.00 API` badge, explicitly disclosing "excludes host electricity")
  - *Unmetered Calls* (`ACTION NEEDED` badge, capturing calls with missing pricing)
- **Auditable Ledger Modal:** Verified request rows with exact cost badges, provider/model attribution, and reconciliation status.

---

## 7. Security & Credential Audit

- **Automated Regex Scan:** Executed across all modified and untracked repository files using high-sensitivity regex rules for API keys (`sk-`, `ghp_`, `AIza`), bearer tokens, passwords, and private keys.
- **Audit Result:** `ZERO` plaintext secrets detected across all staged, modified, and untracked files.
- **Protected Assets:** User asset `screenshots/chrome_airluc_youtube.png` was preserved untouched with zero git diff.

---

## 8. Git Delivery Summary

- **Branch:** `main`
- **Target Remote:** `origin/main`
- **Scoped Commits:**
  - `feat(audit): complete runtime acceptance audit and gap-fix sprint`
    - Integrated rate limiting, concurrency gating, and task budgets into streaming and speech routes.
    - Added real provider usage extraction (prompt, completion, cached, reasoning tokens, speech characters, and request IDs) and ledger persistence.
    - Audited pricing catalog, removed generic fallbacks, and added official OpenAI TTS speech pricing.
    - Isolated 5 demo records to fixtures and created database backup.
    - Added physical core and Ollama version checks, eliminated invented hardware defaults, and labeled benchmark simulations.
    - Enhanced Cost Comparison dashboard to 4-card metric grid and resolved legacy dashboard routing conflict.
    - Added comprehensive 12-test integration audit suite.
