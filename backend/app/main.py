from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import memory, review

app = FastAPI(
    title="PRISM API",
    description="Persistent Review Intelligence & Standards Memory",
    version="0.1.0",
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "prism-api"}