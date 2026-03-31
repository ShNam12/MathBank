"""
Migration: Add V2 fields to questions table
Thêm các columns mới cho AI enrichment và review workflow

Columns được thêm:
- explanation: TEXT - Lời giải chi tiết từ AI
- explanation_latex: TEXT - LaTeX version của explanation
- ai_enriched: BOOLEAN - Flag cho biết có được AI làm giàu không
- review_status: VARCHAR(20) - Trạng thái review (DRAFT, AI_GENERATED, VERIFIED, REJECTED)

Backward compatible: Tất cả columns có DEFAULT values
"""

import sqlite3
import sys
from pathlib import Path

# Thêm parent directory vào path để import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config


def migrate():
    """Chạy migration để thêm V2 fields"""
    db_path = Config.DATABASE_PATH
    
    print(f"[MIGRATION] Bắt đầu migration V2 fields...")
    print(f"[MIGRATION] Database path: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Kiểm tra xem columns đã tồn tại chưa
        cursor.execute("PRAGMA table_info(questions)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        migrations_applied = []
        
        # 1. Thêm explanation column
        if 'explanation' not in existing_columns:
            print("[MIGRATION] Thêm column: explanation")
            cursor.execute("""
                ALTER TABLE questions 
                ADD COLUMN explanation TEXT DEFAULT ''
            """)
            migrations_applied.append("explanation")
        else:
            print("[MIGRATION] Column 'explanation' đã tồn tại, bỏ qua")
        
        # 2. Thêm explanation_latex column
        if 'explanation_latex' not in existing_columns:
            print("[MIGRATION] Thêm column: explanation_latex")
            cursor.execute("""
                ALTER TABLE questions 
                ADD COLUMN explanation_latex TEXT DEFAULT ''
            """)
            migrations_applied.append("explanation_latex")
        else:
            print("[MIGRATION] Column 'explanation_latex' đã tồn tại, bỏ qua")
        
        # 3. Thêm ai_enriched column
        if 'ai_enriched' not in existing_columns:
            print("[MIGRATION] Thêm column: ai_enriched")
            cursor.execute("""
                ALTER TABLE questions 
                ADD COLUMN ai_enriched BOOLEAN DEFAULT 0
            """)
            migrations_applied.append("ai_enriched")
        else:
            print("[MIGRATION] Column 'ai_enriched' đã tồn tại, bỏ qua")
        
        # 4. Thêm review_status column
        if 'review_status' not in existing_columns:
            print("[MIGRATION] Thêm column: review_status")
            cursor.execute("""
                ALTER TABLE questions 
                ADD COLUMN review_status VARCHAR(20) DEFAULT 'DRAFT'
            """)
            migrations_applied.append("review_status")
        else:
            print("[MIGRATION] Column 'review_status' đã tồn tại, bỏ qua")
        
        # 5. Cập nhật review_status cho các questions cũ (nếu chưa có)
        if 'review_status' in migrations_applied or 'review_status' not in existing_columns:
            print("[MIGRATION] Cập nhật review_status cho questions cũ...")
            cursor.execute("""
                UPDATE questions 
                SET review_status = 'DRAFT' 
                WHERE review_status IS NULL OR review_status = ''
            """)
            updated_count = cursor.rowcount
            print(f"[MIGRATION] Đã cập nhật {updated_count} questions cũ")
        
        # 6. Tạo indexes mới
        print("[MIGRATION] Tạo indexes mới...")
        
        # Index cho review_status
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_review_status 
                ON questions(review_status)
            """)
            print("[MIGRATION] Đã tạo index: idx_questions_review_status")
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e).lower():
                print(f"[MIGRATION] Warning: {e}")
        
        # Index cho ai_enriched
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_ai_enriched 
                ON questions(ai_enriched)
            """)
            print("[MIGRATION] Đã tạo index: idx_questions_ai_enriched")
        except sqlite3.OperationalError as e:
            if "already exists" not in str(e).lower():
                print(f"[MIGRATION] Warning: {e}")
        
        conn.commit()
        
        if migrations_applied:
            print(f"[MIGRATION] ✅ Hoàn thành! Đã thêm {len(migrations_applied)} columns: {', '.join(migrations_applied)}")
        else:
            print("[MIGRATION] ✅ Tất cả columns đã tồn tại, không cần migration")
        
        return True
        
    except Exception as e:
        print(f"[MIGRATION] ❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)

