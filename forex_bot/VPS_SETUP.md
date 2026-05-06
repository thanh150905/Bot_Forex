# 🚀 VPS Deployment - Step by Step

## 1️⃣ Chọn VPS Provider

### **Recommended: DigitalOcean** (Easiest)
- **Price**: $5/month
- **Specs**: 1 vCPU, 1GB RAM, 25GB SSD
- **Link**: https://www.digitalocean.com
- **Promo**: Code `ONEXONE` = $100 credit (60 days)

**Steps:**
1. Go to https://www.digitalocean.com
2. Sign up
3. Click "Create" → "Droplet"
4. Choose:
   - **Region**: Singapore/Tokyo (closest to Vietnam)
   - **Image**: Ubuntu 22.04 LTS
   - **Size**: $5/month plan
   - **Hostname**: `forex-bot-1`
5. Click "Create Droplet"
6. Wait 2-3 minutes
7. Check email for root password
8. Note the IP address

---

## 2️⃣ First Time SSH Access

### **Windows (PowerShell):**
```powershell
# Install SSH if needed
# Or use PuTTY / Windows Terminal

ssh root@your_vps_ip_address
# Enter password from email
```

### **Mac/Linux:**
```bash
ssh root@your_vps_ip_address
```

### **Using PuTTY (Easiest for Windows):**
1. Download: https://www.putty.org
2. Open PuTTY
3. Enter IP address
4. Click "Open"
5. Login: `root`
6. Password: (paste from email)

---

## 3️⃣ Quick Deployment (One Command)

### **If using DigitalOcean:**

```bash
# Run one command (copies to clipboard)
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/forex_bot_system/main/deploy.sh | bash
```

### **Or Manual Steps:**

```bash
# 1. Update system
apt-get update && apt-get upgrade -y

# 2. Install Docker
curl -fsSL https://get.docker.com | sh

# 3. Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 4. Clone your repo
cd /root
git clone https://github.com/YOUR_USERNAME/forex_bot_system.git
cd forex_bot_system/forex_bot

# 5. Setup environment
cp license_server/.env.example .env
nano .env  # Edit with your SMTP, Telegram, etc.

# 6. Build and start
docker build -t forex-bot:latest -f Dockerfile .
docker-compose up -d

# 7. Check status
docker-compose logs -f license-server
```

---

## 4️⃣ Configure .env on VPS

After cloning, edit `.env`:

```bash
nano .env
```

**Essential settings:**
```
PORT=8000
SECRET_KEY=generate_64_random_chars
ADMIN_PASSWORD=YourSecurePassword123!

# SMTP (Gmail)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password-16-chars
SMTP_FROM_EMAIL=your-email@gmail.com

# Telegram (optional but recommended)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_CHAT_ID=your-chat-id

# Database
DATABASE_URL=sqlite+aiosqlite:///./forex_license.db
```

**Save**: Press `Ctrl+X`, then `Y`, then `Enter`

---

## 5️⃣ Verify Deployment

```bash
# Check if containers running
docker-compose ps

# View logs
docker-compose logs -f license-server

# Test API
curl http://localhost:8000/docs

# Check database
docker-compose exec license-server ls -la forex_license.db
```

---

## 6️⃣ Setup Domain + SSL (Optional but Recommended)

### **Buy Domain:**
- Go to namecheap.com or godaddy.com
- Buy domain (e.g., `your-domain.com`)

### **Point to VPS:**
1. Go to domain DNS settings
2. Add A record:
   - Name: `@`
   - Value: `your_vps_ip_address`
3. Wait 5-10 minutes for DNS to propagate

### **Setup SSL Certificate:**

```bash
# Install certbot
apt-get install -y nginx certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d your-domain.com

# Auto-renew
systemctl enable certbot.timer
```

**Result**: Your API is now at `https://your-domain.com` ✅

---

## 7️⃣ Test Bot Connection

### **From your laptop/bot client:**

```python
# In bot client config
SERVER_URL = "https://your-domain.com"  # Or http://vps_ip:8000

# Test verify
import httpx
response = httpx.post(
    f"{SERVER_URL}/bot/verify",
    json={"license_key": "TEST_KEY"}
)
print(response.json())
```

---

## 8️⃣ Monitoring & Maintenance

### **View Real-time Logs:**
```bash
docker-compose logs -f license-server

# Filter by level
docker-compose logs -f --tail=100 license-server | grep ERROR
```

### **Check System Resources:**
```bash
docker stats
docker ps
df -h  # Disk usage
free -h  # Memory
```

### **Restart Services:**
```bash
docker-compose restart
```

### **Backup Database:**
```bash
# Manual backup
docker-compose exec license-server python -c "
from pathlib import Path
from core.backup import DatabaseBackup
import asyncio
backup = DatabaseBackup(Path('forex_license.db'))
asyncio.run(backup.create_backup(compress=True))
"

# Check backups
docker-compose exec license-server ls -la backups/
```

### **Update Code:**
```bash
# Pull latest
git pull origin main

# Rebuild
docker-compose build --no-cache

# Restart
docker-compose up -d

# Verify
docker-compose logs -f license-server
```

---

## 9️⃣ Setup Monitoring (Auto Restarts)

### **Enable Auto-Restart:**

```bash
# Create systemd service
sudo nano /etc/systemd/system/forex-bot.service
```

Paste:
```ini
[Unit]
Description=Forex Bot License Server (Docker)
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/root/forex_bot_system/forex_bot
ExecStart=/usr/local/bin/docker-compose up
ExecStop=/usr/local/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable forex-bot
sudo systemctl start forex-bot
```

---

## 🔟 Troubleshooting

### **Container won't start:**
```bash
docker-compose logs license-server
docker-compose down
docker-compose up --build
```

### **Port already in use:**
```bash
lsof -i :8000
# Kill process or use different port
```

### **Database locked:**
```bash
docker-compose exec license-server sqlite3 forex_license.db "PRAGMA journal_mode=WAL;"
```

### **SMTP not working:**
```bash
# Test email
docker-compose exec license-server python -c "
import asyncio
from core.email_utils import send_code_email
asyncio.run(send_code_email('test@example.com', '123456', 'user_login'))
"
```

### **Can't SSH:**
```bash
# Reset root password via DigitalOcean console
# Or use "Access Console" button in DigitalOcean dashboard
```

---

## 📊 After Deployment Checklist

- [ ] VPS deployed with Docker
- [ ] `.env` configured (SMTP, Telegram, etc.)
- [ ] Database initialized
- [ ] Can access `/docs` at http://your-vps-ip:8000
- [ ] Admin dashboard at http://your-vps-ip:8000/dashboard
- [ ] Bot can verify license: POST `/bot/verify`
- [ ] Email OTP working
- [ ] Telegram alerts configured
- [ ] Backups running daily
- [ ] SSL certificate setup (optional)
- [ ] Domain pointing to VPS (optional)
- [ ] Monitoring logs working

---

## 🎯 Testing Bot Connection from Your Machine

Create `test_bot_connection.py`:

```python
import httpx
import json

SERVER_URL = "http://your_vps_ip:8000"  # or https://your-domain.com

# Test verify endpoint
response = httpx.post(
    f"{SERVER_URL}/bot/verify",
    json={
        "license_key": "TEST_LICENSE_KEY_123",
        "mt_account": "12345678",
        "hosted_runner": False
    }
)

print("Status:", response.status_code)
print("Response:", json.dumps(response.json(), indent=2))

# If status 200: ✅ Connection works!
# If error: Check server logs with "docker-compose logs -f"
```

Run:
```bash
python test_bot_connection.py
```

---

## 💡 Pro Tips

1. **Automatic backups**: Already setup daily in `core/backup.py`
2. **Monitoring**: Check `docker stats` to see resource usage
3. **Scaling**: Can upgrade VPS anytime if needed
4. **Database**: Switch to PostgreSQL if need more reliability
5. **CI/CD**: Setup GitHub Actions for auto-deploy on push

---

## 🆘 Need Help?

Check logs:
```bash
docker-compose logs license-server
tail -f logs/errors_*.log
```

---

**Status**: 🟢 Your bot is now running 24/7 on VPS! 🚀
