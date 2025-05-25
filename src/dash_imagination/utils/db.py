import sqlite3
import os

def get_db_connection():
    """Get a connection to the SQLite database."""
    # Determine environment
    is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
    is_chromebook = os.getenv('ENVIRONMENT', 'development') == 'chromebook'
    
    if is_production:
        db_path = "/app/src/dash_imagination/data/imagination.db"
    elif is_chromebook:
        db_path = "/home/yoonsen/Dash_Imagination/src/dash_imagination/data/imagination.db"
    else:
        # Development environment - use the correct path directly
        db_path = "/mnt/disk1/Github/Dash_Imagination/src/dash_imagination/data/imagination.db"
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        raise Exception(f"Could not connect to database at {db_path}: {str(e)}")