from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from app.core.config import settings
from app.db.database import init_db
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown events."""
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="FastAPI service for uploading, processing, and measuring geospatial files.",
    lifespan=lifespan,
)

# Register API v1 router routes under settings.API_PREFIX (/api)
app.include_router(api_router, prefix=settings.API_PREFIX)



@app.get("/health", tags=["Health"], summary="Health check endpoint")
def health_check() -> dict[str, str]:
    """Health check endpoint to verify that the service is running and healthy."""
    return {
        "status": "ok",
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
