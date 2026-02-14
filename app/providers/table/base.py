from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class TableCellData(BaseModel):
    text: str
    row_idx: int
    col_idx: int
    row_span: int = 1
    col_span: int = 1
    confidence: float = 0.0
    bbox: Optional[List[float]] = None

class TableStructure(BaseModel):
    cells: List[TableCellData]
    rows_count: int
    cols_count: int
    confidence: float = 0.0

class TableProvider(ABC):
    """Base class for advanced table extraction."""
    
    @abstractmethod
    async def extract_tables(self, image_path: str) -> List[TableStructure]:
        """Extract table structures from an image."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Name of the provider."""
        pass
