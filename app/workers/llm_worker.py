"""
LLM Worker - Processes LLM tasks from queue

Dedicated worker for LLM processing to prevent blocking extraction workers.
"""
import argparse
import time
import logging
from uuid import UUID

from sqlmodel import Session

from app.db.session import engine
from app.services.llm_queue_service import LlmQueueService, LlmTask
from app.services.llm_service import get_llm_provider
from app.models import Document
from sqlmodel import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def process_llm_task(task: LlmTask, session: Session):
    """
    Process a single LLM task.
    
    Args:
        task: LLM task to process
        session: Database session
    """
    logger.info(f"Processing LLM task {task.task_id} for document {task.document_id}")
    
    try:
        # Get LLM provider
        provider = get_llm_provider()
        
        # Process based on task type
        if task.task_type == "extraction":
            result = await provider.extract_fields(task.text, task.schema)
            result_data = {
                "data": result.data,
                "raw_response": result.raw_response,
                "model_name": result.model_name
            }
        
        elif task.task_type == "summary":
            result = await provider.extract_fields(task.text, task.schema)
            result_data = {
                "summary": str(result.data) if isinstance(result.data, str) else str(result.data.get("summary", result.data)),
                "model_name": result.model_name
            }
        
        elif task.task_type == "insight":
            result = await provider.extract_fields(task.text, task.schema)
            result_data = {
                "insight": result.data if isinstance(result.data, dict) else {"raw": result.data},
                "model_name": result.model_name
            }
        
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")
        
        # Update document with result
        await update_document_with_result(task, result_data, session)
        
        # Mark task as complete
        queue_service = LlmQueueService()
        queue_service.complete_task(task.task_id, result_data)
        
        logger.info(f"Completed LLM task {task.task_id}")
        
    except Exception as e:
        logger.exception(f"LLM task {task.task_id} failed: {e}")
        
        # Mark task as failed
        queue_service = LlmQueueService()
        queue_service.complete_task(task.task_id, {}, error=str(e))


async def update_document_with_result(task: LlmTask, result_data: dict, session: Session):
    """
    Update document with LLM result based on callback data.
    
    Args:
        task: LLM task
        result_data: Result from LLM
        session: Database session
    """
    try:
        doc = session.exec(
            select(Document).where(Document.id == UUID(task.document_id))
        ).first()
        
        if not doc:
            logger.error(f"Document {task.document_id} not found")
            return
        
        # Update based on task type
        if task.task_type == "summary":
            doc.ai_summary = result_data.get("summary")
        
        elif task.task_type == "insight":
            doc.ai_insight = result_data.get("insight")
        
        elif task.task_type == "extraction":
            # Store in callback_data specified field
            field_name = task.callback_data.get("field_name")
            if field_name:
                setattr(doc, field_name, result_data.get("data"))
        
        session.add(doc)
        session.commit()
        
        logger.info(f"Updated document {task.document_id} with LLM result")
        
    except Exception as e:
        logger.exception(f"Failed to update document {task.document_id}: {e}")
        session.rollback()


def run_worker(poll_interval: float = 2.0, once: bool = False) -> int:
    """
    Run LLM worker loop.
    
    Args:
        poll_interval: Polling interval in seconds
        once: Process only one task and exit
    
    Returns:
        Number of tasks processed
    """
    import asyncio
    
    queue_service = LlmQueueService()
    processed = 0
    
    logger.info("LLM worker started")
    
    while True:
        try:
            # Pop task from queue
            task = queue_service.pop_task(timeout=5)
            
            if task:
                with Session(engine) as session:
                    asyncio.run(process_llm_task(task, session))
                    processed += 1
                
                if once:
                    return processed
            else:
                # No task available, sleep
                time.sleep(poll_interval)
        
        except KeyboardInterrupt:
            logger.info("Worker interrupted, shutting down...")
            break
        
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            time.sleep(poll_interval)
    
    return processed


def main():
    """Main entry point for LLM worker."""
    parser = argparse.ArgumentParser(description="Document Hub LLM Worker")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds"
    )
    args = parser.parse_args()
    
    run_worker(poll_interval=args.poll_interval, once=args.once)


if __name__ == "__main__":
    main()
