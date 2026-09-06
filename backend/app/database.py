"""
Database engine + session setup.

Reads DATABASE_URL from the environment (see backend/.env.example).
Each teammate points this at their own local MySQL — nothing here
is shared or hardcoded.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL not set. Copy backend/.env.example to backend/.env "
        "and fill in your local MySQL credentials."
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: yields a DB session, closes it after the request.

    Usage in a route:
        from app.database import get_db
        from sqlalchemy.orm import Session
        from fastapi import Depends

        @router.get("/something")
        def something(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
