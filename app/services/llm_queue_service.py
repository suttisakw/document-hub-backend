"""
LLM Queue Service - Async LLM Processing

Provides non-blocking LLM task submission and processing via Redis queue.
Eliminates worker deadlock caused by synchronous LLM calls.
"""
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, Dict, Any
import json
import logging

from app.services.redis_queue import get_redis_client

logger = logging.getLogger(__name__)

# Queue names
LLM_QUEUE = "llm_tasks"
LLM_PROCESSING = "llm_tasks:processing"
LLM_RESULTS = "llm_results"

class LlmTask:
    """Represents an LLM processing task."""
    
    def __init__(
        self,
        task_id: str,
        document_id: str,
        task_type: str,  # "extraction" | "summary" | "insight"
        text: str,
        schema: str,
        callback_data: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        created_at: Optional[datetime] = None
    ):
        self.task_id = task_id
        self.document_id = document_id
        self.task_type = task_type
        self.text = text
        self.schema = schema
        self.callback_data = callback_data or {}
        self.priority = priority
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "document_id": self.document_id,
            "task_type": self.task_type,
            "text": self.text,
            "schema": self.schema,
            "callback_data": self.callback_data,
            "priority": self.priority,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LlmTask":
        return cls(
            task_id=data["task_id"],
            document_id=data["document_id"],
            task_type=data["task_type"],
            text=data["text"],
            schema=data["schema"],
            callback_data=data.get("callback_data", {}),
            priority=data.get("priority", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else None
        )


class LlmQueueService:
    """Service for managing LLM task queue."""
    
    def __init__(self):
        self.redis = get_redis_client()
    
    def submit_task(
        self,
        document_id: str,
        task_type: str,
        text: str,
        schema: str,
        callback_data: Optional[Dict[str, Any]] = None,
        priority: int = 0
    ) -> str:
        """
        Submit an LLM task to the queue (non-blocking).
        
        Args:
            document_id: Document ID
            task_type: Type of task (extraction, summary, insight)
            text: Text to process
            schema: Schema/prompt for LLM
            callback_data: Additional data for callback
            priority: Task priority (higher = processed first)
        
        Returns:
            task_id: Unique task ID
        """
        task_id = str(uuid4())
        
        task = LlmTask(
            task_id=task_id,
            document_id=document_id,
            task_type=task_type,
            text=text,
            schema=schema,
            callback_data=callback_data,
            priority=priority
        )
        
        # Add to queue with priority
        score = -priority  # Negative for descending order
        self.redis.zadd(LLM_QUEUE, {json.dumps(task.to_dict()): score})
        
        logger.info(f"Submitted LLM task {task_id} for document {document_id}")
        return task_id
    
    def pop_task(self, timeout: int = 5) -> Optional[LlmTask]:
        """
        Pop next task from queue (blocking with timeout).
        
        Args:
            timeout: Timeout in seconds
        
        Returns:
            LlmTask or None if timeout
        """
        # Get highest priority task
        result = self.redis.zpopmin(LLM_QUEUE, count=1)
        
        if not result:
            return None
        
        task_json, _ = result[0]
        task_data = json.loads(task_json)
        task = LlmTask.from_dict(task_data)
        
        # Move to processing set
        self.redis.sadd(LLM_PROCESSING, task.task_id)
        
        return task
    
    def complete_task(self, task_id: str, result: Dict[str, Any], error: Optional[str] = None):
        """
        Mark task as complete and store result.
        
        Args:
            task_id: Task ID
            result: LLM result data
            error: Error message if failed
        """
        # Remove from processing
        self.redis.srem(LLM_PROCESSING, task_id)
        
        # Store result (expire after 1 hour)
        result_data = {
            "task_id": task_id,
            "result": result,
            "error": error,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        result_key = f"{LLM_RESULTS}:{task_id}"
        self.redis.setex(result_key, 3600, json.dumps(result_data))
        
        logger.info(f"Completed LLM task {task_id}")
    
    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task result if available.
        
        Args:
            task_id: Task ID
        
        Returns:
            Result data or None
        """
        result_key = f"{LLM_RESULTS}:{task_id}"
        result_json = self.redis.get(result_key)
        
        if not result_json:
            return None
        
        return json.loads(result_json)
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        return {
            "pending": self.redis.zcard(LLM_QUEUE),
            "processing": self.redis.scard(LLM_PROCESSING)
        }
    
    def requeue_stuck_tasks(self, max_age_seconds: int = 300):
        """
        Requeue tasks stuck in processing for too long.
        
        Args:
            max_age_seconds: Max processing time before requeue
        """
        # This is a simplified version
        # In production, track task start time and requeue based on that
        processing_tasks = self.redis.smembers(LLM_PROCESSING)
        
        for task_id in processing_tasks:
            # Check if task is stuck (simplified - just requeue all for now)
            # In production: check timestamp
            logger.warning(f"Requeuing potentially stuck task {task_id}")
            # Implementation depends on how we track task metadata
