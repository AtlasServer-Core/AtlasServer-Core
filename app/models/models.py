from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
import datetime
from app.db import Base
from pydantic import BaseModel
from typing import Optional, List

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    directory = Column(String)
    main_file = Column(String)
    app_type = Column(String)  # "flask" o "fastapi"
    port = Column(Integer, nullable=True)
    status = Column(String, default="stopped")  # "running", "stopped", "error"
    pid = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    logs = relationship("Log", back_populates="application", cascade="all, delete-orphan")
    ngrok_enabled = Column(Boolean, default=False)
    ngrok_url = Column(String, nullable=True)
    environment_type = Column(String, default="system")  # "system", "virtualenv", "conda"
    environment_path = Column(String, nullable=True)     # ruta al entorno virtual o nombre del entorno conda

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    message = Column(String)
    level = Column(String, default="info")  # "info", "error", "warning"
    
    application = relationship("Application", back_populates="logs")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # Almacenaremos contraseñas hasheadas
    is_admin = Column(Boolean, default=True)  # El primer usuario será admin
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_registration_open = Column(Boolean, default=False)  # Control de registro

class ApplicationCreate(BaseModel):
    name: str
    directory: str
    main_file: str
    app_type: str
    port: str | None = None
    ngrok_enabled: bool | None = None

class ApplicationUpdate(BaseModel):
    name: Optional[str] = None
    directory: Optional[str] = None
    main_file: Optional[str] = None
    app_type: Optional[str] = None
    port: Optional[int] = None

class LogResponse(BaseModel):
    id: int
    message: str
    level: str
    timestamp: str

class ApplicationResponse(BaseModel):
    id: int
    name: str
    directory: str
    main_file: str
    app_type: str
    port: Optional[int]
    status: str
    created_at: str
    logs: List[LogResponse] = []