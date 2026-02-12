from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    audit,
    auth,
    document_router,
    documents,
    matching,
    matching_rules,
    ocr,
    ocr_templates,
    taxonomy,
    users,
)
from app.api.routers import settings as settings_router
from app.core.config import settings

app = FastAPI(
    title="Document Hub Backend",
    description="FastAPI backend for Document Hub OCR System",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(document_router.router)
app.include_router(ocr.router)
app.include_router(ocr_templates.router)
app.include_router(settings_router.router)
app.include_router(users.router)
app.include_router(audit.router)
app.include_router(taxonomy.router)
app.include_router(matching_rules.router)
app.include_router(matching.router)


@app.get("/")
async def root():
    return {"message": "Document Hub Backend API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
