#!/usr/bin/env python3
"""
Quick VPS Setup Helper - Interactive configuration
Run: python3 setup_vps.py
"""

import os
import sys
import subprocess
from pathlib import Path


def run_command(cmd, description=""):
    """Run shell command and handle errors"""
    if description:
        print(f"\n📝 {description}")
        print(f"$ {cmd}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return False
    
    if result.stdout:
        print(result.stdout)
    return True


def generate_secret_key():
    """Generate a secure SECRET_KEY"""
    import secrets
    return secrets.token_hex(32)


def main():
    print("=" * 60)
    print("🚀 Forex Bot VPS Setup Helper")
    print("=" * 60)
    
    # Check if Docker is installed
    print("\n🔍 Checking prerequisites...")
    
    docker_installed = run_command("docker --version", "✓ Checking Docker")
    if not docker_installed:
        print("❌ Docker not installed!")
        print("Run: curl -fsSL https://get.docker.com | sh")
        sys.exit(1)
    
    # Create .env file
    env_path = Path(".env")
    if env_path.exists():
        print("\n⚠️  .env already exists")
        response = input("Overwrite? (y/n): ").lower()
        if response != 'y':
            print("Keeping existing .env")
            return
    
    print("\n📋 Creating .env configuration...")
    
    # Get user inputs
    secret_key = generate_secret_key()
    admin_password = input("Admin password (default: Admin@2024!Strong): ").strip() or "Admin@2024!Strong"
    
    print("\n📧 SMTP Configuration (for email OTP):")
    smtp_host = input("SMTP Host (default: smtp.gmail.com): ").strip() or "smtp.gmail.com"
    smtp_port = input("SMTP Port (default: 587): ").strip() or "587"
    smtp_username = input("SMTP Username (your email): ").strip() or ""
    smtp_password = input("SMTP Password (App Password for Gmail): ").strip() or ""
    smtp_from_email = input("From Email (default: same as username): ").strip() or smtp_username
    
    print("\n🤖 Telegram Configuration (optional for alerts):")
    telegram_token = input("Telegram Bot Token (leave empty to skip): ").strip() or ""
    telegram_chat_id = input("Telegram Admin Chat ID (leave empty to skip): ").strip() or ""
    
    print("\n🌐 Frontend Configuration:")
    frontend_url = input("Frontend URL (default: https://your-domain.com): ").strip() or "https://your-domain.com"
    
    # Generate .env content
    env_content = f"""# ═════════════════════════════════════════════════════════════════════════════════
# Forex Bot License Server - Configuration
# Generated: {Path('.env').read_text() if Path('.env').exists() else 'New'}
# ═════════════════════════════════════════════════════════════════════════════════

# ─── Server Configuration ─────────────────────────────────────────────────────
PORT=8000
SECRET_KEY={secret_key}
DATABASE_URL=sqlite+aiosqlite:///./forex_license.db

# ─── Admin Credentials ────────────────────────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD={admin_password}

# ─── SMTP Configuration ───────────────────────────────────────────────────────
SMTP_HOST={smtp_host}
SMTP_PORT={smtp_port}
SMTP_USERNAME={smtp_username}
SMTP_PASSWORD={smtp_password}
SMTP_FROM_EMAIL={smtp_from_email}
SMTP_FROM_NAME=Forex Bot
SMTP_USE_TLS=true
SMTP_USE_SSL=false

EMAIL_CODE_EXPIRE_MINUTES=10
EMAIL_CODE_RESEND_SECONDS=60
EMAIL_CODE_MAX_ATTEMPTS=5

# ─── Telegram Notifications ────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN={telegram_token}
TELEGRAM_ADMIN_CHAT_ID={telegram_chat_id}

# ─── Frontend/CORS ─────────────────────────────────────────────────────────────
FRONTEND_URL={frontend_url}

# ─── Rate Limiting ──────────────────────────────────────────────────────────────
MAX_REQUESTS_PER_MINUTE=100
BOT_PING_INTERVAL_SECONDS=300
BOT_PING_TIMEOUT_SECONDS=600
"""
    
    # Write .env
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"\n✅ .env created at {env_path}")
    
    # Build Docker image
    print("\n🐳 Building Docker image...")
    if not run_command("docker build -t forex-bot:latest -f Dockerfile .", "Building Docker image"):
        print("❌ Docker build failed!")
        sys.exit(1)
    
    # Start services
    print("\n🚀 Starting services...")
    if not run_command("docker-compose up -d", "Starting Docker Compose"):
        print("❌ Failed to start services!")
        sys.exit(1)
    
    # Verify
    print("\n✅ Deployment Complete!")
    print("\n📊 Services Status:")
    run_command("docker-compose ps", "Checking containers")
    
    print("\n📖 Next Steps:")
    print("1. View logs: docker-compose logs -f license-server")
    print("2. Access API: http://localhost:8000/docs")
    print("3. Admin dashboard: http://localhost:8000/dashboard")
    print("4. Setup domain (optional): See VPS_SETUP.md")
    
    print("\n💾 Configuration saved to: .env")
    print("🔒 Keep this file secure!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Setup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
