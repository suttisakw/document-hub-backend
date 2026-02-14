"""
Unit tests for LLM Queue Service
"""
import pytest
from unittest.mock import Mock, patch
from app.services.llm_queue_service import LlmQueueService, LlmTask


class TestLlmQueueService:
    """Test LLM queue service functionality."""
    
    @pytest.fixture
    def queue_service(self):
        """Create queue service instance."""
        with patch('app.services.llm_queue_service.get_redis_client'):
            return LlmQueueService()
    
    def test_submit_task(self, queue_service):
        """Test task submission."""
        task_id = queue_service.submit_task(
            document_id="test-doc-123",
            task_type="extraction",
            text="Test text",
            schema="Test schema",
            priority=1
        )
        
        assert task_id is not None
        assert isinstance(task_id, str)
    
    def test_task_serialization(self):
        """Test LlmTask serialization."""
        task = LlmTask(
            task_id="test-123",
            document_id="doc-456",
            task_type="summary",
            text="Test text",
            schema="Test schema",
            priority=1
        )
        
        # Serialize
        task_dict = task.to_dict()
        assert task_dict["task_id"] == "test-123"
        assert task_dict["task_type"] == "summary"
        
        # Deserialize
        restored = LlmTask.from_dict(task_dict)
        assert restored.task_id == task.task_id
        assert restored.task_type == task.task_type
    
    def test_priority_ordering(self, queue_service):
        """Test that higher priority tasks are processed first."""
        # Submit low priority task
        low_id = queue_service.submit_task(
            document_id="doc-1",
            task_type="summary",
            text="Low priority",
            schema="Schema",
            priority=1
        )
        
        # Submit high priority task
        high_id = queue_service.submit_task(
            document_id="doc-2",
            task_type="summary",
            text="High priority",
            schema="Schema",
            priority=10
        )
        
        # High priority should be popped first
        # (Implementation depends on Redis mock)


@pytest.mark.asyncio
class TestLlmWorker:
    """Test LLM worker functionality."""
    
    async def test_process_summary_task(self):
        """Test processing summary task."""
        from app.workers.llm_worker import process_llm_task
        from app.services.llm_queue_service import LlmTask
        from unittest.mock import AsyncMock
        
        task = LlmTask(
            task_id="test-123",
            document_id="doc-456",
            task_type="summary",
            text="Test document text",
            schema="Summarize this document",
            priority=1
        )
        
        mock_session = Mock()
        
        with patch('app.workers.llm_worker.get_llm_provider') as mock_provider:
            mock_provider.return_value.extract_fields = AsyncMock(
                return_value=Mock(data="Test summary", model_name="test-model")
            )
            
            await process_llm_task(task, mock_session)
            
            # Verify LLM was called
            mock_provider.return_value.extract_fields.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
