# ULTRON — MANUAL END-TO-END ACCEPTANCE CHECKLIST
**Purpose:** Pre-Release Owner Acceptance & Verification Manual Test Protocol  
**Repository:** `D:\Ultron`  
**Target Environment:** Local Windows Workstation (`localhost:8000`)  
**Prerequisites:** Python 3.12 Virtual Environment (`.venv`), Node.js / npm, Optional: Local Ollama daemon or Cloud API keys (Gemini / OpenAI / Anthropic)

---

## Pre-Flight Checklist

- [ ] Repository is on branch `main` with clean working tree.
- [ ] Dependencies installed:
  - Python: `pip install -e ".[dev]"`
  - Frontend: `npm install --prefix frontend`
- [ ] Database baseline: `usage_ledger.db` exists or will auto-create on first write.
- [ ] Backend server starts without crash:
  ```powershell
  .\.venv\Scripts\python.exe -m openjarvis.server
  ```
- [ ] Browser navigates to `http://localhost:8000/` and renders Ultron SPA without critical console exceptions.

---

## Test Suite 1: Health, Diagnostics & Basic Navigation

### Test 1.1: System Health Endpoint
- **Precondition:** Backend server running on `http://127.0.0.1:8000`.
- **Action:** Execute HTTP GET request to `/health`.
  ```powershell
  Invoke-RestMethod -Uri http://127.0.0.1:8000/health
  ```
- **Expected Result:**
  - Status code: `200 OK`.
  - Body: `{"status": "ok"}`.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 1.2: SPA Page Routing
- **Precondition:** Web app open in browser.
- **Action:** Click sidebar navigation links:
  1. `Chat` (`/`)
  2. `Tasks` (`/tasks`)
  3. `Memory & Skills` (`/memory-skills`)
  4. `Dashboard` (`/dashboard`)
  5. `Settings` (`/settings`)
- **Expected Result:**
  - Each view mounts instantaneously without page reload.
  - Active navigation item highlights correctly.
  - No 404 or uncaught JavaScript exceptions in Developer Tools console.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Test Suite 2: Local & Cloud Conversational Inference

### Test 2.1: Local or Mock Inference Streaming
- **Precondition:** Active chat window open at `/`.
- **Action:** Send a prompt: `"Reply with exactly: System operational."`
- **Expected Result:**
  - Message bubble immediately appears with streaming cursor.
  - Text streams smoothly token-by-token.
  - Generation completes and final response matches prompt directive.
  - Cost badge in sidebar or header updates accurately (`$0.00` for local, or nominal fraction of a cent for cloud).
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 2.2: Partial Stream Interruption
- **Precondition:** Chat session active.
- **Action:**
  1. Send a long prompt: `"Write an extensive 20-paragraph essay on the history of computing."`
  2. After 3 seconds of streaming, click the **Stop Generation** button.
- **Expected Result:**
  - Stream immediately halts.
  - Input box returns to editable ready state.
  - Usage ledger logs stream with `interrupted: true` and `partial_stream: true` metadata.
  - Token count only counts tokens generated up to interruption point; no phantom hallucinated tokens billed.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Test Suite 3: Persistent Task Runner & DAG Execution

### Test 3.1: Natural Language Task Planning & Execution
- **Precondition:** Navigate to `/tasks`.
- **Action:** Submit new task with prompt: `"Analyze current system files and create a summary report"`.
- **Expected Result:**
  - Persistent Task Runner decomposes prompt into an ordered DAG of steps.
  - Steps transition: `pending` -> `running` -> `completed`.
  - Progress bar advances proportionally (0% -> 100%).
  - Step logs and outputs display in the step detail panel.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 3.2: Task Creation Idempotency & Safe Replay
- **Precondition:** Task created in Test 3.1.
- **Action:** Send a `POST /api/tasks` request via curl or PowerShell with the identical `idempotency_key`:
  ```powershell
  $body = @{ prompt = "List system files for audit"; idempotency_key = "unique-test-key-001" } | ConvertTo-Json
  $res1 = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/tasks -Method Post -Body $body -ContentType "application/json"
  $res2 = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/tasks -Method Post -Body $body -ContentType "application/json"
  ```
- **Expected Result:**
  - `$res1.task.task_id` equals `$res2.task.task_id`.
  - `$res2.idempotent_replay` is `True`.
  - No duplicate task is created; no steps are re-executed.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 3.3: Task Pause, Resume & Cancel Controls
- **Precondition:** A multi-step task is running.
- **Action:**
  1. Click **Pause Task** on a running task.
  2. Verify state changes to `paused` and active worker ceases dispatching new steps.
  3. Click **Resume Task**.
  4. Verify state returns to `running` and subsequent steps execute.
  5. Click **Cancel Task**.
  6. Verify all remaining `pending` steps transition to `cancelled`.
- **Expected Result:**
  - Task state machine accurately reflects operator commands without orphaned background processes.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Test Suite 4: Safety Kernel & Operator Approvals

### Test 4.1: High-Risk Action Approval Gate
- **Precondition:** Task contains a high-risk tool call (e.g., shell command execution or file modification).
- **Action:** Launch the task.
- **Expected Result:**
  - High-risk step automatically transitions to `waiting_approval`.
  - UI displays modal or banner indicating operator intervention required.
  - Step provides clear explanation of the proposed action, parameters, and duplicate risk.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 4.2: Approval Authorization & Execution
- **Precondition:** Step waiting in `waiting_approval` state.
- **Action:** Click **Approve Step** (providing safety confirmation code if configured).
- **Expected Result:**
  - Approval token verified against action fingerprint.
  - Step executes and finishes. Downstream steps resume.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 4.3: Operator Rejection Aborts Downstream Steps
- **Precondition:** Step waiting in `waiting_approval` state.
- **Action:** Click **Reject Step**.
- **Expected Result:**
  - Target step marked `rejected`.
  - Downstream steps depending on this step are aborted.
  - Task status reflects honest termination due to operator policy denial.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Test Suite 5: Usage Ledger & Billing Reconciliation Audit

### Test 5.1: Cloud Usage Export with Timestamp Filters
- **Precondition:** At least one usage record or empty ledger.
- **Action:**
  ```powershell
  # Test with ISO-8601 string
  Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/usage/export?start_time=2026-01-01T00:00:00Z&end_time=2026-12-31T23:59:59Z"
  ```
- **Expected Result:**
  - Status code: `200 OK`.
  - Header: `Content-Type: text/csv`.
  - Header: `Content-Disposition: attachment; filename=ultron_cloud_usage_ledger.csv`.
  - CSV contains headers: `request_id,session_id,provider,model,input_tokens,output_tokens,total_tokens,cost_usd,cost_type,timestamp,reconciled_cost_usd,reconciled_at,reconciliation_source`.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 5.2: Authoritative Billing Reconciliation Provenance
- **Precondition:** Record in usage ledger.
- **Action:** Submit billing reconciliation:
  ```powershell
  $body = @{
    request_id = "test-req-001"
    provider_billed_cost = 0.042
    source = "Invoice-2026-10"
  } | ConvertTo-Json
  Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/usage/reconcile -Method Post -Body $body -ContentType "application/json"
  ```
- **Expected Result:**
  - Record cost updated to `0.042` with cost category `PROVIDER_BILLED`.
  - Metadata captures `reconciliation_source: "Invoice-2026-10"`, `reconciled_at`, and `reconciled_cost_usd: 0.042`.
  - Submitting negative cost (`-1.0`) or short source (`""`) returns `422 Unprocessable Entity`.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Test Suite 6: One-Click Local Model Recommendation & Wizard

### Test 6.1: Hardware Discovery Scan
- **Precondition:** Navigate to `/settings`.
- **Action:** In the "One-Click Local Model Recommendation & Wizard" section, click **Scan Hardware & Recommend**.
- **Expected Result:**
  - Non-privileged scan runs within 2 seconds.
  - System hardware specifications render:
    - CPU cores detected.
    - System RAM detected (or honest `unverified system RAM` fallback if obscured).
    - GPU vendor and VRAM detected (or `None (CPU Only)` if no discrete GPU).
    - Ollama connectivity status reported.
  - Zero crashes from null/None metric formatting.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 6.2: Ranked Recommendations & Capacity Safety
- **Precondition:** Hardware scan completed.
- **Action:** Review recommended model cards.
- **Expected Result:**
  - Models requiring more RAM than available are flagged with `INSUFFICIENT_MEMORY` (e.g. 70B models on 8GB machines).
  - Models fitting available memory are ranked by suitability score (e.g. Qwen 3 4B with ~85/100).
  - Suitability breakdown cites tool-calling reliability, context window, and license.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 6.3: Simulated Benchmark Honesty
- **Precondition:** Hardware recommendations visible.
- **Action:** Click **Benchmark** on a recommended model when running in simulation mode.
- **Expected Result:**
  - Benchmark completes and reports tokens/sec and latency estimates.
  - Backend record sets `empirical_score_verified = False` to prevent simulation data from masquerading as physical hardware benchmarks.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Test Suite 7: REST API Error Handlers & Centralized Limits

### Test 7.1: Centralized 422 Validation Error
- **Action:** Send invalid JSON to `/v1/usage/reconcile` (negative cost).
- **Expected Result:**
  - Status code: `422 Unprocessable Entity`.
  - Body contains dual-format:
    - `"detail"`: array of Pydantic validation errors (backward-compatible).
    - `"error"`: `{"code": "VALIDATION_ERROR", "message": "Request validation failed", "status": 422, "details": [...]}`.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 7.2: Centralized 404 Not Found Error
- **Action:** Send GET request to `/api/tasks/nonexistent-id-0000`.
- **Expected Result:**
  - Status code: `404 Not Found`.
  - Body contains:
    - `"detail"`: `"Task 'nonexistent-id-0000' not found."`
    - `"error"`: `{"code": "NOT_FOUND", "message": "Task 'nonexistent-id-0000' not found.", "status": 404}`.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

### Test 7.3: Circuit Breaker & Concurrency Protection
- **Precondition:** Settings page -> Runtime Reliability section.
- **Action:** Inspect rate limits and click **Reset All Breakers**.
- **Expected Result:**
  - Provider limits display RPM, TPM, and Concurrency limits.
  - Breaker status shows `CLOSED` (healthy).
  - Reset button resets failure counters and confirms with success toast.
- **Pass / Fail Criteria:** [ ] Pass / [ ] Fail

---

## Sign-Off

| Role | Name | Status | Date |
|---|---|---|---|
| Engineering Lead / Agent | Antigravity AI | VERIFIED (Automated & MCP Audits Complete) | 2026-10-19 |
| Product Owner / Reviewer | | [ ] APPROVED FOR RELEASE | |
