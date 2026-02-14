import logging
from typing import List
from app.providers.table.base import TableProvider, TableStructure, TableCellData

logger = logging.getLogger(__name__)

class PaddleTableProvider(TableProvider):
    """Table extraction using PaddleOCR's PP-Structure."""

    async def extract_tables(self, image_path: str) -> List[TableStructure]:
        try:
            from paddleocr import PPStructure
            import re
            
            logger.info(f"Running PaddleTable PP-Structure on {image_path}")
            table_engine = PPStructure(show_log=False, table=True)
            result = table_engine(image_path)
            
            structures = []
            for res in result:
                if res['type'] != 'table':
                    continue
                
                html = res['res'].get('html', '')
                if not html:
                    continue
                
                # Parse HTML for spans
                cells_data = []
                rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
                
                # Keep track of occupied cells for row/col indexing
                occupied = set()
                
                for r_idx, row_html in enumerate(rows):
                    # <td> can have attributes like rowspan="2" colspan="3"
                    cells = re.findall(r'<td(.*?)>(.*?)</td>', row_html, re.DOTALL)
                    
                    c_ptr = 0
                    for attrs, text in cells:
                        # Skip occupied cells from previous row spans
                        while (r_idx, c_ptr) in occupied:
                            c_ptr += 1
                            
                        row_span = 1
                        col_span = 1
                        
                        r_match = re.search(r'rowspan="(\d+)"', attrs)
                        if r_match: row_span = int(r_match.group(1))
                        
                        c_match = re.search(r'colspan="(\d+)"', attrs)
                        if c_match: col_span = int(c_match.group(1))
                        
                        # Mark occupied cells
                        for rs in range(row_span):
                            for cs in range(col_span):
                                occupied.add((r_idx + rs, c_ptr + cs))
                        
                        cells_data.append(TableCellData(
                            text=text.replace('<html><body><table>', '').replace('</table></body></html>', '').strip(),
                            row_idx=r_idx,
                            col_idx=c_ptr,
                            row_span=row_span,
                            col_span=col_span,
                            confidence=0.8
                        ))
                        c_ptr += col_span

                structures.append(TableStructure(
                    cells=cells_data,
                    rows_count=len(rows),
                    cols_count=max(c[1] for c in occupied) + 1 if occupied else 0,
                    confidence=0.85
                ))
            
            return structures
        except Exception as e:
            logger.error(f"PaddleTable failed: {e}")
            return []

    def get_name(self) -> str:
        return "paddle_structure"
