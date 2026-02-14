import time
import asyncio
import logging
from enum import Enum
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(
        self, 
        name: str,
        fail_threshold: int = 5,
        recovery_timeout: int = 30,
        expected_exception: Exception = Exception
    ):
        self.name = name
        self.fail_threshold = fail_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.fail_count = 0
        self.last_fail_time: Optional[float] = None

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - (self.last_fail_time or 0) > self.recovery_timeout:
                logger.info(f"Circuit {self.name} entering HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                logger.warning(f"Circuit {self.name} is OPEN. Blocking call.")
                raise Exception(f"Circuit {self.name} is OPEN")

        try:
            result = await func(*args, **kwargs)
            
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit {self.name} restored to CLOSED")
                self.state = CircuitState.CLOSED
                self.fail_count = 0
                
            return result
            
        except self.expected_exception as e:
            self.fail_count += 1
            self.last_fail_time = time.time()
            logger.error(f"Circuit {self.name} failure {self.fail_count}/{self.fail_threshold}: {e}")
            
            if self.fail_count >= self.fail_threshold:
                logger.error(f"Circuit {self.name} tripped to OPEN")
                self.state = CircuitState.OPEN
                
            raise e
