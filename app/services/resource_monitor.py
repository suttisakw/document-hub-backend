"""
Resource Monitor Service - Track and enforce resource limits

Monitors memory and CPU usage to prevent worker crashes.
Enforces job timeouts and resource limits.
"""
import psutil
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ResourceMetrics:
    """Resource usage metrics."""
    memory_mb: float
    memory_percent: float
    cpu_percent: float
    timestamp: datetime


@dataclass
class ResourceLimits:
    """Resource limit configuration."""
    max_memory_mb: int = 4096  # 4GB default
    max_memory_percent: float = 80.0  # 80% of available
    max_cpu_percent: float = 90.0
    job_timeout_seconds: int = 300  # 5 minutes default


class ResourceMonitor:
    """Monitor and enforce resource limits for workers."""
    
    def __init__(self, limits: Optional[ResourceLimits] = None):
        self.limits = limits or ResourceLimits()
        self.process = psutil.Process()
        self.job_start_times: Dict[str, datetime] = {}
    
    def get_current_metrics(self) -> ResourceMetrics:
        """Get current resource usage metrics."""
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)  # Convert to MB
        memory_percent = self.process.memory_percent()
        
        # CPU percent over 1 second interval
        cpu_percent = self.process.cpu_percent(interval=0.1)
        
        return ResourceMetrics(
            memory_mb=memory_mb,
            memory_percent=memory_percent,
            cpu_percent=cpu_percent,
            timestamp=datetime.utcnow()
        )
    
    def check_memory_limit(self) -> bool:
        """
        Check if memory usage is within limits.
        
        Returns:
            True if within limits, False if exceeded
        """
        metrics = self.get_current_metrics()
        
        if metrics.memory_mb > self.limits.max_memory_mb:
            logger.warning(
                f"Memory limit exceeded: {metrics.memory_mb:.1f}MB > {self.limits.max_memory_mb}MB"
            )
            return False
        
        if metrics.memory_percent > self.limits.max_memory_percent:
            logger.warning(
                f"Memory percent exceeded: {metrics.memory_percent:.1f}% > {self.limits.max_memory_percent}%"
            )
            return False
        
        return True
    
    def can_start_job(self) -> bool:
        """
        Check if worker can start a new job based on current resources.
        
        Returns:
            True if can start job, False otherwise
        """
        if not self.check_memory_limit():
            logger.warning("Cannot start job: memory limit exceeded")
            return False
        
        metrics = self.get_current_metrics()
        if metrics.cpu_percent > self.limits.max_cpu_percent:
            logger.warning(f"Cannot start job: CPU usage too high ({metrics.cpu_percent:.1f}%)")
            return False
        
        return True
    
    def start_job(self, job_id: str):
        """
        Mark job as started for timeout tracking.
        
        Args:
            job_id: Job identifier
        """
        self.job_start_times[job_id] = datetime.utcnow()
        logger.debug(f"Started tracking job {job_id}")
    
    def check_job_timeout(self, job_id: str) -> bool:
        """
        Check if job has exceeded timeout.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if timed out, False otherwise
        """
        if job_id not in self.job_start_times:
            return False
        
        start_time = self.job_start_times[job_id]
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        if elapsed > self.limits.job_timeout_seconds:
            logger.warning(
                f"Job {job_id} timeout: {elapsed:.1f}s > {self.limits.job_timeout_seconds}s"
            )
            return True
        
        return False
    
    def end_job(self, job_id: str):
        """
        Mark job as ended.
        
        Args:
            job_id: Job identifier
        """
        if job_id in self.job_start_times:
            start_time = self.job_start_times[job_id]
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Job {job_id} completed in {duration:.1f}s")
            del self.job_start_times[job_id]
    
    def get_active_jobs(self) -> Dict[str, float]:
        """
        Get currently active jobs and their durations.
        
        Returns:
            Dict mapping job_id to duration in seconds
        """
        now = datetime.utcnow()
        return {
            job_id: (now - start_time).total_seconds()
            for job_id, start_time in self.job_start_times.items()
        }
    
    def cleanup_stuck_jobs(self) -> list[str]:
        """
        Identify and cleanup stuck jobs that exceeded timeout.
        
        Returns:
            List of timed out job IDs
        """
        timed_out = []
        for job_id in list(self.job_start_times.keys()):
            if self.check_job_timeout(job_id):
                timed_out.append(job_id)
                self.end_job(job_id)
        
        return timed_out
    
    def log_metrics(self):
        """Log current resource metrics."""
        metrics = self.get_current_metrics()
        active_jobs = len(self.job_start_times)
        
        logger.info(
            f"Resources: Memory={metrics.memory_mb:.1f}MB ({metrics.memory_percent:.1f}%), "
            f"CPU={metrics.cpu_percent:.1f}%, Active Jobs={active_jobs}"
        )


# Global monitor instance
_monitor: Optional[ResourceMonitor] = None


def get_resource_monitor() -> ResourceMonitor:
    """Get global resource monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = ResourceMonitor()
    return _monitor


def configure_resource_limits(
    max_memory_mb: Optional[int] = None,
    max_memory_percent: Optional[float] = None,
    job_timeout_seconds: Optional[int] = None
):
    """
    Configure global resource limits.
    
    Args:
        max_memory_mb: Maximum memory in MB
        max_memory_percent: Maximum memory as percent of available
        job_timeout_seconds: Job timeout in seconds
    """
    global _monitor
    
    limits = ResourceLimits()
    if max_memory_mb is not None:
        limits.max_memory_mb = max_memory_mb
    if max_memory_percent is not None:
        limits.max_memory_percent = max_memory_percent
    if job_timeout_seconds is not None:
        limits.job_timeout_seconds = job_timeout_seconds
    
    _monitor = ResourceMonitor(limits)
    logger.info(f"Configured resource limits: {limits}")
