from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import jobs, memory, review
from app.services.hindsight_service import hindsight_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await hindsight_service.ensure_bank_configuration()
    yield
    await hindsight_service.close()


app = FastAPI(
    title="PRISM API",
    description="Persistent Review Intelligence & Standards Memory",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory.router)
app.include_router(review.router)
app.include_router(jobs.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "prism-api"}