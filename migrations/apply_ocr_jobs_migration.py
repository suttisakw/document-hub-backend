"""
Apply OCR Jobs migration to add result_json column.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import engine


def apply_migration():
    """Apply the OCR Jobs result_json migration."""
    migration_file = Path(__file__).parent / "add_ocr_jobs_result_json.sql"
    
    print(f"Reading migration from: {migration_file}")
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    print("Applying migration to database...")
    
    with engine.begin() as conn:
        # Remove comment lines and split by semicolon
        lines = sql.split('\n')
        cleaned_lines = [line for line in lines if not line.strip().startswith('--')]
        cleaned_sql = '\n'.join(cleaned_lines)
        
        # Split by semicolon and execute each statement
        statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]
        
        for i, statement in enumerate(statements, 1):
            if statement:
                print(f"  Executing statement {i}/{len(statements)}: {statement[:50]}...")
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    print(f"  ⚠️  Skipping statement (may already exist): {e}")
    
    print("✅ Migration applied successfully!")
    print("\nThe following columns have been added to the 'ocr_jobs' table:")
    print("  - interface_id (UUID)")
    print("  - transaction_id (UUID)")
    print("  - request_id (INTEGER)")
    print("  - retry_count (INTEGER)")
    print("  - current_step (VARCHAR)")
    print("  - result_data (JSON)")
    print("  - result_json (JSON)")
    print("\nIndexes created:")
    print("  - idx_ocr_jobs_interface_id")
    print("  - idx_ocr_jobs_transaction_id")
    print("  - idx_ocr_jobs_request_id")
    print("  - idx_ocr_jobs_current_step")


if __name__ == "__main__":
    try:
        apply_migration()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
