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
git clone https://github.com/Airlucofficial/Jarvis-2.0.git
cd Jarvis-2.0

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
curl -fsSL https://raw.githubusercontent.com/Airlucofficial/Jarvis-2.0/main/deploy/oracle/install.sh | bash
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
jarvis                          # start interactive console (concise Ultron persona)
jarvis serve --hologram         # start 3D Holographic web interface with voice barge-in
jarvis ask "Run security audit" # execute single directive directly
```

OpenJarvis ships with eight built-in agents across three execution modes (on-demand, scheduled, continuous):

| Agent | Type | What it does |
|-------|------|-------------|
| `morning_digest` | Scheduled | Daily briefing from email, calendar, health, news — with TTS audio |
| `deep_research` | On-demand | Multi-hop research with citations across web and local docs |
| `monitor_operative` | Continuous | Long-horizon monitoring with memory, compression, and retrieval |
| `orchestrator` | On-demand | Multi-turn reasoning with automatic tool selection |
| `native_react` | On-demand | ReAct (Thought-Action-Observation) loop agent |
| `operative` | Continuous | Persistent autonomous agent with state management |
| `native_openhands` | On-demand | CodeAct — generates and executes Python code |
| `simple` | On-demand | Single-turn chat, no tools |

See the [User Guide](https://open-jarvis.github.io/OpenJarvis/user-guide/morning-digest/) and [Tutorials](https://open-jarvis.github.io/OpenJarvis/tutorials/) for detailed setup instructions.

Full documentation — including Docker deployment, cloud engines, development setup, and tutorials — at **[open-jarvis.github.io/OpenJarvis](https://open-jarvis.github.io/OpenJarvis/)**.

## Community

- **GitHub:** [github.com/open-jarvis/OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
- **Discord:** [discord.gg/CMVBmDQ5Fj](https://discord.gg/CMVBmDQ5Fj)
- **X / Twitter:** [@OpenJarvisAI](https://x.com/OpenJarvisAI)
- **Docs:** [open-jarvis.github.io/OpenJarvis](https://open-jarvis.github.io/OpenJarvis/)

## Contributing

We welcome contributions! See the [Contributing Guide](CONTRIBUTING.md) for incentives, contribution types, and the PR process.

Quick start for contributors:

```bash
git clone https://github.com/Airlucofficial/Jarvis-2.0.git
cd Jarvis-2.0
uv sync --extra dev
uv run pre-commit install
uv run pytest tests/ -v
```

Browse the [Roadmap](https://open-jarvis.github.io/OpenJarvis/development/roadmap/) for areas where help is needed. Comment **"take"** on any issue to get auto-assigned.

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
