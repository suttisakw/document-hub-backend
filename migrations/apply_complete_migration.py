"""
Complete Database Schema Migration Script

This script applies all pending schema changes to sync the database
with the SQLModel definitions in models.py.

Usage:
    poetry run python migrations/apply_complete_migration.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import engine


def apply_migration():
    """Apply the complete schema migration."""
    migration_file = Path(__file__).parent / "complete_schema_migration.sql"
    
    print("=" * 70)
    print("Complete Database Schema Migration")
    print("=" * 70)
    print(f"\nReading migration from: {migration_file}")
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    print("\nApplying migration to database...")
    print("-" * 70)
    
    with engine.begin() as conn:
        # Remove comment lines and split by semicolon
        lines = sql.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith('--') and stripped:
                cleaned_lines.append(line)
        
        cleaned_sql = '\n'.join(cleaned_lines)
        
        # Split by semicolon and execute each statement
        statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]
        
        total_statements = len(statements)
        successful = 0
        skipped = 0
        
        for i, statement in enumerate(statements, 1):
            if statement:
                # Show abbreviated statement
                preview = statement.replace('\n', ' ').replace('  ', ' ')[:60]
                print(f"\n[{i}/{total_statements}] {preview}...")
                
                try:
                    conn.execute(text(statement))
                    successful += 1
                    print("    ✓ Success")
                except Exception as e:
                    error_msg = str(e)
                    if "already exists" in error_msg or "duplicate" in error_msg.lower():
                        skipped += 1
                        print(f"    ⊘ Skipped (already exists)")
                    else:
                        print(f"    ✗ Error: {error_msg}")
                        raise
    
    print("\n" + "=" * 70)
    print("✅ Migration completed successfully!")
    print("=" * 70)
    print(f"\nStatistics:")
    print(f"  • Total statements: {total_statements}")
    print(f"  • Successful: {successful}")
    print(f"  • Skipped: {skipped}")
    
    print("\n📋 Changes applied:")
    print("\nDOCUMENTS table - Added columns:")
    print("  • full_text (TEXT)")
    print("  • embedding (JSON)")
    print("  • extracted_tables (JSON)")
    print("  • extraction_report (JSON)")
    print("  • confidence_report (JSON)")
    print("  • validation_report (JSON)")
    print("  • review_reason (TEXT)")
    print("  • ai_summary (TEXT)")
    print("  • ai_insight (JSON)")
    
    print("\nOCR_JOBS table - Added columns:")
    print("  • interface_id (UUID)")
    print("  • transaction_id (UUID)")
    print("  • request_id (INTEGER)")
    print("  • retry_count (INTEGER)")
    print("  • current_step (VARCHAR)")
    print("  • result_data (JSON)")
    print("  • result_json (JSON)")
    
    print("\nIndexes created:")
    print("  • idx_ocr_jobs_interface_id")
    print("  • idx_ocr_jobs_transaction_id")
    print("  • idx_ocr_jobs_request_id")
    print("  • idx_ocr_jobs_current_step")
    
    print("\n" + "=" * 70)
    print("🚀 You can now restart your backend server!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        apply_migration()
    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ Migration failed: {e}")
        print("=" * 70)
        sys.exit(1)
