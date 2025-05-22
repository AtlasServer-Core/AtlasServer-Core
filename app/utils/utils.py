import socket
from app.models import Application
from sqlalchemy.orm import Session
from contextlib import closing
import sys
import os
import subprocess
import json

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No importa si realmente se conecta
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    return local_ip

def check_port_available(port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex(('localhost', port)) != 0

def is_port_assigned_in_db(db: Session, port: int, exclude_app_id: int = None):
    """
    Verifica si un puerto ya está asignado a alguna aplicación en la base de datos,
    excluyendo opcionalmente una aplicación específica.
    """
    query = db.query(Application).filter(Application.port == port)
    
    if exclude_app_id is not None:
        query = query.filter(Application.id != exclude_app_id)
    
    return query.count() > 0

def find_available_port(db: Session, start_port=8000, end_port=9000, exclude_app_id: int = None):
    """
    Encuentra un puerto disponible que no esté en uso en el sistema
    y que no esté asignado a ninguna otra aplicación en la base de datos.
    """
    for port in range(start_port, end_port):
        # Verificar si el puerto está disponible a nivel del sistema
        if check_port_available(port):
            # Verificar si el puerto ya está asignado en la base de datos
            if not is_port_assigned_in_db(db, port, exclude_app_id):
                return port
    return None

def detect_environments(project_directory=None):
    """
    Detecta entornos virtuales disponibles en el sistema y en el directorio del proyecto.
    
    Args:
        project_directory: Directorio del proyecto donde buscar entornos locales
    """
    environments = {
        "system": {
            "name": "Sistema (Global)",
            "path": sys.executable,
            "type": "system"
        }
    }
    
    # Primero, buscar entornos dentro del directorio del proyecto (prioridad alta)
    if project_directory and os.path.exists(project_directory):
        # Nombres comunes de carpetas de entorno virtual
        env_folders = ["venv", ".venv", "env", ".env", "virtualenv", "pyenv"]
        
        for folder in env_folders:
            env_path = os.path.join(project_directory, folder)
            
            # Verificar si existe el entorno
            if os.path.exists(env_path):
                # Determinar la ruta al ejecutable de Python
                if os.name == 'nt':  # Windows
                    python_bin = os.path.join(env_path, "Scripts", "python.exe")
                else:  # Unix/Mac
                    python_bin = os.path.join(env_path, "bin", "python")
                
                if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
                    env_id = f"local:{folder}"
                    environments[env_id] = {
                        "name": f"Entorno del proyecto ({folder})",
                        "path": env_path,
                        "type": "virtualenv",
                        "local": True,
                        "python_bin": python_bin
                    }
                    # Marcar este como preferido
                    environments[env_id]["preferred"] = True
    
    # Detectar entornos virtualenv
    # Buscar en ubicaciones comunes
    venv_paths = [
        os.path.expanduser("~/.virtualenvs"),  # virtualenvwrapper
        os.path.expanduser("~/venvs"),         # ubicación común
        os.path.expanduser("~/virtualenvs"),   # otra ubicación común
    ]
    
    for base_path in venv_paths:
        if os.path.exists(base_path):
            for env_name in os.listdir(base_path):
                env_path = os.path.join(base_path, env_name)
                python_bin = os.path.join(env_path, "bin", "python")
                if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
                    environments[f"virtualenv:{env_name}"] = {
                        "name": f"Virtualenv: {env_name}",
                        "path": env_path,
                        "type": "virtualenv"
                    }
    
    # Detectar entornos conda si conda está instalado
    try:
        conda_output = subprocess.check_output(["conda", "env", "list", "--json"], universal_newlines=True)
        conda_envs = json.loads(conda_output)
        
        for env_path in conda_envs.get("envs", []):
            env_name = os.path.basename(env_path)
            environments[f"conda:{env_name}"] = {
                "name": f"Conda: {env_name}",
                "path": env_path,
                "type": "conda"
            }
    except (subprocess.SubprocessError, FileNotFoundError):
        pass  # Conda no está instalado o no se encuentra
        
    return environments