# auth.py
from fastapi import Depends, status, Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.models import User
from app.db import get_db
import os
from platformdirs import user_data_dir
import json
import secrets
from datetime import datetime, timedelta

data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

# Configuración para hasheo de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

SESSIONMIDDLEWARE_FILE = os.path.join(data_dir, "sessionmiddleware.json")

ROTATION_DAYS = 7

# Función para verificar contraseña
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Función para generar hash de contraseña
def get_password_hash(password):
    return pwd_context.hash(password)

# Función para autenticar usuario
def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password):
        return False
    return user

# Función para crear un nuevo usuario
def create_user(db: Session, username: str, password: str, is_admin: bool = False):
    hashed_password = get_password_hash(password)
    db_user = User(
        username=username,
        password=hashed_password,
        is_admin=is_admin
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# Función para obtener el usuario actual desde la sesión
def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    return user

# Middleware para verificar si el usuario está autenticado
async def login_required(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_current_user(request, db)
        if user is None:
            # Usar la redirección asíncrona y forzar la redirección
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        return user
    except Exception as e:
        # Capturar cualquier excepción para evitar bloqueos
        print(f"Error en login_required: {str(e)}")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

# Función para verificar si es la primera ejecución
def is_first_run(db: Session):
    return db.query(User).count() == 0

# Función para verificar si el registro está abierto
def is_registration_open(db: Session):
    admin = db.query(User).filter(User.is_admin == True).first()
    if not admin:
        return True  # Si no hay admin, permitir registro
    return admin.is_registration_open

def load_middleware_config():
    if os.path.exists(SESSIONMIDDLEWARE_FILE):
        try:
            with open(SESSIONMIDDLEWARE_FILE, "r") as f:
                data = json.load(f)
            # Si no es un dict con los campos adecuados, lo descartamos
            if (
                isinstance(data, dict)
                and "token" in data
                and "generated_at" in data
            ):
                gen_time = datetime.fromisoformat(data["generated_at"])
                # Si tiene más de ROTATION_DAYS, forzamos regeneración
                if datetime.utcnow() - gen_time < timedelta(days=ROTATION_DAYS):
                    return data  # token aún válido
        except (json.JSONDecodeError, ValueError):
            pass
    # Si llegamos aquí, hay que generar uno nuevo
    return {"token": None, "generated_at": None}

def save_middleware_config(config):
    with open(SESSIONMIDDLEWARE_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_or_refresh_token():
    print(f"[DEBUG] Entrando en get_or_refresh_token(), ruta de config: {SESSIONMIDDLEWARE_FILE}")
    config = load_middleware_config()
    # Si no había token, o expiró (token es None)
    if not config.get("token"):
        new_token = secrets.token_hex(32)
        config["token"] = new_token
        config["generated_at"] = datetime.utcnow().isoformat()
        save_middleware_config(config)
    return config["token"]