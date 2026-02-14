# Phase 1 API Documentation

## New Endpoints

### LLM Queue Management

#### Get Queue Stats
```http
GET /api/v1/llm/queue/stats
```

**Response:**
```json
{
  "pending": 15,
  "processing": 3
}
```

**Description:** Get current LLM queue statistics.

---

#### Submit LLM Task (Internal)
```python
# Internal API - not exposed via HTTP
from app.services.llm_queue_service import LlmQueueService

queue = LlmQueueService()
task_id = queue.submit_task(
    document_id="doc-123",
    task_type="summary",  # or "extraction", "insight"
    text="Document text...",
    schema="Prompt/schema...",
    priority=1  # Higher = processed first
)
```

---

### Resource Monitoring

#### Get Resource Metrics
```http
GET /api/v1/system/resources
```

**Response:**
```json
{
  "memory_mb": 2048.5,
  "memory_percent": 65.2,
  "cpu_percent": 45.8,
  "active_jobs": 3,
  "timestamp": "2026-02-14T08:00:00Z"
}
```

**Description:** Get current worker resource usage.

---

#### Health Check
```http
GET /api/v1/health
```

**Response:**
```json
{
  "status": "healthy",
  "workers": {
    "extraction": "running",
    "llm": "running"
  },
  "queues": {
    "extraction": 5,
    "llm": 12
  },
  "memory_ok": true,
  "uptime_seconds": 86400
}
```

---

## Modified Endpoints

### Document Processing

#### Upload Document
```http
POST /api/v1/documents/upload
```

**Changes:**
- LLM processing now async (non-blocking)
- Returns immediately after OCR
- `ai_summary` and `ai_insight` populated later

**Response:**
```json
{
  "id": "doc-123",
  "status": "processing",
  "llm_tasks": {
    "summary": "task-456",
    "insight": "task-789"
  }
}
```

---

#### Get Document
```http
GET /api/v1/documents/{id}
```

**New Fields:**
```json
{
  "id": "doc-123",
  "ai_summary": "Invoice from ACME...",  // May be null if LLM pending
  "ai_insight": {
    "risk_level": "low",
    "flags": []
  },
  "llm_status": "completed"  // or "pending", "failed"
}
```

---

## Internal APIs

### Resource Monitor

```python
from app.services.resource_monitor import get_resource_monitor

monitor = get_resource_monitor()

# Check if can start job
if monitor.can_start_job():
    monitor.start_job(job_id)
    # Process job
    monitor.end_job(job_id)

# Get metrics
metrics = monitor.get_current_metrics()

# Check timeout
if monitor.check_job_timeout(job_id):
    # Handle timeout
```

---

### LLM Queue Service

```python
from app.services.llm_queue_service import LlmQueueService

queue = LlmQueueService()

# Submit task
task_id = queue.submit_task(
    document_id=doc_id,
    task_type="summary",
    text=text,
    schema=prompt,
    priority=1
)

# Get result (if completed)
result = queue.get_result(task_id)

# Get stats
stats = queue.get_queue_stats()
```

---

## Configuration

### Environment Variables

```env
# LLM Queue
LLM_QUEUE_ENABLED=true
LLM_QUEUE_WORKERS=2

# Resource Limits
MAX_WORKER_MEMORY_MB=4096
MAX_WORKER_MEMORY_PERCENT=80.0
EXTRACTION_JOB_TIMEOUT_SECONDS=300

# OCR
OCR_BATCH_SIZE=5
OCR_MAX_WORKERS=2
```

---

## Error Handling

### New Error Codes

**503 Service Unavailable**
```json
{
  "error": "Resource limits exceeded",
  "retry_after": 30
}
```
Returned when worker cannot accept job due to memory/CPU limits.

**408 Request Timeout**
```json
{
  "error": "Job timeout",
  "job_id": "job-123",
  "timeout_seconds": 300
}
```
Returned when job exceeds timeout limit.

---

## Migration Notes

### Breaking Changes
None - all changes are backward compatible.

### Behavioral Changes
1. **LLM Processing**: Now async, `ai_summary` and `ai_insight` may be null initially
2. **Job Timeouts**: Jobs now timeout after 300s (configurable)
3. **Resource Limits**: Workers may reject jobs if overloaded
