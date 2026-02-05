"""
Database module for shared PostgreSQL connection.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

# Load env immediately
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

# Database configuration from environment variables
DB_USER = os.getenv('DB_USER', 'directus')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'directus')
DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_DATABASE = os.getenv('DB_DATABASE', 'directus')

# Build connection URL (fallback to QUOTES_DATABASE_URL if set)
DATABASE_URL = os.getenv('QUOTES_DATABASE_URL') or \
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"

# Create engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@contextmanager
def get_db():
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db_session():
    """Generator for FastAPI Depends."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
