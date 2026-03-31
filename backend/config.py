"""
config.py - Cấu hình ứng dụng và quản lý environment variables
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file từ root directory
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """Cấu hình ứng dụng"""
    
    
    # ============================================
    # FLASK CONFIGURATION
    # ============================================
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))
    
    # ============================================
    # DATABASE CONFIGURATION
    # ============================================
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'backend/question_bank.db')
    
    # ============================================
    # SECURITY
    # ============================================
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # ============================================
    # AI CONFIGURATION (Gemini API)
    # ============================================
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-pro')
    GEMINI_BATCH_SIZE = int(os.getenv('GEMINI_BATCH_SIZE', '5'))  # Số câu hỏi mỗi batch
    
    # ============================================
    # VALIDATION
    # ============================================
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        
        
        if cls.FLASK_ENV == 'production' and cls.FLASK_DEBUG:
            errors.append("FLASK_DEBUG should be False in production")
        
        if cls.FLASK_ENV == 'production' and cls.SECRET_KEY == 'dev-secret-key-change-in-production':
            errors.append("SECRET_KEY must be changed in production")
        
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
        
        return True
    

