# ULTRON — Manual End-to-End QA Checklist & Testing Guide

## Executive Summary
This document provides the owner's manual testing protocol for **Ultron (Jarvis 2.0)** following the Product Readiness Sprint. All unit tests, provider compatibility suites, file sandbox safety guardrails, and automated browser end-to-end journeys have completed with 100% pass rates.

The server is currently running and ready for hands-on human testing.

---

## 1. Quick Startup & Access Commands

### Application Server
- **Active URL:** `http://localhost:8000`
- **Hologram Interface:** `http://localhost:8000/hologram` (or `http://localhost:8000/hologram.html`)
- **API Documentation:** `http://localhost:8000/docs`
- **Pre-flight Health Check:** `http://localhost:8000/health` (returns `{"status":"ok"}`)

### Starting / Restarting the Server
If you ever need to restart the server manually:
```powershell
cd D:\Ultron
.\.venv\Scripts\python.exe -m openjarvis.server
```
*(The server binds to `0.0.0.0:8000` with hot-reload and static asset serving).*

---

## 2. Step-by-Step QA Testing Checklist

### Phase 1: White Glassmorphism Argon Hologram
- [ ] **Open Hologram Interface:** Navigate to `http://localhost:8000/hologram`.
- [ ] **Visual Theme Verification:** Verify the white glassmorphism HUD design:
  - Frosted white panels (`rgba(255, 255, 255, 0.84)` with `backdrop-filter: blur(24px)`).
  - Crisp slate typography and clean borders.
  - Central **Quantum Containment Lens** (`radial-gradient`) providing deep visual contrast for the 3D additive particle brain.
- [ ] **3D Canvas & Particle Brain:** Confirm the 3D neural brain is rotating smoothly and responding to mouse hover/drag interactions.
- [ ] **Responsive Viewport Testing:**
  - Resize the browser window to **Desktop (1280px+)**: HUD elements float neatly along the top and bottom.
  - Resize to **Tablet (768px)**: Floating panels stack elegantly; 3D canvas scales dynamically.
  - Resize to **Mobile (480px)**: Bottom command bar and top status indicators adjust with touch-friendly spacing.
- [ ] **Alternative Route Check:** Navigate to `http://localhost:8000/hologram.html` and verify identical appearance.

### Phase 2: Model Provider Configuration & Security
- [ ] **Open Settings Page:** Navigate to `http://localhost:8000/settings`.
- [ ] **Inference Source Selection:**
  - Check toggle between **Bundled Ollama** and **Custom OpenAI-compatible server**.
  - For Custom servers: Verify Host URL, Model ID, and API Key input fields.
- [ ] **Credential Masking & Sanitization:**
  - Enter test text into the OpenAI, Anthropic, or Gemini API key fields.
  - Confirm the input behaves as a password field (characters are hidden as dots).
  - Inspect network requests in DevTools: verify keys are never transmitted in cleartext URL query parameters.
- [ ] **Base URL Normalization:** Verify that entering `http://localhost:8000/v1` or `http://localhost:8000/v1/` does not generate double `/v1/v1` paths.

### Phase 3: Task Center & Execution
- [ ] **Open Task Center:** Navigate to `http://localhost:8000/tasks`.
- [ ] **Task Status Overview:** Verify the summary metric tiles (Total Tasks, Active, Needs Approval, Completed, Failed, Paused).
- [ ] **Create New Task:** Click the **"New Task"** button:
  - Enter prompt: `Run system diagnostics and verify memory availability`.
  - Click **"Start Task"** or **"Cancel"** to confirm modal dismissal.
- [ ] **Task Inspection:** Click any existing task in the list to view its execution steps, status badges, and output logs.

### Phase 4: File Sandbox Operations & Safety Guardrails
- [ ] **Create Disposable Sandbox:** Create a temporary test folder (e.g. `D:\Ultron\test_sandbox`).
- [ ] **Safe File Operations:** Test creating, reading, and editing files within the sandbox.
- [ ] **Path Traversal Defense:** Attempt a path traversal operation (e.g. `..\..\outside.txt`) and verify it is rejected.
- [ ] **Credential Protection:** Attempt to read or write a file named `.env` or `credentials.json` and verify the Ultron Safety Kernel hard-blocks the operation.

### Phase 5: Memory & Skills Control Center
- [ ] **Open Memory & Skills:** Navigate to `http://localhost:8000/memory-skills`.
- [ ] **Trust Tiers:** Verify filter tabs: **Trusted**, **Auto-Extracted**, and **Quarantined**.
- [ ] **Inspect Facts:** Click **"View Provenance & Metadata"** on an existing memory entry to inspect source origin, timestamp, and confidence score.
- [ ] **Learned Skills:** Switch to the **"Learned Skills"** tab to view governed workflows.

### Phase 6: MCP (Model Context Protocol) Server Integration
- [ ] **Open MCP Section:** On `http://localhost:8000/settings`, scroll to **"MCP Servers (Model Context Protocol)"**.
- [ ] **Add MCP Server:** Click **"Add MCP Server"**:
  - Enter Name: `test-mcp`
  - Select Transport: `HTTP` or `SSE`
  - Enter Endpoint URL: `http://localhost:8000/v1/mcp`
- [ ] **Connection Verification:** Click **"Validate & Save"** and observe response validation.

---

## 3. Disposable Sandbox Guidelines
When testing file write, read, or patch capabilities manually:
1. Always point file tools at a temporary folder, such as:
   `D:\Ultron\temp_qa_sandbox`
2. Never test deletion on root directories (`C:\`, `C:\Windows`, `D:\Ultron`).
3. Clean up temporary test files after concluding testing:
   ```powershell
   Remove-Item -Recurse -Force D:\Ultron\temp_qa_sandbox
   ```

---

## 4. Owner Bug Report Template

If any anomaly, visual defect, or execution issue is identified during manual testing, record it using the template below:

```markdown
### Bug Report

**Summary:** [Short descriptive title]
**Journey / Area:** [Hologram | Provider Settings | Task Center | Sandbox | Memory | MCP]
**Severity:** [Cosmetic | Low | Medium | High | Blocker]

**Steps to Reproduce:**
1. Navigate to ...
2. Click on ...
3. Enter value ...

**Expected Result:** [What should have happened]
**Actual Result:** [What actually happened]

**Environment:**
- OS: Windows 11
- Browser: Google Chrome / Edge
- Resolution: [e.g. 1920x1080 / 1280x800 / Mobile]
- Server Version / Commit: 546e021 (or current HEAD)

**Screenshots / Error Logs:**
[Paste screenshot or console error traceback here]
```
