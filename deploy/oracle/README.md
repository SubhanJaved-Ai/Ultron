# Jarvis 2.0 — Oracle Cloud Free Tier Deployment Guide

Deploy your autonomous **Jarvis 2.0** personal AI assistant with zero ongoing server costs ($0/month forever) on Oracle Cloud Infrastructure (OCI) Free Tier.

---

## 1. Quick Install (1 Command)

SSH into your freshly created Oracle Cloud instance (Ubuntu 22.04 / 24.04 or Oracle Linux) and run:

```bash
curl -sSL https://raw.githubusercontent.com/Airlucofficial/Jarvis-2.0/main/deploy/oracle/install.sh | sudo bash
```

The script will automatically:
1. Install system libraries, Python 3.12, and `uv`.
2. Deploy the Jarvis 2.0 codebase and virtual environment.
3. Configure `/etc/jarvis/env` with secure default keys.
4. Set up and start the hardened `jarvis.service` systemd daemon.
5. Provide your live Hologram PWA link: `http://<YOUR_IP>:8000/hologram`.

---

## 2. Oracle Cloud Free Tier Specifications

Jarvis 2.0 is specifically optimized to fit within OCI Always-Free resource limits:

| Resource | OCI Free Tier Limit | Jarvis 2.0 Consumption |
| :--- | :--- | :--- |
| **Compute** | 1 OCPU AMD (1 GB RAM) or up to 4 OCPU ARM (24 GB RAM) | ~340 MB RAM in idle / ~600 MB peak |
| **Storage** | 200 GB Block Volume | ~4 GB disk space |
| **Network** | 10 TB outbound bandwidth / month | < 5 GB / month typical |
| **Total Cost** | **$0.00 / month forever** | **$0.00** |

---

## 3. Running 100% Free Local Models with Ollama (Zero API Keys)

To run completely free without paying for any cloud API keys, install **Ollama** directly on your Oracle Cloud instance (the Ampere A1 shape includes 24 GB of RAM, which is more than enough for 3B, 7B, and 14B models):

```bash
# 1. Install Ollama on your Oracle VM
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull your preferred local model (Qwen 2.5 or Llama 3.2 recommended)
ollama pull qwen2.5:7b     # High intelligence, tool calling (~4.7 GB RAM)
# or for snappy real-time voice:
ollama pull qwen2.5:3b     # Fast response, conversational (~2.2 GB RAM)

# 3. Jarvis automatically connects to Ollama on localhost:11434 with zero configuration!
sudo systemctl restart jarvis
```

---

## 4. Configuring Secrets & Optional Cloud Keys (BYOK)

If you prefer cloud models or optional external integrations, edit `/etc/jarvis/env`:

```bash
sudo nano /etc/jarvis/env
```

```ini
# Voice Synthesis & Transcription (Optional Lifelike Voice)
ELEVENLABS_API_KEY=your_elevenlabs_key_here
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb

# Messaging Channels (Optional)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
WHATSAPP_ACCESS_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=1092837465...

# Cloud LLM Providers (Optional — leave blank if using Ollama)
GEMINI_API_KEY=AIzaSy...
OPENAI_API_KEY=
GROQ_API_KEY=
```

Then restart the service:

```bash
sudo systemctl restart jarvis
```

---

## 4. Firewall & Oracle Security List

Ensure TCP port `8000` is open:

### On the VM:
```bash
sudo ufw allow 8000/tcp
# Or on Oracle Linux:
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### In Oracle Cloud Console:
1. Navigate to **Networking** → **Virtual Cloud Networks** → Select your VCN.
2. Under **Security Lists**, click **Default Security List**.
3. Click **Add Ingress Rules**:
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: `TCP`
   - **Destination Port Range**: `8000`

---

## 5. Connecting Your Local Home Computer (`jarvis-node`)

To give Cloud Jarvis access to your local desktop files and apps when your computer is powered on:

1. On your home computer, run:
```bash
python -m openjarvis.daemon.node_worker --server http://<YOUR_ORACLE_IP>:8000 --device-id <ID> --token <TOKEN>
```
2. When your home computer shuts down, Cloud Jarvis automatically transitions to Cloud-Only mode (handling YouTube, news, Google Sheets, email, and web tasks autonomously).
