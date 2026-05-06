"""
Forex Bot - License Server
FastAPI + SQLite | Admin quản lý user, IP lock, JWT auth
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from contextlib import asynccontextmanager

from api.routes_admin import router as admin_router
from api.routes_auth  import router as auth_router
from api.routes_ai    import router as ai_router
from api.routes_bot   import router as bot_router
from api.routes_user  import router as user_router
from core.database    import init_db
from core.config      import settings
from core.logger      import app_logger
from core.error_handlers import ErrorHandlingMiddleware

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app_logger.info(f"✅ License server started on port {settings.PORT}")
    app_logger.info(f"Dashboard: http://localhost:{settings.PORT}/dashboard")
    app_logger.info(f"API docs: http://localhost:{settings.PORT}/docs")
    print(f"[SERVER] License server started on port {settings.PORT}")
    print(f"[SERVER] Admin dashboard: http://localhost:{settings.PORT}/dashboard")
    print(f"[SERVER] API docs: http://localhost:{settings.PORT}/docs")
    yield
    app_logger.info("Server shutting down...")
    print("[SERVER] Shutting down...")


app = FastAPI(
    title="Forex Bot License Server",
    version="1.0.0",
    description="Hệ thống quản lý license, IP lock và xác thực bot",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ErrorHandlingMiddleware)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth_router,  prefix="/auth",  tags=["Authentication"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(bot_router,   prefix="/bot",   tags=["Bot Verification"])
app.include_router(ai_router,    prefix="/ai",    tags=["AI Engine"])
app.include_router(user_router,  prefix="/user",  tags=["User Portal"])


@app.get("/", include_in_schema=False)
async def root_dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/user", include_in_schema=False)
async def user_portal_page():
    return FileResponse(STATIC_DIR / "user.html")


@app.get("/portal", include_in_schema=False)
async def portal_page():
    return FileResponse(STATIC_DIR / "user.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "forex-license-server"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=False)
