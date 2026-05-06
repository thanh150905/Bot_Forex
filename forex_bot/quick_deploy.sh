#!/bin/bash
# Quick deployment script for Railway, Render, Fly.io
# Usage: ./quick_deploy.sh

set -e

echo "🚀 Forex Bot - Quick Deploy Script"
echo "===================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if in correct directory
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}Error: Dockerfile not found!${NC}"
    echo "Please run this script from: forex_bot_system/forex_bot/"
    exit 1
fi

# Menu
echo "Choose deployment platform:"
echo "1) Railway (Easiest - ⭐⭐⭐⭐⭐)"
echo "2) Render"
echo "3) Fly.io"
echo "4) Oracle Cloud"
echo "5) Just prepare files (no deploy)"
echo ""
read -p "Enter choice (1-5): " choice

# Function: Generate SECRET_KEY
generate_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))"
}

# Function: Create .env file
create_env() {
    if [ -f ".env" ]; then
        echo -e "${YELLOW}⚠️  .env already exists, skipping...${NC}"
        return
    fi
    
    echo -e "${GREEN}📝 Creating .env file...${NC}"
    
    SECRET=$(generate_secret)
    
    cat > .env << EOF
# Forex Bot Configuration
PORT=8000
SECRET_KEY=$SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@2024!Strong
DATABASE_URL=sqlite+aiosqlite:///./forex_license.db

# Email (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=Forex Bot

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=

# Frontend URL
FRONTEND_URL=https://your-app.railway.app
EOF
    
    echo -e "${GREEN}✅ .env created (check SECRET_KEY!)${NC}"
    echo "SECRET_KEY: $SECRET"
}

# Function: Prepare git
prepare_git() {
    if [ ! -d ".git" ]; then
        echo -e "${GREEN}📝 Initializing Git...${NC}"
        git init
        git add .
        git commit -m "Initial commit - Forex Bot System"
    else
        echo -e "${YELLOW}Git already initialized${NC}"
    fi
}

# Function: Add .gitignore
add_gitignore() {
    if [ ! -f ".gitignore" ]; then
        echo -e "${GREEN}📝 Creating .gitignore...${NC}"
        cat > .gitignore << 'EOF'
.env
.env.local
.env.*.local
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST
venv/
.venv/
ENV/
env/
.vscode/
.idea/
*.log
logs/
*.db
forex_license.db
backups/
.DS_Store
.pytest_cache/
.coverage
EOF
        echo -e "${GREEN}✅ .gitignore created${NC}"
    fi
}

# Choice handler
case $choice in
    1)
        echo -e "\n${YELLOW}🚀 Railway Deployment${NC}"
        create_env
        prepare_git
        add_gitignore
        
        echo ""
        echo -e "${GREEN}✅ Files prepared!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Push to GitHub:"
        echo "   git remote add origin https://github.com/YOUR_USERNAME/forex_bot_system.git"
        echo "   git branch -M main"
        echo "   git push -u origin main"
        echo ""
        echo "2. Go to https://railway.app"
        echo "3. Connect GitHub and deploy!"
        echo ""
        ;;
        
    2)
        echo -e "\n${YELLOW}🚀 Render Deployment${NC}"
        create_env
        prepare_git
        add_gitignore
        
        echo ""
        echo -e "${GREEN}✅ Files prepared!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Create render.yaml (will be created for you)"
        
        cat > render.yaml << 'EOF'
services:
  - type: web
    name: forex-bot-api
    env: docker
    dockerfilePath: ./Dockerfile
    region: singapore
    
    envVars:
      - key: SECRET_KEY
        fromFile: .env
      - key: ADMIN_PASSWORD
        fromFile: .env
      - key: PORT
        value: "8000"
EOF
        
        echo ""
        echo "2. Push to GitHub"
        echo "3. Go to https://render.com"
        echo "4. Connect GitHub and deploy!"
        echo ""
        ;;
        
    3)
        echo -e "\n${YELLOW}🚀 Fly.io Deployment${NC}"
        create_env
        prepare_git
        add_gitignore
        
        echo ""
        echo -e "${GREEN}✅ Files prepared!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Install Fly CLI: https://fly.io/docs/getting-started/installing-flyctl/"
        echo "2. Run: flyctl auth login"
        echo "3. Run: flyctl launch"
        echo "4. Choose region: Singapore"
        echo "5. Set secrets: flyctl secrets set --from-file .env"
        echo ""
        ;;
        
    4)
        echo -e "\n${YELLOW}🚀 Oracle Cloud Deployment${NC}"
        create_env
        
        echo ""
        echo -e "${GREEN}✅ .env created!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Create Oracle Cloud account: https://www.oracle.com/cloud/free"
        echo "2. Launch Ubuntu 22.04 LTS instance"
        echo "3. SSH into instance"
        echo "4. Run these commands:"
        echo ""
        echo "   curl -fsSL https://get.docker.com | sh"
        echo "   sudo usermod -aG docker \$USER"
        echo "   git clone YOUR_REPO_URL"
        echo "   cd forex_bot_system/forex_bot"
        echo "   docker-compose up -d"
        echo ""
        echo "5. Allow port 8000 in Oracle Cloud security rules"
        echo ""
        ;;
        
    5)
        echo -e "\n${YELLOW}📦 Preparing files (no deploy)${NC}"
        create_env
        prepare_git
        add_gitignore
        
        echo ""
        echo -e "${GREEN}✅ Files prepared!${NC}"
        echo ""
        echo "Your project is ready. You can:"
        echo "- Push to GitHub and deploy manually"
        echo "- Test locally: docker-compose up"
        echo ""
        ;;
        
    *)
        echo -e "${RED}Invalid choice!${NC}"
        exit 1
        ;;
esac

echo -e "${GREEN}Done! 🎉${NC}"
