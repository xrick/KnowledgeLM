# main.py
"""
DocAI - RAG Application Main Entry Point

FastAPI application factory with:
- RESTful API routing (/api/v1)
- Legacy compatibility routing (/upload-pdf, /chat)
- Static files serving
- Frontend serving (template/index.html)
- Startup/Shutdown lifecycle management
"""

# MUST be set BEFORE huggingface_hub is imported (constants are frozen at import time).
# Prevents "ModuleNotFoundError: No module named 'hf_transfer'" when shell sets
# HF_HUB_ENABLE_HF_TRANSFER=1 but the package is not installed in this venv.
import os
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import configuration
from app.core.config import settings

# Import API routers
from app.api.v1 import router as api_v1_router

# Import background tasks
from app.SkillServices.background_integrity_checker import start_background_checker

logger = logging.getLogger(__name__)


# =============================================================================
# Lifespan Management
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan management

    Handles:
    - Startup: Database initialization, directory creation
    - Shutdown: Resource cleanup
    """
    # Startup
    logger.info(f"=� Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Create necessary directories
    directories = [
        Path(settings.UPLOAD_DIR),
        Path(settings.PDF_UPLOAD_DIR),
        Path("data"),
        Path("logs"),
        Path("static")
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"=� Ensured directory exists: {directory}")

    # Initialize database tables
    try:
        from app.Providers.file_metadata_provider import get_file_metadata_provider
        file_metadata_provider = await get_file_metadata_provider()
        # Database already initialized by get_file_metadata_provider()
        logger.info("✅ SQLite database provider initialized")
    except Exception as e:
        logger.error(f"L Failed to initialize database: {str(e)}")


    # Check Milvus vector database service availability
    try:
        from app.Providers.vector_store_provider.milvus_client import MilvusClient

        logger.info(f"🔍 Checking Milvus service at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}...")

        milvus_client = MilvusClient()

        if milvus_client.is_service_available():
            logger.info(f"✅ Milvus vector database service is available")
        else:
            logger.warning(
                f"⚠️  Milvus service is not available at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}. "
                "Vector search features may not work properly. "
                "Please ensure Milvus is running (e.g., docker ps | grep milvus)"
            )
    except Exception as e:
        logger.warning(f"⚠️  Milvus health check failed: {str(e)}")
        logger.info("ℹ️  Application will continue, but vector search features may be limited")

    # Start background integrity checker
    try:
        asyncio.create_task(start_background_checker(interval_seconds=3600))
        logger.info("✅ Background integrity checker started (interval: 1 hour)")
    except Exception as e:
        logger.error(f"❌ Failed to start background integrity checker: {str(e)}")
    logger.info(" Application startup complete")

    yield  # Application runs here

    # Shutdown
    logger.info("=� Shutting down application")

    # Close LLM Manager
    try:
        from app.Providers.llm_provider.manager import get_llm_manager
        llm_manager = get_llm_manager()
        await llm_manager.shutdown()
        logger.info("✅ LLM Manager shutdown complete")
    except Exception as e:
        logger.warning(f"⚠️ LLM Manager cleanup warning: {str(e)}")

    # Close database connections
    try:
        from app.Providers.chat_history_provider.client import _chat_history_provider_instance
        if _chat_history_provider_instance:
            await _chat_history_provider_instance.close()
            logger.info(" MongoDB connection closed")
    except Exception as e:
        logger.warning(f"� MongoDB cleanup warning: {str(e)}")

    logger.info(" Application shutdown complete")


# =============================================================================
# Application Factory
# =============================================================================

def create_application() -> FastAPI:
    """
    Create and configure FastAPI application

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="RAG-powered document Q&A system with hierarchical chunking and OPMP streaming",
        lifespan=lifespan,
        debug=settings.DEBUG
    )

    # =============================================================================
    # CORS Middleware
    # =============================================================================
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # =============================================================================
    # Static Files
    # =============================================================================
    # Mount static files directory
    static_dir = Path("static")
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory="static"), name="static")
        logger.info("=� Static files mounted at /static")

    # =============================================================================
    # API Routers - RESTful Architecture
    # =============================================================================
    # Register v1 API router (RESTful: /api/v1/...)
    app.include_router(
        api_v1_router.router,
        prefix="/api"
    )
    logger.info("= RESTful API v1 registered at /api/v1")

    # =============================================================================
    # Legacy Compatibility Routers
    # =============================================================================
    # Import individual endpoint routers for legacy compatibility
    from app.api.v1.endpoints import upload, chat, files

    # Legacy upload endpoint: /upload-pdf/ (frontend compatibility)
    app.include_router(
        upload.router,
        prefix="/upload-pdf",
        tags=["upload-legacy"]
    )
    logger.info("= Legacy upload endpoint registered at /upload-pdf")

    # Legacy chat endpoint: /chat/ (frontend compatibility)
    app.include_router(
        chat.router,
        prefix="/chat",
        tags=["chat-legacy"]
    )
    logger.info("🔌 Legacy chat endpoint registered at /chat")

    # File management endpoints: /api/v1/files (RESTful multi-user support)
    app.include_router(
        files.router,
        prefix="/api/v1",
        tags=["file-management"]
    )
    logger.info("📁 File management endpoints registered at /api/v1/files")

    # =============================================================================
    # Frontend Routes
    # =============================================================================

    @app.get("/", response_class=HTMLResponse, tags=["frontend"])
    async def serve_skill_main():
        """
        Serve Skill-Based RAG main interface (default landing page)

        Returns:
            HTML content from template/skill_main.html
        """
        try:
            html_path = Path("template/skill_main.html")
            if not html_path.exists():
                return HTMLResponse(
                    content="<h1>Skill Main not found</h1><p>Please ensure template/skill_main.html exists.</p>",
                    status_code=404,
                    media_type="text/html; charset=utf-8"
                )

            html_content = html_path.read_text(encoding='utf-8')
            return HTMLResponse(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )

        except Exception as e:
            logger.error(f"Failed to serve skill main: {str(e)}")
            return HTMLResponse(
                content=f"<h1>Error loading skill main</h1><p>{str(e)}</p>",
                status_code=500,
                media_type="text/html; charset=utf-8"
            )

    @app.get("/SinglePDFQuery", response_class=HTMLResponse, tags=["frontend"])
    async def serve_single_pdf_query():
        """
        Serve Single PDF Query interface (file-based mode)

        Returns:
            HTML content from template/index.html
        """
        try:
            html_path = Path("template/index.html")
            if not html_path.exists():
                return HTMLResponse(
                    content="<h1>Single PDF Query not found</h1><p>Please ensure template/index.html exists.</p>",
                    status_code=404,
                    media_type="text/html; charset=utf-8"
                )

            html_content = html_path.read_text(encoding='utf-8')
            return HTMLResponse(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )

        except Exception as e:
            logger.error(f"Failed to serve single PDF query: {str(e)}")
            return HTMLResponse(
                content=f"<h1>Error loading single PDF query</h1><p>{str(e)}</p>",
                status_code=500,
                media_type="text/html; charset=utf-8"
            )

    @app.get("/skill", response_class=HTMLResponse, tags=["frontend"])
    async def serve_skill_alias():
        """
        Alias for Skill-Based RAG main interface

        Returns:
            HTML content from template/skill_main.html
        """
        try:
            html_path = Path("template/skill_main.html")
            if not html_path.exists():
                return HTMLResponse(
                    content="<h1>Skill Main not found</h1>",
                    status_code=404,
                    media_type="text/html; charset=utf-8"
                )

            html_content = html_path.read_text(encoding='utf-8')
            return HTMLResponse(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate"
                }
            )

        except Exception as e:
            logger.error(f"Failed to serve skill: {str(e)}")
            return HTMLResponse(
                content=f"<h1>Error</h1><p>{str(e)}</p>",
                status_code=500,
                media_type="text/html; charset=utf-8"
            )

    @app.get("/skill/config", response_class=HTMLResponse, tags=["frontend"])
    async def serve_skill_config():
        """
        Serve Skill Configuration interface for managing PDFs

        Returns:
            HTML content from template/skill_config.html
        """
        try:
            html_path = Path("template/skill_config.html")
            if not html_path.exists():
                return HTMLResponse(
                    content="<h1>Skill Config not found</h1><p>Please ensure template/skill_config.html exists.</p>",
                    status_code=404,
                    media_type="text/html; charset=utf-8"
                )

            html_content = html_path.read_text(encoding='utf-8')
            return HTMLResponse(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )

        except Exception as e:
            logger.error(f"Failed to serve skill config: {str(e)}")
            return HTMLResponse(
                content=f"<h1>Error loading skill config</h1><p>{str(e)}</p>",
                status_code=500,
                media_type="text/html; charset=utf-8"
            )

    @app.get("/skill/settings", response_class=HTMLResponse, tags=["frontend"])
    async def serve_skill_settings():
        """
        Serve Settings interface for user preferences and system settings

        Returns:
            HTML content from template/skill_settings.html
        """
        try:
            html_path = Path("template/skill_settings.html")
            if not html_path.exists():
                return HTMLResponse(
                    content="<h1>Settings not found</h1><p>Please ensure template/skill_settings.html exists.</p>",
                    status_code=404,
                    media_type="text/html; charset=utf-8"
                )

            html_content = html_path.read_text(encoding='utf-8')
            return HTMLResponse(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )

        except Exception as e:
            logger.error(f"Failed to serve settings: {str(e)}")
            return HTMLResponse(
                content=f"<h1>Error loading settings</h1><p>{str(e)}</p>",
                status_code=500,
                media_type="text/html; charset=utf-8"
            )

    @app.get("/session-manager", response_class=HTMLResponse, tags=["frontend"])
    async def serve_session_manager():
        """
        Serve Session Manager interface for managing chat sessions

        Returns:
            HTML content from template/session_manager.html
        """
        try:
            html_path = Path("template/session_manager.html")
            if not html_path.exists():
                return HTMLResponse(
                    content="<h1>Session Manager not found</h1><p>Please ensure template/session_manager.html exists.</p>",
                    status_code=404,
                    media_type="text/html; charset=utf-8"
                )

            html_content = html_path.read_text(encoding='utf-8')
            return HTMLResponse(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )

        except Exception as e:
            logger.error(f"Failed to serve session manager: {str(e)}")
            return HTMLResponse(
                content=f"<h1>Error loading session manager</h1><p>{str(e)}</p>",
                status_code=500,
                media_type="text/html; charset=utf-8"
            )

    @app.get("/health", tags=["system"])
    async def health_check():
        """
        Health check endpoint

        Returns:
            System health status
        """
        return JSONResponse(content={
            "status": "healthy",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION
        })

    return app


# =============================================================================
# Application Instance
# =============================================================================

app = create_application()


# =============================================================================
# Main Entry Point (for direct execution)
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    # Configure logging
    logging.basicConfig(
        level=logging.INFO if not settings.DEBUG else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8082, #8082對外portAI Server開放的port #8000,
        reload=False,  # Disable auto-reload and watchfiles
        log_level="info",
        access_log=True  # Enable access logs
    )
