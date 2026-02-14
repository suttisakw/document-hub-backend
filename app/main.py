from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    audit,
    auth,
    confidence_routing,
    corrections,
    document_router,
    documents,
    matching,
    matching_rules,
    ocr,
    ocr_templates,
    output_formatter,
    taxonomy,
    users,
    analytics,
    discovery,
    review,
    export,
    learning,
)
from app.api.routers import settings as settings_router
from app.core.config import settings

OPENAPI_DESCRIPTION = """
Document Hub API สำหรับระบบ OCR และการจับคู่เอกสาร

## Authentication
ส่วนใหญ่ endpoint ต้องใช้ **Bearer token** (OAuth2 password flow)
- ใช้ **POST /api/v1/auth/token** เพื่อรับ token (ส่ง `username` = email, `password`)
- คลิก **Authorize** ใน Swagger UI แล้วใส่ token หรือ username/password

## กลุ่ม API
- **auth** – ลงทะเบียน, ล็อกอิน, ข้อมูลผู้ใช้
- **documents** – อัปโหลด, รายการ, สถิติ, export, แก้ไขฟิลด์
- **ocr** – งาน OCR (jobs, retry, cancel, trigger external/EasyOCR), webhook
- **ocr-templates** – เทมเพลต OCR ตามโซน
- **matching** – ชุดการจับคู่ (sets), จับคู่อัตโนมัติ
- **matching-rules** – กฎการจับคู่ (conditions, test)
- **taxonomy** – หมวดหมู่, แท็ก, กลุ่มเอกสาร
- **settings** – storage, external OCR interfaces
- **audit** – บันทึก audit log
- **users** – จัดการผู้ใช้ (admin)
"""

app = FastAPI(
    title="Document Hub API",
    description=OPENAPI_DESCRIPTION,
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    servers=[{"url": "/", "description": "Current host"}],
    openapi_tags=[
        {"name": "auth", "description": "ลงทะเบียน, ล็อกอิน, ข้อมูลผู้ใช้ปัจจุบัน"},
        {"name": "documents", "description": "อัปโหลดและจัดการเอกสาร, สถิติ, export, ฟิลด์และหน้า"},
        {"name": "document-extraction", "description": "สกัดข้อความและฟิลด์จากไฟล์ (OCR + LLM)"},
        {"name": "ocr", "description": "งาน OCR, คิว, retry/cancel, trigger, webhook"},
        {"name": "ocr-templates", "description": "เทมเพลต OCR ตามโซนและ apply กับเอกสาร"},
        {"name": "matching", "description": "ชุดการจับคู่เอกสาร (sets), unmatched, auto-match"},
        {"name": "matching-rules", "description": "กฎการจับคู่ (conditions, test rule)"},
        {"name": "taxonomy", "description": "หมวดหมู่, แท็ก, กลุ่มเอกสาร"},
        {"name": "settings", "description": "Storage, External OCR interfaces"},
        {"name": "audit", "description": "Audit logs"},
        {"name": "users", "description": "จัดการผู้ใช้ (admin only)"},
        {"name": "corrections", "description": "แก้ไขฟิลด์, ประวัติแก้ไข, ข้อมูล training"},
        {"name": "export", "description": "Export documents (JSON, CSV, JSONL, ERP mapping)"},
        {"name": "routing", "description": "Route documents based on confidence scores (approved, review, rejected)"},
    ],
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Group all API routes under /api/v1
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(document_router.router)
api_router.include_router(ocr.router)
api_router.include_router(ocr_templates.router)
api_router.include_router(settings_router.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(taxonomy.router)
api_router.include_router(matching_rules.router)
api_router.include_router(matching.router)
api_router.include_router(corrections.router)
api_router.include_router(output_formatter.router)
api_router.include_router(confidence_routing.router)
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(learning.router)

app.include_router(api_router)


@app.get("/", tags=["root"])
async def root():
    """Root endpoint; returns API info."""
    return {"message": "Document Hub Backend API"}


@app.get("/health", tags=["root"])
async def health_check():
    """Health check for load balancer / monitoring."""
    return {"status": "healthy"}
