# 📦 Tổng Hợp File Deploy & Hướng Dẫn

> Cập nhật: Tháng 5 2026

## 📄 File Tài Liệu Được Tạo

| File | Mô Tả | Sử Dụng |
|------|-------|--------|
| **QUICK_DEPLOY_VN.md** | Hướng dẫn deploy nhanh (Tiếng Việt) | ⭐⭐⭐ **BẮT ĐẦU TỪ ĐÂY** |
| **FREE_DEPLOYMENT_GUIDE.md** | Hướng dẫn chi tiết (Tiếng Anh) | Tham khảo thêm |
| **quick_deploy.sh** | Script tự động setup | `bash quick_deploy.sh` |
| **Dockerfile.slim** | Dockerfile tối ưu (200MB vs 900MB) | Sử dụng cho free tier |
| **render.yaml** | Config cho Render deployment | Deploy Render |
| **railway.json** | Config cho Railway deployment | Deploy Railway |
| **fly.toml** | Config cho Fly.io deployment | Deploy Fly.io |
| **.github/workflows/deploy.yml** | Auto-deploy khi push GitHub | GitHub Actions |

---

## 🚀 NHANH NHẤT: 3 Bước Deploy Railway (5 phút)

### Bước 1: Commit & Push GitHub

```bash
git init
git add .
git commit -m "Forex Bot v1.0"
git remote add origin https://github.com/YOUR_USERNAME/forex_bot_system.git
git branch -M main
git push -u origin main
```

### Bước 2: Vào Railway

Truy cập: **https://railway.app**
- Đăng nhập GitHub
- Click "Create New Project"
- Chọn "Deploy from GitHub"
- Chọn repo

### Bước 3: Thêm Variables

Thêm biến môi trường:
```
SECRET_KEY=abcdef1234567890... (64 ký tự)
ADMIN_PASSWORD=YourPassword123!
```

✅ **Done! App chạy trong 2-3 phút!**

---

## 📊 So Sánh 4 Nhà Cung Cấp FREE

```
┌─────────────┬──────────┬────────┬──────┬────────────────┐
│ Provider    │ Chi phí  │ Dễ dùng│Uptime│ Notes          │
├─────────────┼──────────┼────────┼──────┼────────────────┤
│ Railway ⭐  │ FREE     │ 5/5    │ 99%  │ Dễ nhất        │
│ Render      │ FREE     │ 4/5    │99.95%│ Ổn định        │
│ Fly.io      │ FREE     │ 4/5    │99.99%│ Performance OK │
│ Oracle ∞    │ FREE ∞   │ 3/5    │ 99%  │ Powerful       │
└─────────────┴──────────┴────────┴──────┴────────────────┘
```

---

## 🎯 Chọn Provider Dựa Trên Nhu Cầu

### 🚀 **Muốn deploy nhanh nhất?**
→ **Railway** (5 phút)

### ⚡ **Muốn performance tốt nhất?**
→ **Fly.io** (99.99% uptime)

### 💪 **Muốn server mạnh & free forever?**
→ **Oracle Cloud** (2 vCPU, 12GB RAM, mãi miễn phí)

### 🆓 **Muốn đơn giản & ổn định?**
→ **Render** (free plan, dễ setup)

---

## 📋 Checklist Trước Deploy

```bash
# 1. Kiểm tra file cấu hình
ls -la
# Phải có: Dockerfile, docker-compose.yml, license_server/

# 2. Kiểm tra .env không được tracked
cat .gitignore | grep -i ".env"
# Phải có: .env

# 3. Tạo SECRET_KEY random
python -c "import secrets; print(secrets.token_hex(32))"

# 4. Kiểm tra Dockerfile syntax
docker build -t test . --no-cache

# 5. Commit lên GitHub
git status
git add .
git commit -m "Ready for deployment"
git push origin main
```

---

## 🔧 Lệnh Chạy Nhanh

### Script tự động setup

```bash
bash quick_deploy.sh

# Chọn: 1 (Railway) hoặc 2 (Render) hoặc 3 (Fly.io) hoặc 4 (Oracle)
```

### Test local trước deploy

```bash
# Build Docker image
docker build -f Dockerfile.slim -t forex-bot:latest .

# Chạy container
docker run -d -p 8000:8000 \
  -e SECRET_KEY=test123 \
  -e ADMIN_PASSWORD=test123 \
  forex-bot:latest

# Test
curl http://localhost:8000/health
# Kết quả: {"status":"ok","service":"forex-license-server"}

# Stop
docker stop $(docker ps -q)
```

### Docker Compose

```bash
# Khởi động
docker-compose up -d

# Xem logs
docker-compose logs -f license-server

# Restart service
docker-compose restart license-server

# Stop all
docker-compose down
```

---

## 🌐 Truy Cập Sau Deploy

Sau khi deploy thành công, bạn sẽ có:

```
🔗 Dashboard:    https://your-app.platform.com/dashboard
📚 API Docs:     https://your-app.platform.com/docs
💚 Health Check: https://your-app.platform.com/health
```

**Login credentials:**
- Username: `admin` (hoặc tùy chỉnh)
- Password: Mật khẩu bạn đặt trong `.env`

---

## 🔒 Bảo Mật - PHẢI LÀM

- ✅ Không commit `.env` lên GitHub
- ✅ Tạo `SECRET_KEY` ngẫu nhiên (64 ký tự)
- ✅ Đặt `ADMIN_PASSWORD` mạnh (>12 ký tự)
- ✅ Thêm biến env trên platform UI (không trực tiếp trên code)
- ✅ Enable HTTPS (tất cả platform FREE support)
- ✅ Định kỳ backup database

---

## 🛠️ File Config Có Sẵn

### railway.json (Railway)
```json
{
  "build": {"builder": "dockerfile"},
  "deploy": {"numReplicas": 1}
}
```
→ Railway sẽ tự dùng config này

### render.yaml (Render)
```yaml
services:
  - type: web
    name: forex-bot-api
    env: docker
```
→ Render sẽ tự dùng config này

### fly.toml (Fly.io)
```toml
app = "forex-bot-api"
primary_region = "sgp"
```
→ Fly sẽ tự dùng config này

---

## 🚨 Troubleshoot Thường Gặp

| Lỗi | Nguyên Nhân | Giải Pháp |
|-----|-----------|----------|
| **Build fail** | Dockerfile lỗi | `docker build -t test .` locally |
| **App crash** | RAM hết | Giảm worker processes |
| **Slow startup** | Image quá lớn | Dùng `Dockerfile.slim` |
| **Port conflict** | Port 8000 bị dùng | Thay port trong config |
| **DB error** | SQLite corrupt | Xóa `forex_license.db` → reset |

---

## 📱 Tài Liệu Tham Khảo

- [Railway Docs](https://docs.railway.app)
- [Render Docs](https://render.com/docs)
- [Fly.io Docs](https://fly.io/docs)
- [Oracle Cloud Always Free](https://www.oracle.com/cloud/free)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices)

---

## ✅ Workflow Hoàn Chỉnh

```
1. Code xong
   ↓
2. .env config OK (không commit)
   ↓
3. Push GitHub
   ↓
4. Chọn platform (Railway/Render/Fly.io/Oracle)
   ↓
5. Deploy (platform sẽ auto pull GitHub)
   ↓
6. Chờ build & start (2-10 phút)
   ↓
7. Kiểm tra logs
   ↓
8. Truy cập dashboard
   ↓
9. ✅ DONE! Chạy 24/7 trên server!
```

---

## 🎉 Chúc Mừng!

Bạn đã có hệ thống deploy production-ready, **miễn phí** và **tự động**!

**Bất cứ lúc nào code thay đổi:**
1. `git push origin main`
2. Platform tự động deploy
3. App update trong 5-10 phút

**No more manual deployment! 🚀**

