# Phase 1 Testing Guide

## Quick Test Commands

### Unit Tests
```bash
# Test LLM Queue
poetry run pytest tests/test_llm_queue.py -v

# Test Resource Monitor
poetry run pytest tests/test_resource_monitor.py -v

# Test OCR Batching (if exists)
poetry run pytest tests/test_ocr_easyocr.py -v
```

### Integration Tests
```bash
# Run all Phase 1 integration tests
poetry run pytest tests/test_phase1_integration.py -v -s

# Run specific test
poetry run pytest tests/test_phase1_integration.py::TestPhase1Integration::test_async_llm_workflow -v
```

### Manual Testing

#### 1. Test Async LLM Queue

**Start LLM Worker:**
```bash
poetry run python -m app.workers.llm_worker --poll-interval 2.0
```

**Submit Test Task (Python REPL):**
```python
from app.services.llm_queue_service import LlmQueueService

queue = LlmQueueService()
task_id = queue.submit_task(
    document_id="test-doc-123",
    task_type="summary",
    text="This is a test invoice from ACME Corp for $500.00 dated 2024-01-01",
    schema="Summarize this document in one sentence",
    priority=1
)
print(f"Submitted task: {task_id}")

# Check queue stats
stats = queue.get_queue_stats()
print(f"Queue stats: {stats}")
```

#### 2. Test Resource Monitor

**Python REPL:**
```python
from app.services.resource_monitor import get_resource_monitor

monitor = get_resource_monitor()

# Get current metrics
metrics = monitor.get_current_metrics()
print(f"Memory: {metrics.memory_mb:.1f}MB ({metrics.memory_percent:.1f}%)")
print(f"CPU: {metrics.cpu_percent:.1f}%")

# Test job tracking
monitor.start_job("test-job-1")
print(f"Active jobs: {monitor.get_active_jobs()}")

# Check if can start new job
can_start = monitor.can_start_job()
print(f"Can start job: {can_start}")

monitor.end_job("test-job-1")
```

#### 3. Test OCR Batching

**Process Multi-Page PDF:**
```python
from app.services.extraction.ocr_engine import OcrEngine
from app.models import DocumentPage
from app.db.session import engine
from sqlmodel import Session

# Get document with multiple pages
with Session(engine) as session:
    # Assuming you have a document with pages
    pages = session.query(DocumentPage).filter(
        DocumentPage.document_id == "your-doc-id"
    ).all()
    
    engine = OcrEngine()
    result = await engine.run_ocr(pages)
    
    print(f"Processed {len(pages)} pages")
    print(f"Total text length: {len(result.full_text)}")
```

## Load Testing

### Test 100 Documents
```bash
# Use locust or custom script
poetry run python scripts/load_test_phase1.py --documents 100 --concurrent 10
```

### Monitor During Load Test
```bash
# Terminal 1: Watch queue
watch -n 1 'redis-cli llen llm_tasks'

# Terminal 2: Watch memory
watch -n 1 'ps aux | grep python'

# Terminal 3: Watch logs
tail -f logs/worker.log
```

## Expected Results

### ✅ Success Criteria

**Async LLM Queue:**
- Tasks submitted instantly (<10ms)
- Worker processes tasks without blocking
- No worker deadlocks

**Resource Monitor:**
- Memory tracking accurate
- Job timeout detected within 1s
- Resource limits enforced

**OCR Batching:**
- Memory usage stable (<4GB per worker)
- Batch processing 5 pages at a time
- No memory leaks

### ❌ Failure Indicators

- Worker hangs/deadlocks
- Memory continuously increasing
- Jobs timing out unexpectedly
- Queue backlog growing indefinitely

## Troubleshooting

### LLM Queue Issues
```bash
# Check Redis connection
redis-cli ping

# Check queue depth
redis-cli zcard llm_tasks

# Clear queue (if needed)
redis-cli del llm_tasks
```

### Memory Issues
```bash
# Check Python memory
python -c "import psutil; print(f'Memory: {psutil.Process().memory_info().rss / 1024**2:.1f}MB')"

# Force garbage collection
python -c "import gc; gc.collect()"
```

### Worker Issues
```bash
# Check worker process
ps aux | grep llm_worker

# Kill stuck worker
pkill -f llm_worker

# Restart worker
poetry run python -m app.workers.llm_worker
```
