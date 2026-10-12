# Open Jarvis Deployment Runbook (Release Candidate Verification)

**Platform Support:** Windows 10/11, Ubuntu 22.04 LTS / 24.04 LTS, Oracle Linux 8/9  
**Deployment Models:**  
- **Target A:** Local Workstation / Laptop (Single Operator, Loopback, Zero-Friction)  
- **Target B:** Hardened Public Multi-User Deployment (Linux Cloud VM behind NGINX TLS Reverse Proxy)

---

## 1. Target A: Local Workstation Installation & Run (Verified)

### Prerequisites
- Python 3.10+ (Recommended: Python 3.12)
- Git
- Modern Chromium Browser (Google Chrome, Microsoft Edge, Brave, Opera) for Web Speech recognition and WebGL Three.js canvas.

### Quick Start Commands
```powershell
# 1. Clone repository
git clone https://github.com/Airlucofficial/Jarvis-2.0.git Ultron
cd Ultron

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Install core and server dependencies
pip install -e ".[server]"

# 4. Optional: Configure Gemini Cloud Cognitive Key in .env
# GEMINI_API_KEY="AIzaSy..."

# 5. Launch Open Jarvis in single-user mode with 3D Hologram Interface
python -m openjarvis.cli serve --hologram --port 8000
```

- The server starts on `http://127.0.0.1:8000`.
- In single-user mode (`OPENJARVIS_MULTI_USER=0`), authentication is disabled on loopback for immediate, zero-friction local personal assistant operation.
- The browser automatically opens to `http://127.0.0.1:8000/hologram`.

---

## 2. Target B: Hardened Public Multi-User Deployment

### 2.1 Multi-User Configuration & Environment Variables
In multi-user mode, Open Jarvis activates the OWASP-compliant 600,000 iteration PBKDF2 authentication gateway, session token hashing, tenant data isolation, and RBAC tool execution.

Generate a fresh, unique 32-byte (64 hex characters) cryptographic secret key before configuring the environment. **Every deployment must generate and use its own secret key stored strictly outside source control. Never use a shared or published example key, as any published key must be treated as compromised.**

Generate a key using one of the following commands:
```bash
# Using OpenSSL (recommended):
openssl rand -hex 32

# Or using Python (built-in secrets module):
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Configure `/etc/jarvis/env` (ensure file permissions are strictly restricted to `chmod 600 /etc/jarvis/env` owned by `jarvis:jarvis`):
```bash
# Enable multi-user authentication and tenant isolation
OPENJARVIS_MULTI_USER=1

# Secret key for server signing and token validation.
# Replace <GENERATE_WITH_OPENSSL_RAND_HEX_32> with the output of the generation command above.
# WARNING: Do NOT use a static, default, or public key.
OPENJARVIS_SECRET_KEY="<GENERATE_WITH_OPENSSL_RAND_HEX_32>"

# Host and Port (binds locally behind reverse proxy)
OPENJARVIS_HOST=127.0.0.1
OPENJARVIS_PORT=8000

# Base Configuration Directory (stores users.db, sessions.db, workflows/)
OPENJARVIS_CONFIG_DIR=/var/lib/jarvis

# Maximum request payload size (25MB)
OPENJARVIS_MAX_BODY_SIZE=26214400

# Optional: LLM brain key (supply your own private API key)
GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"
```

### 2.2 Systemd Service Configuration
File: `/etc/systemd/system/jarvis.service`
```ini
[Unit]
Description=Open Jarvis Multi-User Production Agent Platform
After=network.target

[Service]
Type=simple
User=jarvis
Group=jarvis
WorkingDirectory=/opt/jarvis/app
EnvironmentFile=/etc/jarvis/env
ExecStart=/opt/jarvis/app/.venv/bin/python -m openjarvis.cli serve --host 127.0.0.1 --port 8000 --multi-user
Restart=always
RestartSec=5
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 2.3 NGINX Reverse Proxy with TLS and Rate Limiting
File: `/etc/nginx/sites-available/openjarvis.conf`
```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=jarvis_api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=jarvis_auth:10m rate=2r/s;

# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name jarvis.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name jarvis.yourdomain.com;

    # TLS Certificates (managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/jarvis.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jarvis.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 25M;

    # Static assets and UI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # Authentication routes with strict rate limiting
    location /api/auth/ {
        limit_req zone=jarvis_auth burst=5 nodelay;
        proxy_pass http://127.0.0.1:8000/api/auth/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # API routes with burst rate limiting
    location /api/ {
        limit_req zone=jarvis_api burst=20 nodelay;
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSocket endpoints
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

---

## 3. Operational Health Checks, Smoke Tests & Automated Staging Rehearsal

### Automated Staging Rehearsal Script
To simulate the full production lifecycle without touching live infrastructure:
```bash
python deploy/staging_rehearsal.py
```
This script executes and verifies 8/8 end-to-end production stages:
1. Environment initialization and variable verification.
2. Health & readiness probes (`GET /health`).
3. Multi-user bootstrapping (first user admin, second user standard user).
4. Secure session issuance (tokens & cookies).
5. Protected directive execution and unauthenticated 401 blocking.
6. Hot online SQLite database backup (`sqlite3.backup`).
7. Simulated disaster deletion & point-in-time restoration.
8. Process restart recovery and persistent session validation.

### Manual Smoke Test Commands
```bash
# 1. Health Probe
curl -I http://127.0.0.1:8000/health

# 2. Registration (Bootstrap Admin)
curl -X POST http://127.0.0.1:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "SecurePassword123!"}'

# 3. Authenticated Directive
curl -X POST http://127.0.0.1:8000/api/hologram/directive \
     -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"directive": "System status"}'

# 4. Unauthenticated Directive (Must return 401)
curl -I -X POST http://127.0.0.1:8000/api/hologram/directive \
     -H "Content-Type: application/json" \
     -d '{"directive": "System status"}'
```

---

## 4. Backup, Storage Isolation, Disaster Recovery & Rollback

### Data Directory Location
When configured, all multi-tenant databases reside under `OPENJARVIS_CONFIG_DIR` (e.g. `/var/lib/jarvis/`):
- `users.db`: User accounts, OWASP 600k PBKDF2 hashes, session hashes, lockout tables, and per-user preferences.
- `sessions.db`: Chat conversation sessions partitioned by `user_id` and FTS5 search index.
- `workflows/<user_id>/`: Tenant-isolated workflow JSON/TOML definitions.
- `memory.db`: Local vector/FTS document store.

### Automated Hot Backup Procedure
```bash
#!/usr/bin/env bash
BACKUP_DIR="/var/backups/jarvis"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
sqlite3 /var/lib/jarvis/users.db ".backup '${BACKUP_DIR}/users_${TIMESTAMP}.db'"
sqlite3 /var/lib/jarvis/sessions.db ".backup '${BACKUP_DIR}/sessions_${TIMESTAMP}.db'"
tar -czvf "${BACKUP_DIR}/workflows_${TIMESTAMP}.tar.gz" -C /var/lib/jarvis workflows/
find "$BACKUP_DIR" -type f -mtime +14 -delete
```

### Point-in-Time Disaster Recovery Restore
In the event of database corruption or hardware failure:
1. Stop the application: `sudo systemctl stop jarvis`
2. Restore the latest verified snapshot:
   ```bash
   cp /var/backups/jarvis/users_latest.db /var/lib/jarvis/users.db
   cp /var/backups/jarvis/sessions_latest.db /var/lib/jarvis/sessions.db
   tar -xzvf /var/backups/jarvis/workflows_latest.tar.gz -C /var/lib/jarvis/
   ```
3. Restart the service: `sudo systemctl start jarvis`
4. Run `deploy/staging_rehearsal.py` or smoke check `/health` to verify full service recovery.

### Rollback Procedure
If a regression occurs after updating code:
1. `sudo systemctl stop jarvis`
2. `git checkout <previous_stable_commit>`
3. `source .venv/bin/activate && pip install -e ".[server]"`
4. `sudo systemctl start jarvis`
5. Verify `curl -I http://127.0.0.1:8000/health` returns `200 OK`.
