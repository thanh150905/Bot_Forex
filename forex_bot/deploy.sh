#!/bin/bash
# 🚀 Forex Bot - One-Click VPS Deployment
# Usage: curl -sSL https://your-raw-github-url/deploy.sh | bash

set -e

echo "=========================================="
echo "🚀 Forex Bot System - VPS Deployment"
echo "=========================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

echo -e "${YELLOW}Step 1: Update system packages${NC}"
apt-get update && apt-get upgrade -y

echo -e "${YELLOW}Step 2: Install Docker${NC}"
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

echo -e "${YELLOW}Step 3: Install Docker Compose${NC}"
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

echo -e "${YELLOW}Step 4: Add user to docker group${NC}"
usermod -aG docker $USER

echo -e "${YELLOW}Step 5: Install Git${NC}"
apt-get install -y git

echo -e "${YELLOW}Step 6: Clone repository${NC}"
cd /root
git clone https://github.com/YOUR_GITHUB_USERNAME/forex_bot_system.git || echo "Git clone skipped - repo already exists"
cd forex_bot_system/forex_bot

echo -e "${YELLOW}Step 7: Create .env file${NC}"
if [ ! -f .env ]; then
    cp license_server/.env.example .env
    echo -e "${YELLOW}Please edit .env with your configuration:${NC}"
    echo "nano .env"
    read -p "Press Enter after editing .env... "
else
    echo ".env already exists"
fi

echo -e "${YELLOW}Step 8: Build Docker image${NC}"
docker build -t forex-bot:latest -f Dockerfile .

echo -e "${YELLOW}Step 9: Start services${NC}"
docker-compose up -d

echo -e "${YELLOW}Step 10: Setup systemd service (optional)${NC}"
cat > /etc/systemd/system/forex-bot.service << 'EOF'
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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable forex-bot
echo "Systemd service created"

echo -e "${YELLOW}Step 11: Setup Nginx reverse proxy${NC}"
apt-get install -y nginx certbot python3-certbot-nginx

# Create Nginx config
cat > /etc/nginx/sites-available/forex-bot << 'EOF'
server {
    listen 80;
    server_name _;
    
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
EOF

ln -sf /etc/nginx/sites-available/forex-bot /etc/nginx/sites-enabled/ 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
nginx -t && systemctl restart nginx

echo ""
echo -e "${GREEN}=========================================="
echo "✅ Deployment Complete!"
echo "==========================================${NC}"
echo ""
echo -e "${GREEN}🔗 Access your server:${NC}"
echo "http://$(hostname -I | awk '{print $1}')"
echo ""
echo -e "${GREEN}📋 Useful commands:${NC}"
echo "docker-compose logs -f              # View logs"
echo "docker-compose ps                   # Check status"
echo "docker-compose restart              # Restart"
echo "docker-compose down                 # Stop"
echo ""
echo -e "${GREEN}🔒 Setup SSL (recommended):${NC}"
echo "certbot --nginx -d your-domain.com"
echo ""
echo -e "${GREEN}📊 Monitor:${NC}"
echo "docker stats"
echo ""
