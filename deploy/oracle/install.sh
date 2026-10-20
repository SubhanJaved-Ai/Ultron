#!/usr/bin/env bash
# ==============================================================================
# JARVIS 2.0 — 1-Click Oracle Cloud Free Tier Autonomous Installer
# Works on: Ubuntu 22.04/24.04 LTS, Oracle Linux 8/9 (x86_64 & ARM64 Ampere)
# Footprint: Fits comfortably in 1 GB RAM (AMD) or 24 GB RAM (ARM)
# ==============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "================================================================="
echo "       JARVIS 2.0 — ORACLE CLOUD FREE TIER INSTALLER"
echo "  Autonomous Personal AI: Hologram UI, Voice, Telegram & WhatsApp"
echo "================================================================="
echo -e "${NC}"

# 1. Root check
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Error: This script must be run as root (use sudo).${NC}"
  exit 1
fi

# 2. System updates & package installation
echo -e "${YELLOW}[1/7] Installing base system dependencies...${NC}"
if command -v apt-get &>/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl wget git build-essential sqlite3 python3 python3-pip python3-venv \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2
elif command -v dnf &>/dev/null; then
  dnf install -y curl wget git sqlite python3 python3-pip python3-devel gcc
fi

# 3. Install uv (ultra-fast Python package installer)
echo -e "${YELLOW}[2/7] Installing uv fast package manager...${NC}"
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 4. Create dedicated service user
echo -e "${YELLOW}[3/7] Setting up dedicated service user 'jarvis'...${NC}"
if ! id -u jarvis &>/dev/null; then
  useradd -m -s /bin/bash -d /opt/jarvis jarvis
fi
mkdir -p /opt/jarvis /etc/jarvis
chown -R jarvis:jarvis /opt/jarvis

# 5. Clone or deploy code
echo -e "${YELLOW}[4/7] Deploying Jarvis 2.0 codebase to /opt/jarvis...${NC}"
INSTALL_DIR="/opt/jarvis/app"
if [ ! -d "$INSTALL_DIR" ]; then
  if [ -d "/workspace/Jarvis 2.0" ]; then
    cp -r "/workspace/Jarvis 2.0" "$INSTALL_DIR"
  elif [ -d "$(pwd)" ] && [ -f "$(pwd)/pyproject.toml" ]; then
    cp -r "$(pwd)" "$INSTALL_DIR"
  else
    git clone https://github.com/SubhanJaved-Ai/Ultron.git "$INSTALL_DIR"
  fi
  chown -R jarvis:jarvis "$INSTALL_DIR"
fi

# 6. Build virtual environment & Native Rust Acceleration
echo -e "${YELLOW}[5/7] Creating optimized virtualenv and building native Rust core...${NC}"
sudo -u jarvis -H bash -c "
  cd /opt/jarvis/app
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  
  # Install Rust toolchain for native C/Rust high-performance execution
  if ! command -v cargo &>/dev/null && [ ! -d \"\$HOME/.cargo\" ]; then
    echo 'Installing Rust toolchain for native acceleration...'
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal || true
  fi
  [ -f \"\$HOME/.cargo/env\" ] && source \"\$HOME/.cargo/env\"
  export PATH=\"\$HOME/.cargo/bin:\$PATH\"

  uv venv .venv --python 3.12
  source .venv/bin/activate
  uv pip install -e \".[server]\"
  uv pip install \"maturin>=1.12.6,<2\"

  # Compile native openjarvis_rust module if manifest is present
  if [ -f \"rust/crates/openjarvis-python/Cargo.toml\" ] && command -v cargo &>/dev/null; then
    echo 'Compiling native openjarvis_rust high-speed extension...'
    maturin develop --release -m rust/crates/openjarvis-python/Cargo.toml || echo 'Rust extension build optional; continuing with Python runtime'
  fi
"

# 6b. Optional Ollama setup for 100% Free Local AI inference
if [ "${INSTALL_OLLAMA:-false}" = "true" ] || [ "${1:-}" = "--with-ollama" ]; then
  echo -e "${YELLOW}Installing Ollama for local LLM inference...${NC}"
  curl -fsSL https://ollama.com/install.sh | sh || true
  systemctl enable --now ollama || true
fi

# 7. Environment & Secrets setup
echo -e "${YELLOW}[6/7] Configuring environment secrets (/etc/jarvis/env)...${NC}"
if [ ! -f /etc/jarvis/env ]; then
  AUTH_KEY=$(openssl rand -hex 16)
  cat <<EOF > /etc/jarvis/env
# ==============================================================================
# Jarvis 2.0 Environment Configuration
# ==============================================================================
OPENJARVIS_API_KEY=${AUTH_KEY}
OPENJARVIS_HOST=0.0.0.0
OPENJARVIS_PORT=8000

# Voice Engine Configuration (Optional BYOK)
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb

# Messaging Channels (Optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHATS=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=

# LLM Providers (Optional BYOK)
GEMINI_API_KEY=
OPENAI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
EOF
  chmod 0600 /etc/jarvis/env
  echo -e "${GREEN}Generated fresh API key: ${AUTH_KEY}${NC}"
fi

# 8. Setup hardened systemd service
echo -e "${YELLOW}[7/7] Registering systemd service (jarvis.service)...${NC}"
cat <<'EOF' > /etc/systemd/system/jarvis.service
[Unit]
Description=Jarvis 2.0 Autonomous AI Server
After=network.target

[Service]
Type=simple
User=jarvis
WorkingDirectory=/opt/jarvis/app
ExecStart=/opt/jarvis/app/.venv/bin/jarvis serve --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/etc/jarvis/env

# Security Hardening
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=/opt/jarvis
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable jarvis.service
systemctl restart jarvis.service

# 8b. Configure Oracle Cloud Host Firewall (Open port 8000)
echo -e "${YELLOW}Configuring host firewall for port 8000...${NC}"
if command -v ufw &>/dev/null; then
  ufw allow 8000/tcp || true
fi
if command -v iptables &>/dev/null; then
  iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 8000 -j ACCEPT 2>/dev/null || true
  if command -v netfilter-persistent &>/dev/null; then
    netfilter-persistent save 2>/dev/null || true
  fi
fi

# 9. Get Public IP
PUBLIC_IP=$(curl -s -m 4 https://ifconfig.me || echo "YOUR-SERVER-IP")

echo ""
echo -e "${GREEN}=================================================================${NC}"
echo -e "${GREEN}  SUCCESS: Jarvis 2.0 is installed and running on Oracle Cloud!  ${NC}"
echo -e "${GREEN}=================================================================${NC}"
echo ""
echo -e "  ✦ Hologram Interface:  ${CYAN}http://${PUBLIC_IP}:8000/hologram${NC}"
echo -e "  ✦ API Server:          ${CYAN}http://${PUBLIC_IP}:8000/v1${NC}"
echo -e "  ✦ Service Status:      ${CYAN}sudo systemctl status jarvis${NC}"
echo -e "  ✦ View Logs:           ${CYAN}sudo journalctl -u jarvis -f${NC}"
echo -e "  ✦ Edit Secrets:        ${CYAN}sudo nano /etc/jarvis/env${NC}"
echo ""
echo -e "${YELLOW}Tip (100% Free Local AI): Run 'ollama pull qwen2.5:7b' to load free local intelligence.${NC}"
echo -e "${YELLOW}Tip (Optional Cloud Keys): Edit /etc/jarvis/env and run 'sudo systemctl restart jarvis'.${NC}"
