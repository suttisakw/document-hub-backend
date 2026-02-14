"""
Unit tests for Resource Monitor
"""
import pytest
import time
from app.services.resource_monitor import ResourceMonitor, ResourceLimits


class TestResourceMonitor:
    """Test resource monitoring functionality."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with test limits."""
        limits = ResourceLimits(
            max_memory_mb=2048,
            max_memory_percent=80.0,
            job_timeout_seconds=10
        )
        return ResourceMonitor(limits)
    
    def test_get_current_metrics(self, monitor):
        """Test getting current resource metrics."""
        metrics = monitor.get_current_metrics()
        
        assert metrics.memory_mb > 0
        assert metrics.memory_percent > 0
        assert metrics.cpu_percent >= 0
        assert metrics.timestamp is not None
    
    def test_can_start_job(self, monitor):
        """Test job start permission."""
        # Should be able to start job initially
        assert monitor.can_start_job() is True
    
    def test_job_timeout_tracking(self, monitor):
        """Test job timeout detection."""
        job_id = "test-job-123"
        
        # Start job
        monitor.start_job(job_id)
        
        # Should not timeout immediately
        assert monitor.check_job_timeout(job_id) is False
        
        # Wait for timeout
        time.sleep(11)  # Timeout is 10 seconds
        
        # Should timeout now
        assert monitor.check_job_timeout(job_id) is True
    
    def test_job_lifecycle(self, monitor):
        """Test complete job lifecycle."""
        job_id = "test-job-456"
        
        # Start job
        monitor.start_job(job_id)
        assert job_id in monitor.get_active_jobs()
        
        # End job
        monitor.end_job(job_id)
        assert job_id not in monitor.get_active_jobs()
    
    def test_cleanup_stuck_jobs(self, monitor):
        """Test cleanup of stuck jobs."""
        # Start multiple jobs
        monitor.start_job("job-1")
        monitor.start_job("job-2")
        
        # Wait for timeout
        time.sleep(11)
        
        # Cleanup
        timed_out = monitor.cleanup_stuck_jobs()
        
        assert len(timed_out) == 2
        assert "job-1" in timed_out
        assert "job-2" in timed_out
        
        # Jobs should be removed
        assert len(monitor.get_active_jobs()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
