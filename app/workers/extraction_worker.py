import asyncio
import logging
import time
from uuid import UUID
from sqlmodel import Session
import argparse

from app.db.session import engine
from app.services.redis_queue import pop_easyocr_job, move_due_delayed_jobs
from app.services.extraction_queue import process_extraction_job
from app.core.config import settings
from app.models import OcrJob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_worker(poll_interval: float = 2.0):
    logger.info("Starting Extraction Worker (Async)...")
    
    while True:
        # 1. Maintenance
        move_due_delayed_jobs(limit=10)
        
        # 2. Get next job
        job_id_str = pop_easyocr_job(timeout_seconds=int(poll_interval))
        if not job_id_str:
            continue
            
        try:
            job_id = UUID(job_id_str)
            logger.info(f"Processing job {job_id}")
            
            with Session(engine) as session:
                await process_extraction_job(session=session, job_id=job_id)
                
        except Exception as e:
            logger.error(f"Worker encountered error: {e}")
            await asyncio.sleep(poll_interval)

def main():
    parser = argparse.ArgumentParser(description="Extraction Worker")
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()
    
    asyncio.run(run_worker(args.poll))

if __name__ == "__main__":
    main()
