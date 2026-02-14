import asyncio
import logging
import argparse
from uuid import UUID
from sqlmodel import Session
from app.db.session import engine
from app.services.redis_queue import pop_job, move_due_delayed_jobs
from app.services.extraction_queue import process_extraction_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# Use ProcessPool for OCR (CPU-bound, bypass GIL)
# Use ThreadPool for I/O bound (Render, Extraction, Orchestrate)
pool_cpu = ProcessPoolExecutor(max_workers=2)
pool_io = ThreadPoolExecutor(max_workers=4)

async def run_worker(queue_name: str, poll_interval: float = 2.0):
    logger.info(f"Starting {queue_name.capitalize()} Worker (Reliable Mode)...")
    
    # Optional: Clear stale jobs for this queue on startup
    from app.services.redis_queue import move_back_stale_jobs
    moved = move_back_stale_jobs(queue_name)
    if moved:
        logger.info(f"Moved {moved} stale jobs back to '{queue_name}' queue.")

    while True:
        # Maintenance
        if queue_name == "orchestration":
            move_due_delayed_jobs(limit=10)
        
        # 1. Reliable Pop (moved to processing list)
        from app.services.redis_queue import pop_job_reliable, mark_job_complete
        job_id_str = pop_job_reliable(queue_name=queue_name, timeout_seconds=int(poll_interval))
        
        if not job_id_str:
            continue
            
        try:
            job_id = UUID(job_id_str)
            logger.info(f"[{queue_name.upper()}] Processing job {job_id}")
            
            with Session(engine) as session:
                # 2. Execute job
                await process_extraction_job(session=session, job_id=job_id)
                
                # 3. Mark Complete (remove from processing list)
                mark_job_complete(job_id_str, queue_name)
                
        except Exception as e:
            logger.error(f"Worker {queue_name} encountered error: {e}")
            # If it fails, it stays in the processing list until cleanup or retry mechanism handles it
            # For now, we rely on the manual cleanup or next restart
            await asyncio.sleep(poll_interval)

def main():
    parser = argparse.ArgumentParser(description="Specialized Extraction Worker")
    parser.add_argument("--queue", type=str, default="orchestration", choices=["orchestration", "render", "ocr", "extraction"])
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()
    
    asyncio.run(run_worker(args.queue, args.poll))

if __name__ == "__main__":
    main()
