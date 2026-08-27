import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# MySQL by default. Override with env var, e.g.
# DATABASE_URL="mysql+pymysql://root:password@localhost:3306/meditrack"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:root@localhost:3306/meditrack",
)

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    engine.connect().close()
except Exception as exc:  # graceful fallback so the demo always runs
    print(f"[MediTrack] MySQL unavailable ({exc}). Falling back to SQLite file meditrack.db")
    DATABASE_URL = "sqlite:///./meditrack.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
