# 📦 Hướng Dẫn Đóng Gói & Deploy Lên Server FREE (Không Mất Tiền)

> **Cập nhật: Tháng 5 2026**  
> Hướng dẫn này hỗ trợ deploy Backend (FastAPI) + Frontend (Static Files) mà **không tốn tiền** hoặc tối thiểu hóa chi phí.

---

## 🎯 Các Lựa Chọn Deploy FREE (2026)

| Provider | Storage | Compute | Uptime | Dễ Dùng | Link |
|----------|---------|---------|--------|---------|------|
| **Railway** | 5GB | CPU Shared | 99% | ⭐⭐⭐⭐⭐ | https://railway.app |
| **Render** | 100GB | CPU Shared | 99.95% | ⭐⭐⭐⭐ | https://render.com |
| **Fly.io** | 10GB | CPU Shared | 99.99% | ⭐⭐⭐⭐ | https://fly.io |
| **Oracle Cloud** | 200GB | 1 vCPU (Always Free) | 99% | ⭐⭐⭐ | https://oracle.com/cloud/free |
| **Replit** | 5GB | CPU Shared | 99% | ⭐⭐⭐⭐ | https://replit.com |

---

## ⚡ CÁCH 1: Railway (Dễ nhất - 5 phút) ⭐

### Bước 1: Chuẩn Bị File

```bash
# Di chuyển vào thư mục dự án
cd forex_bot_system/forex_bot

# Kiểm tra cấu trúc
ls -la
# Cần có: Dockerfile, docker-compose.yml, license_server/
```

### Bước 2: Setup Git

```bash
# Khởi tạo Git (nếu chưa có)
git init
git add .
git commit -m "Initial commit - Forex Bot System"

# Đẩy lên GitHub (cần tài khoản GitHub)
git remote add origin https://github.com/YOUR_USERNAME/forex_bot_system.git
git branch -M main
git push -u origin main
```

### Bước 3: Deploy Lên Railway

1. **Vào https://railway.app**
2. **Đăng nhập với GitHub** (click "Sign In with GitHub")
3. **Cấp quyền truy cập repo**
4. **Click "Create New Project"**
5. **Chọn "Deploy from GitHub"**
6. **Chọn repo: `forex_bot_system`**
7. **Chọn "Add variables"** và thêm `.env`:

```env
SECRET_KEY=your_random_64_char_string_here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your_app_password
TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_ADMIN_CHAT_ID=your_chat_id
FRONTEND_URL=https://your-app.railway.app
```

8. **Click "Deploy"** → Chờ 2-3 phút

### Bước 4: Kiểm Tra

```bash
# Truy cập vào
Dashboard: https://your-app.railway.app/dashboard
API Docs: https://your-app.railway.app/docs
```

✅ **Xong!** Ứng dụng đã chạy trên server miễn phí!

---

## ⚡ CÁCH 2: Render (Stable - 8 phút)

### Bước 1: Chuẩn Bị

```bash
# Tương tự Railway - commit code lên GitHub
cd forex_bot_system/forex_bot
git push origin main
```

### Bước 2: Tạo file `render.yaml` trong thư mục gốc:

```yaml
services:
  - type: web
    name: forex-bot-api
    env: docker
    dockerfilePath: ./Dockerfile
    
    envVars:
      - key: SECRET_KEY
        value: your_random_64_char_string_here
      - key: ADMIN_USERNAME
        value: admin
      - key: ADMIN_PASSWORD
        value: YourSecurePassword123
      - key: PORT
        value: 8000
```

### Bước 3: Deploy

1. **Vào https://render.com**
2. **Đăng nhập với GitHub**
3. **Click "New +"** → **"Web Service"**
4. **Kết nối repo GitHub**
5. **Chọn "Docker"** as environment
6. **Chọn "Free Plan"** (0.50 credits/month)
7. **Click "Create Web Service"**

✅ **Render sẽ tự deploy trong 5-10 phút!**

---

## ⚡ CÁCH 3: Fly.io (Performance - 10 phút)

### Bước 1: Cài App CLI

```bash
# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex

# Mac/Linux
curl -L https://fly.io/install.sh | sh
```

### Bước 2: Login

```bash
flyctl auth login
# Mở browser để authenticate GitHub
```

### Bước 3: Launch

```bash
cd forex_bot_system/forex_bot

# Tạo app trên Fly
flyctl launch

# Chọn:
# - App name: forex-bot-api
# - Region: Singapore (sgp) hoặc Tokyo (nrt)
# - Database: No
# - Deploy now: Yes
```

### Bước 4: Set Environment Variables

```bash
flyctl secrets set SECRET_KEY="your_random_64_char_string"
flyctl secrets set ADMIN_PASSWORD="YourSecurePassword123"
```

### Bước 5: Kiểm Tra

```bash
# Xem logs
flyctl logs

# Truy cập
https://forex-bot-api.fly.dev/docs
```

---

## ⚡ CÁCH 4: Oracle Cloud Free Tier (Permanent FREE)

**Lợi ích:**
- ✅ Always Free (không bao giờ tính phí)
- ✅ 2 vCPU, 12GB RAM
- ✅ 200GB Storage
- ✅ 10TB Data transfer/month

### Bước 1: Tạo Account

1. Vào https://www.oracle.com/cloud/free
2. Đăng ký account (cần thẻ tín dụng để verify, nhưng không tính phí)
3. Chọn Region: **Singapore** hoặc **Tokyo**

### Bước 2: Launch Compute Instance

```
1. Vào Oracle Cloud Console
2. Click "Create Instances"
3. Chọn:
   - Image: Ubuntu 22.04 LTS (Always Free eligible)
   - Shape: Ampere (ARM) - Free tier
   - SSH Key: Download & lưu file
4. Click "Create"
```

### Bước 3: SSH vào Server

```bash
# Windows (PowerShell) hoặc Mac/Linux Terminal
ssh -i your_key.key ubuntu@your_instance_ip

# Nếu bị Permission denied, fix key:
chmod 600 your_key.key
```

### Bước 4: Setup Docker

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Bước 5: Deploy Ứng Dụng

```bash
# Clone repo
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/forex_bot_system.git
cd forex_bot_system/forex_bot

# Tạo .env file
nano .env
# Thêm:
SECRET_KEY=your_random_64_char_string
ADMIN_PASSWORD=YourSecurePassword123
# ... các config khác

# Start với Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f license-server
```

### Bước 6: Cấu Hình Firewall

```bash
# Mở port 8000 trên Oracle Cloud Console
# Vào Instance → VCN → Security Lists
# Thêm Ingress Rule:
#   - Protocol: TCP
#   - Port: 8000
#   - Source: 0.0.0.0/0
```

✅ **Ứng dụng sẽ chạy forever miễn phí!**

---

## 📦 CÁCH 5: Đóng Gói Tối Ưu (Giảm Size)

### Bước 1: Tạo `.dockerignore`

```bash
# forex_bot_system/forex_bot/.dockerignore
.git
.github
.env.example
README.md
*.md
.pytest_cache
__pycache__
*.pyc
*.egg-info
dist/
build/
logs/*
*.log
backups/*
node_modules/
.venv/
venv/
```

### Bước 2: Tối ưu Dockerfile

```dockerfile
FROM python:3.12-slim-alpine

WORKDIR /app

RUN apk add --no-cache curl gcc musl-dev

COPY license_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY license_server/ .

RUN mkdir -p logs backups

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000

CMD ["python", "main.py"]
```

**Size so sánh:**
- Dockerfile cũ: ~900MB
- Dockerfile tối ưu: ~200MB ⚡

### Bước 3: Xây dựng Image

```bash
# Build image
docker build -t forex-bot:latest .

# Kiểm tra size
docker images | grep forex-bot

# Test local
docker run -d -p 8000:8000 forex-bot:latest
# Truy cập: http://localhost:8000/docs
```

---

## 🔐 Bảo Mật - Checklist Trước Deploy

- [ ] Thay `SECRET_KEY` thành 64 ký tự ngẫu nhiên
- [ ] Thay `ADMIN_PASSWORD` thành mật khẩu mạnh (>12 ký tự)
- [ ] Bật SSL/HTTPS (hầu hết provider đều free)
- [ ] Thêm `.env` vào `.gitignore`
- [ ] Không commit `.env` lên GitHub
- [ ] Đặt biến env trực tiếp trên provider (UI hoặc CLI)

### Tạo Secret Key

```bash
# Python
python -c "import secrets; print(secrets.token_hex(32))"

# Result: 5f8c9e2a1b3d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d
```

---

## 📊 So Sánh Chi Phí

| Giải pháp | Chi phí/tháng | Uptime | Dễ setup | Ghi chú |
|-----------|---------------|--------|----------|---------|
| Railway | **Free** (5GB) | 99% | ⭐⭐⭐⭐⭐ | Dễ nhất |
| Render | **Free** | 99.95% | ⭐⭐⭐⭐ | Ổn định |
| Fly.io | **Free** | 99.99% | ⭐⭐⭐⭐ | Perform tốt |
| Oracle Cloud | **Free mãi mãi** | 99% | ⭐⭐⭐ | Setup phức tạp hơn |
| DigitalOcean | $5/tháng | 99% | ⭐⭐⭐⭐ | Nếu có budget |

---

## 🚀 Git Workflow - Deploy Tự Động

### Cấu hình GitHub Actions (tự động deploy)

Tạo file `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Railway

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to Railway
        run: |
          npm install -g @railway/cli
          railway up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

**Setup:**
1. Vào GitHub → Settings → Secrets
2. Thêm `RAILWAY_TOKEN` từ Railway dashboard
3. Lần tới push code → tự động deploy! 🚀

---

## 📱 Lệnh Nhanh

### Railway Deploy

```bash
# Sau khi connect GitHub trên Railway UI
git push origin main
# ✅ Tự động deploy trong 2-3 phút
```

### Fly.io Deploy

```bash
flyctl deploy
```

### Docker Local Test

```bash
docker build -t forex-bot:latest .
docker run -d -p 8000:8000 -e SECRET_KEY=test123 forex-bot:latest
curl http://localhost:8000/health
```

---

## 🆘 Troubleshoot

### Build thất bại trên Railway

```bash
# Kiểm tra Dockerfile syntax
docker build -t test . 2>&1 | head -20

# Xem logs chi tiết trên Railway UI
# Deployment → View logs
```

### Database lỗi sau deploy

```bash
# SSH vào server
ssh ubuntu@server_ip

# Enter container
docker exec -it forex-bot-license-server bash

# Reset database
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"
exit
```

### App crash/restart liên tục

```bash
# Check logs
docker-compose logs license-server

# Kiểm tra environment variables
docker-compose config | grep SECRET_KEY

# Restart service
docker-compose restart license-server
```

---

## 📚 Resources Thêm

- **Railway Docs**: https://docs.railway.app
- **Render Docs**: https://render.com/docs
- **Fly.io Docs**: https://fly.io/docs
- **Oracle Cloud Free**: https://oracle.com/cloud/free
- **Docker Best Practices**: https://docs.docker.com/develop/dev-best-practices

---

## ✅ Checklist Hoàn Thành

- [ ] Commit code lên GitHub
- [ ] Chọn 1 provider (Railway/Render/Fly.io/Oracle)
- [ ] Follow bước deploy tương ứng
- [ ] Test API: https://your-app/docs
- [ ] Test Dashboard: https://your-app/dashboard
- [ ] Cấu hình domain riêng (tùy chọn)
- [ ] Setup monitoring alerts

---

**Chúc mừng! 🎉 Ứng dụng của bạn đã sẵn sàng deploy lên server miễn phí!**

