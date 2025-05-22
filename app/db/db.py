import os
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from platformdirs import user_data_dir


data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(data_dir, 'applications.db')}"
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=sqlalchemy.pool.QueuePool,
    pool_size=20,
    max_overflow=20,
    pool_timeout=60,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Función para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()