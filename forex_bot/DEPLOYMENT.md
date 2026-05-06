# 🚀 Forex Bot System - Deployment Guide

## Table of Contents
1. [Local Development Setup](#local-development-setup)
2. [Docker Deployment](#docker-deployment)
3. [Production Deployment (VPS)](#production-deployment-vps)
4. [Monitoring & Maintenance](#monitoring--maintenance)
5. [Troubleshooting](#troubleshooting)

---

## Local Development Setup

### Prerequisites
- Python 3.11+
- pip/poetry
- Git

### Step 1: Clone & Setup Virtual Environment

```bash
cd forex_bot_system/forex_bot
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### Step 2: Install Dependencies

```bash
cd license_server
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit .env with your values
nano .env  # or use your editor
```

**Critical settings:**
- `SECRET_KEY`: Generate random 64-char string
- `ADMIN_PASSWORD`: Strong password
- `SMTP_*`: Gmail/email credentials
- `TELEGRAM_*`: Bot token & chat ID (optional)

### Step 4: Initialize Database

```bash
python -c "import asyncio; from core.database import init_db; asyncio.run(init_db())"
```

### Step 5: Run Server

```bash
python main.py
# Server running at http://localhost:8000
# API docs: http://localhost:8000/docs
```

---

## Docker Deployment

### Quick Start

```bash
# Build image
docker build -t forex-bot-server:latest -f Dockerfile .

# Run container
docker run -d \
  --name forex-bot \
  -p 8000:8000 \
  -e SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))') \
  -e ADMIN_PASSWORD=YourSecurePassword123 \
  -v ./license_server/logs:/app/logs \
  -v ./license_server/backups:/app/backups \
  forex-bot-server:latest
```

### Using Docker Compose

```bash
# Create .env file
cp license_server/.env.example .env

# Edit .env with your settings
nano .env

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f license-server

# Stop
docker-compose down
```

### Verify Container Health

```bash
# Check health
curl http://localhost:8000/docs

# View logs
docker logs forex-bot

# Monitor resources
docker stats forex-bot
```

---

## Production Deployment (VPS)

### 1. VPS Setup (Ubuntu 22.04+)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Deploy Application

```bash
# Clone repository
git clone https://github.com/your-repo/forex_bot_system.git
cd forex_bot_system/forex_bot

# Create .env with production values
cat > .env << EOF
PORT=8000
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_ADMIN_CHAT_ID=your-chat-id
EOF

# Set permissions
chmod 600 .env

# Start with Docker Compose
docker-compose up -d

# Verify
docker-compose logs -f license-server
```

### 3. Setup Reverse Proxy (Nginx)

```bash
# Install Nginx
sudo apt install nginx -y

# Create Nginx config
sudo nano /etc/nginx/sites-available/forex-bot
```

**Nginx Configuration:**

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Proxy to FastAPI
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

**Enable site:**

```bash
sudo ln -s /etc/nginx/sites-available/forex-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Setup SSL with Let's Encrypt
sudo apt install certbot python3-certbot-nginx -y
sudo certbot certonly --nginx -d your-domain.com
```

### 4. Setup Systemd Service (Optional)

```bash
# Create service file
sudo nano /etc/systemd/system/forex-bot.service
```

**Service configuration:**

```ini
[Unit]
Description=Forex Bot License Server (Docker)
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/root/forex_bot_system/forex_bot
ExecStart=docker-compose up
ExecStop=docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable service:**

```bash
sudo systemctl enable forex-bot
sudo systemctl start forex-bot
```

---

## Monitoring & Maintenance

### Log Management

```bash
# Real-time logs
docker-compose logs -f license-server

# Log rotation (create logrotate config)
sudo nano /etc/logrotate.d/forex-bot
```

**Logrotate config:**

```
/root/forex_bot_system/forex_bot/license_server/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
    missingok
}
```

### Database Backups

```bash
# Manual backup
docker exec forex-bot python -c "
from core.backup import DatabaseBackup
from pathlib import Path
import asyncio
backup = DatabaseBackup(Path('forex_license.db'))
asyncio.run(backup.create_backup(compress=True))
"

# Automated daily backup (cron)
0 2 * * * cd /root/forex_bot_system/forex_bot && docker-compose exec -T license-server python -c "from core.backup import *; asyncio.run(init_backup_system(Path('forex_license.db')))"
```

### Health Checks

```bash
# Check API health
curl https://your-domain.com/docs

# Check database
docker-compose exec license-server sqlite3 forex_license.db ".tables"

# Check backups
docker-compose exec license-server ls -la backups/
```

### Update Application

```bash
# Pull latest
git pull origin main

# Rebuild docker image
docker-compose build --no-cache

# Restart services
docker-compose up -d

# Check logs
docker-compose logs -f license-server
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
docker-compose up -d -p 8001:8000
```

### SMTP Not Working

```bash
# Test email
docker-compose exec license-server python -c "
from core.email_utils import send_code_email
import asyncio
result = asyncio.run(send_code_email('test@example.com', '123456', 'user_login'))
print(f'Email sent: {result}')
"
```

### Database Locked

```bash
# Check database status
docker-compose exec license-server sqlite3 forex_license.db "PRAGMA journal_mode=WAL;"

# Rebuild if corrupted
docker-compose exec license-server python -c "
from core.backup import DatabaseBackup
from pathlib import Path
backup = DatabaseBackup(Path('forex_license.db'))
backup.restore_backup(Path('backups/latest_backup.db.gz'))
"
```

### Bot Connection Issues

```bash
# Check server logs
docker-compose logs -f license-server | grep "verify\|ping\|license"

# Test bot verify endpoint
curl -X POST http://localhost:8000/bot/verify \
  -H "Content-Type: application/json" \
  -d '{"license_key":"TEST_KEY","mt_account":"12345"}'
```

### Memory Usage High

```bash
# Check container memory
docker stats forex-bot

# Clean up old backups
docker-compose exec license-server python -c "
from core.backup import DatabaseBackup
from pathlib import Path
backup = DatabaseBackup(Path('forex_license.db'))
backup.cleanup_old_backups(keep_days=7, max_backups=30)
"
```

---

## Security Best Practices

1. **Always use HTTPS** in production
2. **Rotate SECRET_KEY** periodically
3. **Use strong admin passwords** (16+ characters)
4. **Enable 2FA** for sensitive operations
5. **Monitor logs** for suspicious activity
6. **Regular backups** (automated daily)
7. **Update dependencies** monthly
8. **Firewall rules** - allow only necessary ports
9. **Rate limiting** enabled on all public endpoints
10. **Regular security audits**

---

## Performance Tuning

### Database Optimization

```bash
# Enable WAL mode
docker-compose exec license-server sqlite3 forex_license.db "PRAGMA journal_mode=WAL;"

# Optimize indexes
docker-compose exec license-server sqlite3 forex_license.db "
CREATE INDEX idx_licenses_user_id ON licenses(user_id);
CREATE INDEX idx_licenses_key ON licenses(license_key);
CREATE INDEX idx_bot_sessions_license ON bot_sessions(license_key);
CREATE INDEX idx_trade_logs_license ON trade_logs(license_key);
"
```

### Rate Limiting Tuning

Edit `.env`:
```
MAX_REQUESTS_PER_MINUTE=100  # Adjust based on load
BOT_PING_INTERVAL_SECONDS=300  # Increase if too frequent
```

---

## Support & Monitoring

- **Status Page**: `/docs` (API documentation)
- **Admin Dashboard**: `/dashboard`
- **User Portal**: `/user`
- **Logs**: `./logs/` directory
- **Backups**: `./backups/` directory

For issues, check:
1. `logs/app_*.log` - Application logs
2. `logs/errors_*.log` - Error logs
3. Docker logs: `docker-compose logs license-server`
