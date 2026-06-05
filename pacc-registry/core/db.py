from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models.database import Base

class DatabaseManager:
    """Handles database connectivity and session management."""

    def __init__(self, db_url: str = "sqlite:///./pacc_registry.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def get_db(self) -> Session:
        """Dependency for FastAPI to provide a DB session per request."""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

db_manager = DatabaseManager()
