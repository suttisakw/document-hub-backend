# Phase 1 Monitoring Guide

## Overview

Phase 1 introduces resource monitoring and async processing. This guide covers monitoring these new systems.

---

## Key Metrics to Monitor

### 1. LLM Queue Metrics

**Queue Depth**
```bash
# Check pending tasks
redis-cli zcard llm_tasks

# Check processing tasks
redis-cli scard llm_tasks:processing
```

**Target:** <50 pending, <5 processing

**Alert if:** >100 pending (queue backlog)

---

**Task Completion Rate**
```bash
# Monitor completed tasks
redis-cli keys "llm_results:*" | wc -l
```

**Target:** 90%+ completion rate

---

### 2. Resource Metrics

**Memory Usage**
```bash
# Per worker
ps aux | grep python | awk '{print $11, $6/1024 "MB"}'

# Total
ps aux | grep python | awk '{sum+=$6} END {print sum/1024 "MB"}'
```

**Target:** <4GB per worker, <12GB total

**Alert if:** >4.5GB per worker (approaching limit)

---

**CPU Usage**
```bash
# Per worker
ps aux | grep python | awk '{print $11, $3"%"}'

# Average
top -b -n 1 | grep python
```

**Target:** <80% per worker

**Alert if:** >90% sustained (CPU bottleneck)

---

### 3. Job Metrics

**Active Jobs**
```python
from app.services.resource_monitor import get_resource_monitor

monitor = get_resource_monitor()
active = monitor.get_active_jobs()
print(f"Active jobs: {len(active)}")
```

**Target:** 1-5 concurrent jobs

**Alert if:** >10 jobs (potential deadlock)

---

**Job Duration**
```bash
# Check logs for job duration
grep "completed in" logs/extraction_worker.log | tail -20
```

**Target:** <5 minutes per job

**Alert if:** >10 minutes (timeout risk)

---

### 4. Worker Health

**Worker Uptime**
```bash
# Check process start time
ps -eo pid,etime,cmd | grep worker
```

**Target:** >24h uptime

**Alert if:** Frequent restarts (<1h uptime)

---

**Worker Crashes**
```bash
# Check for crash logs
grep -i "error\|crash\|exception" logs/worker.log | tail -50
```

**Target:** 0 crashes per day

**Alert if:** >1 crash per hour

---

## Monitoring Scripts

### 1. Real-time Dashboard

```bash
#!/bin/bash
# monitor.sh - Real-time monitoring dashboard

while true; do
  clear
  echo "=== Document Hub Phase 1 Monitor ==="
  echo "Time: $(date)"
  echo ""
  
  echo "=== LLM Queue ==="
  echo "Pending: $(redis-cli zcard llm_tasks)"
  echo "Processing: $(redis-cli scard llm_tasks:processing)"
  echo ""
  
  echo "=== Memory Usage ==="
  ps aux | grep python | awk '{sum+=$6} END {print "Total: " sum/1024 " MB"}'
  echo ""
  
  echo "=== Workers ==="
  ps aux | grep worker | grep -v grep | wc -l | awk '{print "Running: " $1}'
  echo ""
  
  echo "=== Recent Errors ==="
  tail -5 logs/worker.log | grep -i error || echo "None"
  
  sleep 5
done
```

**Usage:**
```bash
chmod +x monitor.sh
./monitor.sh
```

---

### 2. Metrics Collection

```python
# collect_metrics.py
import time
import json
from datetime import datetime
from app.services.resource_monitor import get_resource_monitor
from app.services.llm_queue_service import LlmQueueService

def collect_metrics():
    """Collect all Phase 1 metrics."""
    monitor = get_resource_monitor()
    queue = LlmQueueService()
    
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "resources": {
            "memory_mb": monitor.get_current_metrics().memory_mb,
            "cpu_percent": monitor.get_current_metrics().cpu_percent,
            "active_jobs": len(monitor.get_active_jobs())
        },
        "queues": queue.get_queue_stats()
    }
    
    return metrics

if __name__ == "__main__":
    while True:
        metrics = collect_metrics()
        print(json.dumps(metrics, indent=2))
        
        # Save to file
        with open("metrics.jsonl", "a") as f:
            f.write(json.dumps(metrics) + "\n")
        
        time.sleep(60)  # Every minute
```

**Usage:**
```bash
poetry run python collect_metrics.py
```

---

### 3. Alert Script

```bash
#!/bin/bash
# alert.sh - Check thresholds and alert

# Thresholds
MAX_MEMORY_MB=4096
MAX_QUEUE_DEPTH=100
MAX_CPU_PERCENT=90

# Check memory
MEMORY=$(ps aux | grep python | awk '{sum+=$6} END {print sum/1024}')
if (( $(echo "$MEMORY > $MAX_MEMORY_MB" | bc -l) )); then
  echo "ALERT: Memory usage ${MEMORY}MB exceeds ${MAX_MEMORY_MB}MB"
  # Send alert (email, Slack, etc.)
fi

# Check queue
QUEUE=$(redis-cli zcard llm_tasks)
if [ "$QUEUE" -gt "$MAX_QUEUE_DEPTH" ]; then
  echo "ALERT: Queue depth $QUEUE exceeds $MAX_QUEUE_DEPTH"
fi

# Check CPU
CPU=$(ps aux | grep python | awk '{sum+=$3} END {print sum}')
if (( $(echo "$CPU > $MAX_CPU_PERCENT" | bc -l) )); then
  echo "ALERT: CPU usage ${CPU}% exceeds ${MAX_CPU_PERCENT}%"
fi
```

**Cron:**
```bash
# Run every 5 minutes
*/5 * * * * /path/to/alert.sh
```

---

## Log Files

### Important Logs

**LLM Worker**
```bash
tail -f logs/llm_worker.log
```
Watch for: Task processing, LLM errors, timeouts

**Extraction Worker**
```bash
tail -f logs/extraction_worker.log
```
Watch for: Job timeouts, resource limit rejections

**Resource Monitor**
```bash
grep "Resource" logs/extraction_worker.log
```
Watch for: Memory warnings, job timeouts

---

## Grafana Dashboard (Future - Phase 2)

Recommended panels:

1. **LLM Queue Depth** (time series)
2. **Memory Usage** (gauge + time series)
3. **CPU Usage** (gauge + time series)
4. **Job Duration** (histogram)
5. **Worker Uptime** (stat)
6. **Error Rate** (time series)

---

## Troubleshooting Guide

### High Memory Usage

**Check:**
```bash
ps aux | grep python | sort -k6 -rn | head -5
```

**Actions:**
1. Check for memory leaks
2. Reduce `OCR_BATCH_SIZE`
3. Reduce `MAX_WORKER_MEMORY_MB`
4. Restart workers

---

### Queue Backlog

**Check:**
```bash
redis-cli zcard llm_tasks
redis-cli zrange llm_tasks 0 10 WITHSCORES
```

**Actions:**
1. Add more LLM workers
2. Check LLM worker health
3. Check Ollama availability
4. Clear stuck tasks

---

### Worker Crashes

**Check:**
```bash
grep -i "crash\|killed\|oom" /var/log/syslog
dmesg | tail -50
```

**Actions:**
1. Check OOM killer logs
2. Reduce memory limits
3. Check for code errors
4. Review recent changes

---

## Daily Checklist

- [ ] Check worker uptime
- [ ] Check queue depth
- [ ] Check memory usage
- [ ] Review error logs
- [ ] Verify job completion rate
- [ ] Check for alerts

---

## Weekly Review

- [ ] Analyze metrics trends
- [ ] Review performance
- [ ] Tune configuration
- [ ] Plan capacity
- [ ] Update documentation
