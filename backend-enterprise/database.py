from sqlmodel import create_engine, SQLModel, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pole_user:pole_secure_password@localhost:5433/polevision")

# Synchronous engine for simplicity in first pass (Simpler with GeoAlchemy2)
engine = create_engine(DATABASE_URL, echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
