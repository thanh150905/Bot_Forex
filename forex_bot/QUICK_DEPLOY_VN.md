# 🚀 Deploy Nhanh - Hướng Dẫn Từng Bước (Tiếng Việt)

## ✅ CÁCH DEPLOY NHANH NHẤT (5 PHÚT) - Railway

### Bước 1: Chuẩn Bị GitHub

```bash
# Mở PowerShell/Terminal ở thư mục: forex_bot_system/forex_bot

# 1. Khởi tạo Git
git init
git add .
git commit -m "Forex Bot v1.0 - Initial"

# 2. Thêm remote (thay YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/forex_bot_system.git
git branch -M main
git push -u origin main
```

### Bước 2: Deploy Lên Railway (FREE)

**Truy cập:** https://railway.app

1. **Đăng nhập bằng GitHub** (Click "Sign in with GitHub")
2. **Cấp quyền** cho Railway truy cập GitHub
3. **Click "Create New Project"**
4. **Chọn "Deploy from GitHub"**
5. **Chọn repo: `forex_bot_system`**
6. **Railway tự build & deploy** (chờ 2-3 phút)
7. **Nhập biến môi trường (Environment Variables):**

   Click "Add variables" và thêm:
   ```
   SECRET_KEY=abcdef1234567890abcdef1234567890abcdef1234567890abcdef12
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=YourSecurePassword123!
   PORT=8000
   ```

8. **Chờ Deploy xong!**

### Bước 3: Kiểm Tra Ứng Dụng

- **Dashboard:** https://your-project.railway.app/dashboard
- **API Docs:** https://your-project.railway.app/docs
- **Health Check:** https://your-project.railway.app/health

✅ **Xong! Ứng dụng chạy trên server miễn phí!**

---

## 💰 So Sánh Chi Phí - FREE Providers

| Dịch vụ | Chi phí | Dễ dùng | Link |
|---------|--------|---------|------|
| **Railway** ⭐ | FREE | ⭐⭐⭐⭐⭐ | https://railway.app |
| **Render** | FREE | ⭐⭐⭐⭐ | https://render.com |
| **Fly.io** | FREE | ⭐⭐⭐⭐ | https://fly.io |
| **Oracle Cloud** | FREE ∞ | ⭐⭐⭐ | https://oracle.com/cloud/free |

---

## 🔥 CÁCH 2: Render (Nếu Railway chậm)

### Bước 1-2: Tương tự Railway

Commit & push lên GitHub

### Bước 3: Deploy Render

1. **Vào:** https://render.com
2. **Đăng nhập GitHub**
3. **Click "New" → "Web Service"**
4. **Connect GitHub repo**
5. **Chọn "Docker"** (không phải Node/Python)
6. **Build & Deploy** (Render sẽ tự tìm `Dockerfile`)

✅ Deploy xong sau 5-10 phút!

---

## 🚀 CÁCH 3: Fly.io (Performance tốt)

```bash
# 1. Cài Fly CLI
iwr https://fly.io/install.ps1 -useb | iex

# 2. Đăng nhập
flyctl auth login

# 3. Launch app
cd forex_bot_system/forex_bot
flyctl launch

# Chọn:
# - App name: forex-bot-api
# - Region: Singapore (sgp)
# - Deploy now: Yes

# 4. Check app
flyctl logs
```

✅ App chạy trên https://forex-bot-api.fly.dev

---

## 💪 CÁCH 4: Oracle Cloud (FREE ∞ - Mãi mãi không tính phí)

### Ưu điểm:
- ✅ **FREE FOREVER** (không bao giờ tính phí)
- ✅ 2 vCPU, 12GB RAM (rất mạnh)
- ✅ 200GB Storage
- ✅ Thích hợp cho bot chạy 24/7

### Bước 1: Tạo Account

1. Vào: https://www.oracle.com/cloud/free
2. Đăng ký (cần thẻ tín dụng để verify, nhưng không bao giờ tính phí)
3. Chọn Region: **Singapore** hoặc **Tokyo**

### Bước 2: Tạo Server

Vào Oracle Cloud Console:
1. **Click "Create Instances"**
2. **Chọn:**
   - Image: **Ubuntu 22.04 LTS** (Always Free)
   - Shape: **Ampere (ARM)** (Free tier)
3. **Download SSH key**
4. **Click "Create"** (chờ 1-2 phút)

### Bước 3: SSH vào Server

```bash
# Windows PowerShell
ssh -i your_key.key ubuntu@your_instance_ip

# Mac/Linux Terminal
ssh -i your_key.key ubuntu@your_instance_ip
```

### Bước 4: Setup Docker

```bash
# Update
sudo apt-get update && sudo apt-get upgrade -y

# Cài Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add permission
sudo usermod -aG docker $USER

# Cài Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Bước 5: Deploy

```bash
# Clone code
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/forex_bot_system.git
cd forex_bot_system/forex_bot

# Tạo .env
nano .env
# Paste:
SECRET_KEY=abcdef1234567890abcdef1234567890abcdef1234567890abcdef12
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123!
PORT=8000

# Ctrl+X → Y → Enter để lưu

# Start app
docker-compose up -d

# Check logs
docker-compose logs -f license-server
```

### Bước 6: Mở Firewall

1. Vào Oracle Cloud Console
2. **Instances → Security Lists**
3. **Thêm Rule:**
   - Protocol: **TCP**
   - Destination Port: **8000**
   - Source: **0.0.0.0/0**
4. **Click "Add Ingress Rule"**

### Bước 7: Truy Cập

```
Dashboard: http://your_server_ip:8000/dashboard
API Docs: http://your_server_ip:8000/docs
```

✅ **App chạy 24/7 miễn phí ∞**

---

## 📋 Checklist Trước Deploy

- [ ] Push code lên GitHub
- [ ] Kiểm tra `.env` không được commit
- [ ] Thêm `.env` vào `.gitignore`
- [ ] Tạo `SECRET_KEY` ngẫu nhiên (64 ký tự)
- [ ] Thay `ADMIN_PASSWORD` thành mật khẩu mạnh
- [ ] Thêm biến môi trường trên platform (UI hoặc CLI)
- [ ] Test app sau khi deploy: `/health` endpoint
- [ ] Kiểm tra logs nếu có lỗi

---

## 🔑 Tạo SECRET_KEY Ngẫu Nhiên

### Cách 1: Python (Dễ nhất)

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Cách 2: Online

Vào: https://randomkeygen.com → Copy "Fort Knox Password"

### Cách 3: CLI

```bash
# Linux/Mac
openssl rand -hex 32

# Windows PowerShell
[System.Convert]::ToBase64String((1..32|ForEach-Object{[byte](Get-Random -Max 256)}))
```

---

## ⚡ Nếu Có Lỗi

### App crash/restart liên tục

```bash
# Xem logs
docker-compose logs license-server -f

# Restart
docker-compose restart license-server

# Stop all
docker-compose down
```

### Database lỗi

```bash
# Enter container
docker exec -it forex-bot-license-server bash

# Reset DB
python -c "from core.database import init_db; import asyncio; asyncio.run(init_db())"
exit
```

### Lỗi build trên Railway/Render

1. Kiểm tra `Dockerfile` có valid không
2. Xem **Build logs** trên UI (Render/Railway Dashboard)
3. Kiểm tra `requirements.txt` có syntax đúng không

---

## 🎯 Tối Ưu Hóa FREE Tier

### Giảm RAM/CPU sử dụng

Chỉnh trong `docker-compose.yml`:

```yaml
services:
  license-server:
    # ... other config ...
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
        reservations:
          cpus: '0.25'
          memory: 128M
```

### Giảm Database size

```bash
# Xóa logs cũ
rm license_server/logs/*.log

# Xóa backups cũ
rm license_server/backups/*.backup.css
```

### Giảm Docker image size

Sử dụng `Dockerfile.slim` thay vì `Dockerfile`:

```bash
docker build -f Dockerfile.slim -t forex-bot:latest .
# Image size: ~200MB (thay vì ~900MB)
```

---

## 📱 Lệnh Hữu Ích

```bash
# Test local
docker-compose up -d
curl http://localhost:8000/health

# Xem logs real-time
docker-compose logs -f license-server

# Restart service
docker-compose restart license-server

# Stop all
docker-compose down

# Remove volumes (cleanup)
docker-compose down -v

# SSH vào container
docker exec -it forex-bot-license-server bash
```

---

## 🆘 Hỗ Trợ

- **Railway Support**: https://support.railway.app
- **Render Docs**: https://render.com/docs
- **Fly.io Community**: https://community.fly.io
- **Oracle Cloud Docs**: https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/qs_overview.htm

---

## ✨ Pro Tips

1. **Setup DNS riêng** (tùy chọn):
   - Railway/Render/Fly.io đều hỗ trợ custom domain FREE
   - Chỉ cần trỏ domain CNAME về app

2. **Enable auto-deploy**:
   - Kết nối GitHub
   - Mỗi lần push → tự động deploy (5-10 phút)

3. **Backup database**:
   ```bash
   docker exec forex-bot-license-server cp forex_license.db /app/backups/$(date +%s).db.backup
   ```

4. **Monitor logs từ xa**:
   - Railway: Real-time logs ở Dashboard
   - Render: Logs tab
   - Fly.io: `flyctl logs`

---

**🎉 Chúc mừng! Bạn đã sẵn sàng deploy ứng dụng Forex Bot lên server!**

**Chọn 1 provider và bắt đầu ngay!** ⚡

