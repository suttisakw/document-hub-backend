from __future__ import annotations

import argparse
import time
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from app.db.session import engine
from app.services.ocr_queue import (
    claim_easyocr_job_by_id,
    claim_next_pending_easyocr_job,
    process_easyocr_job,
)
from app.services.redis_queue import move_due_delayed_jobs, pop_easyocr_job


def run_worker(*, poll_interval: float = 2.0, once: bool = False) -> int:
    processed = 0
    while True:
        claimed = None

        move_due_delayed_jobs(limit=200)

        queued_id = pop_easyocr_job(timeout_seconds=settings.ocr_queue_block_timeout_seconds)
        if queued_id:
            try:
                job_uuid = UUID(queued_id)
            except ValueError:
                job_uuid = None

            if job_uuid is not None:
                with Session(engine) as session:
                    claimed = claim_easyocr_job_by_id(session=session, job_id=job_uuid)
                    if claimed is not None:
                        process_easyocr_job(session=session, job_id=claimed.id)
                        processed += 1
                        continue

        with Session(engine) as session:
            job = claim_next_pending_easyocr_job(session=session)
            if job is not None:
                process_easyocr_job(session=session, job_id=job.id)
                processed += 1
                continue

        if once:
            return processed

        time.sleep(max(0.2, poll_interval))


def main() -> None:
    parser = argparse.ArgumentParser(description="Document Hub EasyOCR worker")
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval seconds when queue is empty",
    )
    args = parser.parse_args()

    run_worker(poll_interval=args.poll_interval, once=args.once)


if __name__ == "__main__":
    main()
