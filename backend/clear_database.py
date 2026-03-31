"""
Script để xóa tất cả dữ liệu trong question_bank.db
Giữ nguyên cấu trúc bảng, chỉ xóa dữ liệu
"""

import sqlite3
import os
from pathlib import Path

def clear_database(db_path: str = None):
    """Xóa tất cả dữ liệu trong database"""
    
    # Nếu không có đường dẫn, tự động tìm trong cùng thư mục với script
    if db_path is None:
        script_dir = Path(__file__).parent.absolute()
        db_path = str(script_dir / "question_bank.db")
    
    db_path_obj = Path(db_path)
    
    if not db_path_obj.exists():
        print(f"Database {db_path} không tồn tại!")
        print(f"Đang tìm tại: {db_path_obj.absolute()}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Tắt foreign key checks tạm thời
        cursor.execute("PRAGMA foreign_keys = OFF")
        
        # Xóa dữ liệu theo thứ tự (từ bảng con đến bảng cha)
        tables = [
            'exam_questions',      # Bảng liên kết
            'generation_logs',     # Logs
            'questions',           # Câu hỏi
            'exams',               # Đề thi
            'solvers',             # Solvers
            'templates',           # Templates
            'categories',          # Categories
            'sqlite_sequence',
            'subjects' #Bảng hệ thống SQLite (AUTOINCREMENT)
        ]
        
        deleted_counts = {}
        for table in tables:
            try:
                # Kiểm tra xem bảng có tồn tại không
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if cursor.fetchone():
                    cursor.execute(f"DELETE FROM {table}")
                    count = cursor.rowcount
                    deleted_counts[table] = count
                    print(f"Đã xóa {count} bản ghi từ bảng {table}")
                else:
                    print(f"Bảng {table} không tồn tại, bỏ qua")
                    deleted_counts[table] = 0
            except Exception as e:
                print(f"Lỗi khi xóa bảng {table}: {e}")
                deleted_counts[table] = 0
        
        # Bật lại foreign key checks
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Commit thay đổi
        conn.commit()
        
        print("\n" + "="*50)
        print("Đã xóa tất cả dữ liệu thành công!")
        print("="*50)
        print("\nTổng kết:")
        total = sum(deleted_counts.values())
        print(f"Tổng số bản ghi đã xóa: {total}")
        for table, count in deleted_counts.items():
            if count > 0:
                print(f"  - {table}: {count} bản ghi")
        
    except Exception as e:
        conn.rollback()
        print(f"Lỗi khi xóa dữ liệu: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Tự động tìm file database trong cùng thư mục với script
    clear_database()
    print("\nBạn có thể thêm dữ liệu mới qua giao diện chính của mình.")

