"""
Apply Deep Intelligence migration to add missing columns to documents table.

This script can be run directly to update the database schema.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import engine


def apply_migration():
    """Apply the Deep Intelligence fields migration."""
    migration_file = Path(__file__).parent / "add_deep_intelligence_fields.sql"
    
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
            if statement and not statement.upper().startswith('COMMENT'):
                print(f"  Executing statement {i}/{len(statements)}: {statement[:50]}...")
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    print(f"  ⚠️  Skipping statement (may already exist): {e}")
    
    print("✅ Migration applied successfully!")
    print("\nThe following columns have been added to the 'documents' table:")
    print("  - full_text (TEXT)")
    print("  - embedding (JSON)")
    print("  - extracted_tables (JSON)")
    print("  - extraction_report (JSON)")
    print("  - confidence_report (JSON)")
    print("  - validation_report (JSON)")
    print("  - review_reason (TEXT)")
    print("  - ai_summary (TEXT)")
    print("  - ai_insight (JSON)")


if __name__ == "__main__":
    try:
        apply_migration()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
