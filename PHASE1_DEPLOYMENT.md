# Phase 1 Deployment Guide

## Prerequisites

- Python 3.11+
- Poetry
- Redis 6+
- PostgreSQL 13+
- 8GB+ RAM recommended

---

## Step 1: Update Dependencies

```bash
cd backend
poetry install

# Verify new dependencies
poetry show psutil  # For resource monitoring
```

---

## Step 2: Database Migration

No database changes required for Phase 1.

---

## Step 3: Configuration

### Update .env file

```bash
# Add Phase 1 configuration
cat phase1_config.env >> .env

# Or manually add:
cat >> .env << EOF

# Phase 1 Configuration
LLM_QUEUE_ENABLED=true
LLM_QUEUE_WORKERS=2
MAX_WORKER_MEMORY_MB=4096
MAX_WORKER_MEMORY_PERCENT=80.0
EXTRACTION_JOB_TIMEOUT_SECONDS=300
OCR_BATCH_SIZE=5
OCR_MAX_WORKERS=2
ENABLE_RESOURCE_MONITORING=true
EOF
```

### Verify Redis

```bash
# Test Redis connection
redis-cli ping
# Should return: PONG

# Check Redis queues
redis-cli keys "*"
```

---

## Step 4: Start Workers

### Terminal 1: LLM Worker (NEW)

```bash
cd backend
poetry run python -m app.workers.llm_worker --poll-interval 2.0
```

**Expected Output:**
```
INFO:app.workers.llm_worker:LLM worker started
INFO:app.services.llm_queue_service:Waiting for tasks...
```

### Terminal 2: Extraction Worker

```bash
cd backend
poetry run python -m app.workers.specialized_worker --poll-interval 2.0
```

**Expected Output:**
```
INFO:app.workers.specialized_worker:Worker started
INFO:app.services.resource_monitor:Resource monitor initialized
```

### Terminal 3: Backend API

```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

---

## Step 5: Verify Deployment

### Check Workers

```bash
# Check running processes
ps aux | grep worker

# Should see:
# - llm_worker
# - specialized_worker
```

### Check Queues

```bash
# Check LLM queue
redis-cli zcard llm_tasks
# Should return: 0 (initially empty)

# Check extraction queue
redis-cli llen orchestration
# Should return: 0 (initially empty)
```

### Test API

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Upload test document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@test.pdf"
```

---

## Step 6: Monitor

### Watch Logs

```bash
# Terminal 4: Watch all logs
tail -f logs/*.log

# Or specific logs
tail -f logs/llm_worker.log
tail -f logs/extraction_worker.log
```

### Monitor Resources

```bash
# Watch memory usage
watch -n 5 'ps aux | grep python | awk "{sum+=\$6} END {print sum/1024\" MB\"}"'

# Watch queue depth
watch -n 2 'redis-cli zcard llm_tasks'
```

---

## Step 7: Test Phase 1 Features

### Test Async LLM Queue

```bash
# Upload document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@invoice.pdf"

# Check LLM queue (should have tasks)
redis-cli zcard llm_tasks

# Wait for processing
sleep 10

# Check document (should have ai_summary)
curl http://localhost:8000/api/v1/documents/{doc_id}
```

### Test Resource Limits

```bash
# Monitor memory before upload
ps aux | grep python

# Upload large PDF (50+ pages)
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@large.pdf"

# Monitor memory during processing
watch -n 1 'ps aux | grep python'

# Verify memory stays under limit (4GB)
```

### Test Job Timeout

```bash
# Submit job
# Wait 5+ minutes
# Check logs for timeout message
grep "timeout" logs/extraction_worker.log
```

---

## Troubleshooting

### LLM Worker Not Starting

```bash
# Check Redis connection
redis-cli ping

# Check Python path
which python
poetry env info

# Check imports
poetry run python -c "from app.services.llm_queue_service import LlmQueueService"
```

### Memory Issues

```bash
# Check current memory
free -h

# Check Python memory
ps aux | grep python | awk '{print $6/1024 " MB"}'

# Force garbage collection
poetry run python -c "import gc; gc.collect()"

# Restart workers
pkill -f worker
# Then restart
```

### Queue Backlog

```bash
# Check queue depth
redis-cli zcard llm_tasks
redis-cli llen orchestration

# Clear queues (if needed)
redis-cli del llm_tasks
redis-cli del orchestration

# Restart workers
```

### Worker Crashes

```bash
# Check logs
tail -100 logs/llm_worker.log
tail -100 logs/extraction_worker.log

# Check for OOM
dmesg | grep -i "out of memory"

# Reduce limits in .env
MAX_WORKER_MEMORY_MB=2048
```

---

## Rollback Plan

If Phase 1 causes issues:

```bash
# 1. Stop new workers
pkill -f llm_worker

# 2. Clear LLM queue
redis-cli del llm_tasks

# 3. Revert code (if needed)
git revert <commit-hash>

# 4. Restart old workers
poetry run python -m app.workers.ocr_worker
```

---

## Production Checklist

- [ ] All workers running
- [ ] Redis queues operational
- [ ] Memory usage < 4GB per worker
- [ ] No worker crashes in 24h
- [ ] LLM tasks completing
- [ ] Job timeouts working
- [ ] Logs clean (no errors)
- [ ] Test document processed successfully

---

## Next Steps

After successful deployment:

1. Monitor for 7 days
2. Collect metrics
3. Tune configuration if needed
4. Proceed to Phase 2
