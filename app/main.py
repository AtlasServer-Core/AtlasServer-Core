#main.py

from fastapi import FastAPI, Depends, HTTPException, Request, Form, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
import os
import json
import tempfile
import csv
import io
import pathlib
import asyncio
from starlette.background import BackgroundTask
import uvicorn
from pydantic import BaseModel
from typing import Optional, List
from starlette import status
from .auth import authenticate_user, create_user, login_required, is_first_run, is_registration_open, get_current_user
from .process_manager import *
import secrets

# Crear las tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Application Administration Panel", docs_url=None, redoc_url=None)

data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

SWAGGER_CONFIG_FILE = os.path.join(data_dir, "swagger_config.json")

def load_swagger_config():
    if os.path.exists(SWAGGER_CONFIG_FILE):
        try:
            with open(SWAGGER_CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {"enabled": False, "username": "", "password": "", "use_admin_credentials": False}
    return {"enabled": False, "username": "", "password": "", "use_admin_credentials": False}

def save_swagger_config(config):
    with open(SWAGGER_CONFIG_FILE, "w") as f:
        json.dump(config, f)


# Definir la ruta completa del archivo de configuración de Ngrok
NGROK_CONFIG_FILE = os.path.join(data_dir, "ngrok_config.json")


package_dir = pathlib.Path(__file__).parent.absolute()
static_dir = os.path.join(package_dir, "static")
templates_dir = os.path.join(package_dir, "templates")

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory=templates_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

security = HTTPBasic()

# Modelos de Pydantic para validación
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

# Funciones para cargar y guardar la configuración de ngrok
def load_ngrok_config():
    if os.path.exists(NGROK_CONFIG_FILE):
        try:
            with open(NGROK_CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_ngrok_config(config):
    with open(NGROK_CONFIG_FILE, "w") as f:
        json.dump(config, f)

async def tail_file(websocket: WebSocket, file_path: str, interval: float = 0.5):
    """
    Lee continuamente las nuevas líneas del archivo y las envía por WebSocket.
    Versión mejorada con depuración.
    """
    print(f"⏳ Iniciando tail_file para {file_path}")
    position = 0
    
    try:
        # Enviar mensaje inicial para confirmar conexión
        await websocket.send_json({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "line": "✓ Conexión establecida, monitoreando logs..."
        })
        
        # Verificar si el archivo existe y establecer posición inicial
        if os.path.exists(file_path):
            position = os.path.getsize(file_path)
            print(f"📄 Archivo encontrado, tamaño inicial: {position} bytes")
            
            # Enviar algunas líneas iniciales para verificar que funciona
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Leer las últimas 10 líneas aproximadamente
                    last_pos = max(0, position - 2000)  # Leer ~2KB del final
                    f.seek(last_pos)
                    # Descartar la primera línea que podría estar incompleta
                    if last_pos > 0:
                        f.readline()
                    # Obtener las últimas líneas
                    last_lines = f.readlines()[-10:]
                    
                    for line in last_lines:
                        line = line.rstrip('\n')
                        if line:
                            await websocket.send_json({
                                "timestamp": datetime.datetime.utcnow().isoformat(),
                                "line": f"[Histórico] {line}"
                            })
                    
                    # Actualizar posición después de leer histórico
                    position = os.path.getsize(file_path)
            except Exception as e:
                print(f"⚠️ Error al leer líneas históricas: {e}")
        else:
            print(f"⚠️ Archivo no existe: {file_path}")
            await websocket.send_json({
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "line": f"⚠️ El archivo de log no existe todavía: {os.path.basename(file_path)}"
            })
        
        # Bucle principal de monitoreo
        while True:
            if os.path.exists(file_path):
                try:
                    current_size = os.path.getsize(file_path)
                    
                    # Si el archivo fue truncado
                    if current_size < position:
                        position = 0
                        print(f"🔄 Archivo truncado, reiniciando desde el principio")
                        await websocket.send_json({
                            "timestamp": datetime.datetime.utcnow().isoformat(),
                            "line": "🔄 Archivo de log truncado, reiniciando lectura..."
                        })
                    
                    # Si hay nuevos datos
                    if current_size > position:
                        print(f"📝 Nuevos datos detectados: {current_size - position} bytes")
                        
                        # Leer usando open() estándar para evitar problemas con aiofiles
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(position)
                            new_content = f.read(current_size - position)
                        
                        # Actualizar posición
                        position = current_size
                        
                        # Procesar y enviar líneas
                        lines = new_content.splitlines()
                        if lines:
                            print(f"📤 Enviando {len(lines)} líneas")
                            
                            for line in lines:
                                if line.strip():
                                    try:
                                        await websocket.send_json({
                                            "timestamp": datetime.datetime.utcnow().isoformat(),
                                            "line": line
                                        })
                                    except Exception as e:
                                        print(f"❌ Error al enviar: {str(e)}")
                                        raise
                except Exception as e:
                    print(f"❌ Error procesando archivo: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    
                    await websocket.send_json({
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "line": f"❌ Error al leer el log: {str(e)}"
                    })
            
            # Esperar antes de la siguiente verificación
            await asyncio.sleep(interval)
            
    except WebSocketDisconnect:
        print("👋 Cliente WebSocket desconectado")
    except Exception as e:
        print(f"💥 Error fatal en tail_file: {str(e)}")
        import traceback
        traceback.print_exc()
        
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass


# Rutas API
@app.middleware("http")
async def authenticate_middleware(request: Request, call_next):
    # Rutas públicas que no requieren autenticación
    public_paths = ["/login", "/register", "/static"]
    
    # Comprobamos si la ruta actual es pública
    is_public = False
    for path in public_paths:
        if request.url.path.startswith(path):
            is_public = True
            break
    
    # Para rutas que requieren autenticación
    if not is_public:
        # Obtener DB de manera más eficiente
        try:
            db = next(get_db())
            
            # Verificar si es la primera ejecución - solo si no hay tablas
            try:
                if is_first_run(db):
                    if request.url.path != "/register":
                        db.close()  # Cerrar explícitamente la conexión
                        return RedirectResponse(url="/register", status_code=status.HTTP_302_FOUND)
                else:
                    # Verificar la autenticación
                    user_id = request.session.get("user_id")
                    if user_id is None:
                        db.close()  # Cerrar explícitamente la conexión
                        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
                    
                    # Verificar que el usuario existe - optimizado para no hacer consultas innecesarias
                    user = db.query(User).filter(User.id == user_id).first()
                    if not user:
                        request.session.clear()
                        db.close()  # Cerrar explícitamente la conexión
                        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
            except Exception as e:
                # Si hay error en la consulta (por ejemplo, si las tablas no existen)
                print(f"Error en middleware de autenticación: {str(e)}")
                db.close()  # Cerrar explícitamente la conexión
                return RedirectResponse(url="/register", status_code=status.HTTP_302_FOUND)
            finally:
                db.close()  # Cerrar siempre la conexión
                
        except Exception as e:
            # Error al obtener la sesión de DB
            print(f"Error al obtener la sesión de DB: {str(e)}")
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # Continuar con la solicitud si todo está bien
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        # Capturar cualquier excepción para evitar que la aplicación se bloquee
        print(f"Error en middleware: {str(e)}")
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/docs", include_in_schema=False)
async def get_documentation(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    # Cargar configuración de Swagger
    swagger_config = load_swagger_config()
    
    if swagger_config.get("enabled", False):
        if swagger_config.get("use_admin_credentials", False):
            # Verificar contra credenciales de administrador
            admin_user = db.query(User).filter(User.is_admin == True).first()
            if admin_user:
                # Verificar si las credenciales coinciden con las del administrador
                is_username_correct = secrets.compare_digest(credentials.username, admin_user.username)
                
                # Para la contraseña, usamos la función de verificación segura
                from .auth import verify_password
                is_password_correct = admin_user and verify_password(credentials.password, admin_user.password)
                
                if not (is_username_correct and is_password_correct):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Credenciales incorrectas",
                        headers={"WWW-Authenticate": "Basic"},
                    )
        else:
            # Verificar contra credenciales configuradas
            correct_username = swagger_config.get("username", "")
            correct_password = swagger_config.get("password", "")
            
            is_username_correct = secrets.compare_digest(credentials.username, correct_username)
            is_password_correct = secrets.compare_digest(credentials.password, correct_password)
            
            if not (is_username_correct and is_password_correct):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas",
                    headers={"WWW-Authenticate": "Basic"},
                )
    
    # Si llegamos aquí, la autenticación fue exitosa o no está habilitada
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="AtlasServer - API Documentation"
    )

@app.get("/redoc", include_in_schema=False)
async def get_redoc(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    # Mismo código de verificación que en /docs
    swagger_config = load_swagger_config()
    
    if swagger_config.get("enabled", False):
        if swagger_config.get("use_admin_credentials", False):
            # Verificar contra credenciales de administrador
            admin_user = db.query(User).filter(User.is_admin == True).first()
            if admin_user:
                # Verificar si las credenciales coinciden con las del administrador
                is_username_correct = secrets.compare_digest(credentials.username, admin_user.username)
                
                # Para la contraseña, usamos la función de verificación segura
                from .auth import verify_password
                is_password_correct = admin_user and verify_password(credentials.password, admin_user.password)
                
                if not (is_username_correct and is_password_correct):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Credenciales incorrectas",
                        headers={"WWW-Authenticate": "Basic"},
                    )
        else:
            # Verificar contra credenciales configuradas
            correct_username = swagger_config.get("username", "")
            correct_password = swagger_config.get("password", "")
            
            is_username_correct = secrets.compare_digest(credentials.username, correct_username)
            is_password_correct = secrets.compare_digest(credentials.password, correct_password)
            
            if not (is_username_correct and is_password_correct):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas",
                    headers={"WWW-Authenticate": "Basic"},
                )
    
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="AtlasServer - API Documentation"
    )


# En app/main.py - añadir después de la ruta para ngrok
@app.post("/config/swagger")
def save_swagger_auth_config(
    request: Request,
    swagger_enabled: bool = Form(False),
    use_admin_credentials: bool = Form(False),
    swagger_username: str = Form(""),
    swagger_password: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required)
):
    # Verificar que el usuario actual es administrador
    if not current_user.is_admin:
        return RedirectResponse(url="/", status_code=303)
    
    # Cargar configuración actual
    config = load_swagger_config()
    
    # Actualizar configuración
    config["enabled"] = swagger_enabled
    config["use_admin_credentials"] = use_admin_credentials
    config["username"] = swagger_username if swagger_username else config.get("username", "")
    
    # Solo actualizar password si se proporciona uno nuevo
    if swagger_password:
        config["password"] = swagger_password
    
    # Guardar configuración
    save_swagger_config(config)
    
    return RedirectResponse(
        url="/config?swagger_success=The API documentation configuration has been saved successfully.", 
        status_code=303
    )



@app.get("/api/applications/{app_id}/logs/download")
def download_application_logs(
    app_id: int, 
    format: str = "csv", 
    current_user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    logs = db.query(Log).filter(Log.application_id == app_id).order_by(Log.timestamp.desc()).all()
    
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")
    
    filename = f"{application.name}_logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    if format.lower() == "json":
        # Crear archivo JSON para descargar
        logs_data = []
        for log in logs:
            logs_data.append({
                "id": log.id,
                "message": log.message,
                "level": log.level,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        with open(temp_file.name, "w", encoding="utf-8") as f:
            json.dump(logs_data, f, indent=2, ensure_ascii=False)
        
        return FileResponse(
            path=temp_file.name, 
            filename=f"{filename}.json",
            media_type="application/json",
            background=BackgroundTask(lambda: os.unlink(temp_file.name))
        )
    
    else:  # CSV por defecto
        # Crear archivo CSV para descargar
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Fecha", "Nivel", "Mensaje"])
        
        for log in logs:
            writer.writerow([
                log.id,
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                log.level,
                log.message
            ])
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        with open(temp_file.name, "w", encoding="utf-8") as f:
            f.write(output.getvalue())
        
        return FileResponse(
            path=temp_file.name, 
            filename=f"{filename}.csv",
            media_type="text/csv",
            background=BackgroundTask(lambda: os.unlink(temp_file.name))
        )


@app.get("/api/applications/{app_id}/output-logs/download")
def download_application_output_logs(
    app_id: int, 
    log_type: str = "stdout", 
    current_user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")
    
    log_file = os.path.join(application.directory, "logs", f"{log_type}.log")
    if not os.path.exists(log_file):
        raise HTTPException(status_code=404, detail=f"Archivo de logs {log_type}.log no encontrado")
    
    filename = f"{application.name}_{log_type}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    return FileResponse(
        path=log_file,
        filename=filename,
        media_type="text/plain"
    )

@app.websocket("/api/applications/{app_id}/stdout-logs/")
async def api_stdout_logs(
    websocket: WebSocket,
    app_id: int,
    db: Session = Depends(get_db)
):
    # Aceptar la conexión WebSocket
    await websocket.accept()
    # Validar existencia de la aplicación
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        await websocket.close(code=1008, reason="Aplicación no encontrada")
        return
    # Ruta del archivo stdout.log
    log_file = os.path.join(application.directory, "logs", "stdout.log")
    if not os.path.exists(log_file):
        await websocket.close(code=1008, reason="stdout.log no encontrado")
        return
    # Iniciar streaming del archivo
    await tail_file(websocket, log_file)

@app.websocket("/api/applications/{app_id}/stderr-logs/")
async def api_stderr_logs(
    websocket: WebSocket,
    app_id: int,
    db: Session = Depends(get_db)
):
    await websocket.accept()
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        await websocket.close(code=1008, reason="Aplicación no encontrada")
        return
    log_file = os.path.join(application.directory, "logs", "stderr.log")
    if not os.path.exists(log_file):
        await websocket.close(code=1008, reason="stderr.log no encontrado")
        return
    await tail_file(websocket, log_file)

@app.get("/api/detect-environments")
def api_detect_environments(
    directory: str, 
    current_user: User = Depends(login_required)
):
    import os
    import sys
    import glob
    import json
    import subprocess
    from pathlib import Path
    
    if not os.path.exists(directory):
        return {"success": False, "error": "El directorio no existe"}
    
    # Log para depuración
    print(f"🔍 Buscando entornos en: {directory}")
    
    # Definimos un diccionario básico con el entorno del sistema
    environments = {
        "system": {
            "name": "Sistema (Global)",
            "path": sys.executable,
            "type": "system"
        }
    }
    
    # Función para verificar si una ruta es un entorno Python válido
    def is_valid_python_env(path, env_type="virtualenv"):
        """Verifica si la ruta contiene un entorno Python válido."""
        if not os.path.exists(path):
            print(f"  ❌ Ruta no existe: {path}")
            return False
            
        # Determinar la ruta al ejecutable de Python según el sistema
        if os.name == 'nt':  # Windows
            python_bin = os.path.join(path, "Scripts", "python.exe")
        else:  # Unix/Mac
            python_bin = os.path.join(path, "bin", "python")
        
        # Verificar si existe el ejecutable y tiene permisos
        if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
            print(f"  ✅ Entorno válido encontrado: {path} ({env_type})")
            return {
                "path": path,
                "type": env_type,
                "python_bin": python_bin
            }
        
        print(f"  ❌ No es un entorno válido: {path}")
        return False
    
    # ===== 1. BUSCAR ENTORNOS VIRTUALES ESTÁNDAR =====
    env_folders = ["venv", ".venv", "env", ".env", "virtualenv", "pyenv"]
    project_dir = Path(directory)
    
    # Buscar en el directorio principal
    print("🔎 Buscando entornos virtuales estándar...")
    for folder in env_folders:
        env_path = os.path.join(directory, folder)
        env_info = is_valid_python_env(env_path)
        
        if env_info:
            env_id = f"local:{folder}"
            environments[env_id] = {
                "name": f"Entorno del proyecto ({folder})",
                "path": env_path,
                "type": "virtualenv",
                "local": True,
                "python_bin": env_info["python_bin"],
                "preferred": True
            }
    
    # ===== 2. BUSCAR CARPETAS QUE CONTENGAN "ENV" EN SU NOMBRE =====
    print("🔎 Buscando carpetas con 'env' en su nombre...")
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        # Verificar si es un directorio y si contiene 'env' en su nombre (case insensitive)
        if os.path.isdir(item_path) and 'env' in item.lower() and item.lower() not in [f.lower() for f in env_folders]:
            env_info = is_valid_python_env(item_path, "custom_env")
            if env_info:
                env_id = f"custom:{item}"
                environments[env_id] = {
                    "name": f"Entorno personalizado ({item})",
                    "path": item_path,
                    "type": "virtualenv",
                    "local": True,
                    "python_bin": env_info["python_bin"],
                    "preferred": True  # También les damos alta prioridad
                }
    
    # ===== 3. BUSCAR CONFIGURACIÓN DE POETRY =====
    print("🔎 Buscando entornos Poetry...")
    poetry_lock = os.path.join(directory, "poetry.lock")
    pyproject_toml = os.path.join(directory, "pyproject.toml")
    
    if os.path.exists(poetry_lock) or os.path.exists(pyproject_toml):
        print("  📄 Configuración Poetry detectada")
        # Poetry normalmente usa .venv en el directorio del proyecto
        poetry_venv = os.path.join(directory, ".venv")
        env_info = is_valid_python_env(poetry_venv, "poetry")
        
        if env_info:
            environments["local:poetry"] = {
                "name": "Entorno Poetry (.venv)",
                "path": poetry_venv,
                "type": "poetry",
                "local": True,
                "python_bin": env_info["python_bin"],
                "preferred": True
            }
    
    # ===== 4. BUSCAR PIPENV =====
    print("🔎 Buscando entornos Pipenv...")
    pipfile = os.path.join(directory, "Pipfile")
    
    if os.path.exists(pipfile):
        print("  📄 Pipfile detectado, intentando localizar entorno...")
        try:
            # Intentar obtener la ubicación del entorno Pipenv
            result = subprocess.run(
                ["pipenv", "--venv"],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                pipenv_path = result.stdout.strip()
                print(f"  📍 Entorno Pipenv encontrado en: {pipenv_path}")
                
                env_info = is_valid_python_env(pipenv_path, "pipenv")
                if env_info:
                    environments["local:pipenv"] = {
                        "name": "Entorno Pipenv",
                        "path": pipenv_path,
                        "type": "pipenv",
                        "local": True,
                        "python_bin": env_info["python_bin"],
                        "preferred": True
                    }
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"  ⚠️ Error al detectar entorno Pipenv: {e}")
    
    # ===== 5. BUSCAR ENTORNOS CONDA =====
    print("🔎 Buscando entornos Conda...")
    environment_yml = os.path.join(directory, "environment.yml")
    conda_env_dir = None
    
    if os.path.exists(environment_yml):
        print("  📄 Archivo environment.yml de Conda detectado")
        
        try:
            # Intentar obtener el nombre del entorno desde environment.yml
            with open(environment_yml, 'r') as f:
                import yaml
                try:
                    env_config = yaml.safe_load(f)
                    conda_env_name = env_config.get('name')
                    
                    if conda_env_name:
                        print(f"  🐍 Nombre del entorno Conda: {conda_env_name}")
                        
                        # Intentar localizar el entorno conda
                        try:
                            result = subprocess.run(
                                ["conda", "env", "list", "--json"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            
                            if result.returncode == 0:
                                conda_envs = json.loads(result.stdout)
                                
                                for env_path in conda_envs.get("envs", []):
                                    env_name = os.path.basename(env_path)
                                    
                                    if env_name == conda_env_name:
                                        conda_env_dir = env_path
                                        break
                                
                                if conda_env_dir:
                                    print(f"  ✅ Entorno Conda encontrado: {conda_env_dir}")
                                    
                                    # En Conda, el binario de Python está en diferentes lugares según el sistema
                                    if os.name == 'nt':  # Windows
                                        python_bin = os.path.join(conda_env_dir, "python.exe")
                                    else:  # Unix/Mac
                                        python_bin = os.path.join(conda_env_dir, "bin", "python")
                                    
                                    if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
                                        environments[f"conda:{conda_env_name}"] = {
                                            "name": f"Entorno Conda ({conda_env_name})",
                                            "path": conda_env_dir,
                                            "type": "conda",
                                            "local": True,
                                            "python_bin": python_bin,
                                            "preferred": True
                                        }
                        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError) as e:
                            print(f"  ⚠️ Error al buscar entorno Conda: {e}")
                except yaml.YAMLError:
                    print("  ⚠️ No se pudo parsear environment.yml")
        except Exception as e:
            print(f"  ⚠️ Error al leer environment.yml: {e}")
    
    # ===== 6. BÚSQUEDA RECURSIVA DE ENTORNOS EN SUBDIRECTORIOS (con límite) =====
    print("🔎 Buscando entornos en subdirectorios (profundidad limitada)...")
    
    max_depth = 2  # Máxima profundidad de búsqueda
    searched_dirs = set()  # Para evitar búsquedas duplicadas
    
    def search_envs_in_subdirs(base_path, current_depth=0):
        if current_depth > max_depth or base_path in searched_dirs:
            return
            
        searched_dirs.add(base_path)
        
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                
                # Saltar directorios ya conocidos como entornos
                if any(env.get("path") == item_path for env in environments.values()):
                    continue
                    
                # Saltar directorios comunes que no contienen entornos
                if item in [".git", "node_modules", "__pycache__", "dist", "build"]:
                    continue
                
                # Comprobar si es un directorio
                if os.path.isdir(item_path):
                    # Verificar si este directorio parece un entorno virtual
                    # Ahora también detectamos nombres que contengan "env"
                    if item in env_folders or 'env' in item.lower():
                        env_info = is_valid_python_env(item_path)
                        if env_info:
                            rel_path = os.path.relpath(item_path, directory)
                            env_id = f"subdir:{rel_path}"
                            environments[env_id] = {
                                "name": f"Entorno en subdirectorio ({rel_path})",
                                "path": item_path,
                                "type": "virtualenv",
                                "local": True,
                                "python_bin": env_info["python_bin"],
                                "preferred": False
                            }
                    
                    # Buscar recursivamente, pero sólo en subdirectorios que podrían contener código
                    search_envs_in_subdirs(item_path, current_depth + 1)
        except PermissionError:
            print(f"  ⚠️ Sin permisos para leer {base_path}")
        except Exception as e:
            print(f"  ⚠️ Error al explorar {base_path}: {e}")
    
    # Iniciar búsqueda recursiva
    search_envs_in_subdirs(directory)
    
    # ===== 7. ENCONTRAR ENTORNO PREFERIDO =====
    preferred_env = None
    preferred_priority = {
        "local:.venv": 10,      # .venv en el directorio del proyecto (convención moderna)
        "local:venv": 9,        # venv en el directorio del proyecto
        "local:poetry": 8,      # Entorno poetry
        "local:pipenv": 7,      # Entorno pipenv
        "conda:": 6,            # Entornos conda (prefijo)
        "local:env": 5,         # Otros entornos en el directorio
        "custom:": 5,           # Entornos personalizados con "env" en el nombre
        "subdir:": 4,           # Entornos en subdirectorios (prefijo)
    }
    
    highest_priority = -1
    
    for env_id, env in environments.items():
        if env_id == "system":
            continue
            
        priority = 0
        
        # Buscar prioridad exacta
        if env_id in preferred_priority:
            priority = preferred_priority[env_id]
        else:
            # Buscar prioridad por prefijo
            for prefix, prio in preferred_priority.items():
                if env_id.startswith(prefix):
                    priority = prio
                    break
        
        if priority > highest_priority:
            highest_priority = priority
            preferred_env = env_id
            
    print(f"🏆 Entorno preferido: {preferred_env}")
    print(f"🔢 Total de entornos encontrados: {len(environments)}")

    return {
        "success": True,
        "environments": environments,
        "preferred": preferred_env
    }

# Nueva API para Django
@app.get("/api/applications/{app_id}/django-migrations")
async def check_django_migrations(
    app_id: int,
    current_user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    """Verifica el estado de las migraciones de una aplicación Django"""
    
    # Obtener la aplicación
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")
    
    # Verificar que sea una aplicación Django
    if application.app_type.lower() != "django":
        raise HTTPException(status_code=400, detail="La aplicación no es de tipo Django")
    
    try:
        # Preparar entorno
        env = os.environ.copy()
        python_cmd = "python"  # Por defecto
        
        # Manejar entornos virtuales si está configurado
        if application.environment_type != "system" and application.environment_path:
            if application.environment_type == "virtualenv":
                if os.name == 'nt':  # Windows
                    python_cmd = os.path.join(application.environment_path, "Scripts", "python.exe")
                else:  # Unix/Mac
                    python_cmd = os.path.join(application.environment_path, "bin", "python")
        
        # Ejecutar comando para verificar migraciones
        result = subprocess.run(
            [python_cmd, "manage.py", "showmigrations", "--list"],
            cwd=application.directory,
            env=env,
            capture_output=True,
            text=True
        )
        
        # Procesar la salida
        migrations = []
        
        if result.returncode == 0:
            # Analizar la salida del comando showmigrations
            current_app = None
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                
                # Línea de aplicación
                if line and not line.startswith('['):
                    current_app = line
                
                # Línea de migración
                elif line.startswith('['):
                    applied = '[X]' in line
                    name = line.split(']', 1)[1].strip()
                    
                    migrations.append({
                        "app": current_app,
                        "name": name,
                        "applied": applied
                    })
            
            # Incluir mensaje sobre migraciones pendientes
            pending_count = sum(1 for m in migrations if not m["applied"])
            status_message = "Todas las migraciones aplicadas" if pending_count == 0 else f"{pending_count} migraciones pendientes"
            
            return {
                "success": True,
                "migrations": migrations,
                "status": status_message,
                "pending_count": pending_count
            }
        else:
            # Error al ejecutar el comando
            error_msg = result.stderr or "Error desconocido al verificar migraciones"
            return {
                "success": False,
                "error": error_msg,
                "migrations": []
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "migrations": []
        }


# Rutas de la interfaz web
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    applications = db.query(Application).all()
    return templates.TemplateResponse("index.html", {"request": request, "applications": applications, "user": current_user})

@app.get("/applications/new", response_class=HTMLResponse)
def new_application_form(request: Request, current_user: User = Depends(login_required)):
    # Ok toca iniciar esto asi, porque si no la ruta no funciona, ya buscare otra forma de iniciar correctamente
    environments = {
        "system": {
            "name": "Sistema (Global)",
            "path": sys.executable,
            "type": "system"
        }
    }
    return templates.TemplateResponse("new_application.html", {"request": request, "user": current_user, "environments": environments})

@app.post("/applications/new")
def create_application_form(
    request: Request,
    name: str = Form(...),
    directory: str = Form(...),
    main_file: str = Form(...),
    app_type: str = Form(...),
    port: Optional[str] = Form(None),
    ngrok_enabled: bool = Form(False),  # Nuevo campo como checkbox
    current_user: User = Depends(login_required),
    environment_type: str = Form("system"),
    db: Session = Depends(get_db)
):
    try:
        # Validar que el directorio existe
        if not os.path.isdir(directory):
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "El directorio no existe", "form_data": locals()},
                status_code=400
            )

        env_type = "system"
        env_path = None
    
        if environment_type != "system":
            env_parts = environment_type.split(":", 1)
            if len(env_parts) == 2:
                env_type, env_name = env_parts
            
                # Obtener la ruta real del entorno
                environments = detect_environments()
                if environment_type in environments:
                    env_path = environments[environment_type]["path"]
        
        # Validar que el archivo principal existe
        main_file_path = os.path.join(directory, main_file)
        if not os.path.isfile(main_file_path):
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "El archivo principal no existe", "form_data": locals(), "user": current_user},
                status_code=400
            )
        
        # Validar el tipo de aplicación
        if app_type.lower() not in ["flask", "fastapi", "django"]:
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "Tipo de aplicación no válido. Debe ser 'flask' o 'fastapi'", "form_data": locals(), "user": current_user},
                status_code=400
            )
        
        # Asignar un puerto si no se proporciona
        if not port:
            port = find_available_port(db=db)
            if not port:
                return templates.TemplateResponse(
                    "new_application.html", 
                    {"request": request, "error": "No se encontraron puertos disponibles", "form_data": locals(), "user": current_user},
                    status_code=500
                )
        
        # Crear la aplicación en la base de datos
        db_application = Application(
            name=name,
            directory=directory,
            main_file=main_file,
            app_type=app_type,
            port=port,
            ngrok_enabled=ngrok_enabled,
            environment_type=env_type,
            environment_path=env_path 
        )
        
        db.add(db_application)
        db.commit()
        
        # Añadir log de creación
        log = Log(application_id=db_application.id, message="Aplicación creada", level="info")
        db.add(log)
        db.commit()
        
        return RedirectResponse(url="/", status_code=303)
        
    except Exception as e:
        return templates.TemplateResponse(
            "new_application.html", 
            {"request": request, "error": f"Error: {str(e)}", "form_data": locals(), "user": current_user},
            status_code=500
        )

@app.get("/applications/{app_id}", response_class=HTMLResponse)
def view_application(app_id: int, request: Request, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        return RedirectResponse(url="/", status_code=303)
    
    logs = db.query(Log).filter(Log.application_id == app_id).order_by(Log.timestamp.desc()).limit(50).all()
    
    # Verificar el estado real de la aplicación
    process_manager = ProcessManager(db)
    process_manager.check_application_status(app_id)
    
    # Recargar los datos de la aplicación después de verificar el estado
    application = db.query(Application).filter(Application.id == app_id).first()
    
    # Obtener la IP local para mostrarla en la plantilla
    local_ip = get_local_ip()
    
    return templates.TemplateResponse(
        "view_application.html", 
        {
            "request": request, 
            "application": application, 
            "logs": logs,
            "local_ip": local_ip,
            "user": current_user
        }
    )

@app.get("/applications/{app_id}/logs", response_class=HTMLResponse)
async def application_logs_page(
    request: Request,
    app_id: int,
    current_user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    # Busca la aplicación
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")

    # Renderiza el template que creaste (logs.html)
    return templates.TemplateResponse(
        "logs_terminal.html",
        {
            "request": request,
            "application": application,
            "user": current_user
        }
    )

@app.post("/applications/{app_id}/start")
def start_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    process_manager.start_application(app_id)
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)

@app.post("/applications/{app_id}/stop")
def stop_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    process_manager.stop_application(app_id)
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)

@app.post("/applications/{app_id}/restart")
def restart_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    process_manager.restart_application(app_id)
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)

@app.post("/applications/{app_id}/delete")
def delete_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    db_application = db.query(Application).filter(Application.id == app_id).first()
    if db_application:
        # Detener la aplicación si está en ejecución
        if db_application.status == "running":
            process_manager = ProcessManager(db)
            process_manager.stop_application(app_id)
        
        # Eliminar la aplicación
        db.delete(db_application)
        db.commit()
    
    return RedirectResponse(url="/", status_code=303)



@app.post("/config/ngrok")
def save_ngrok_token(
    request: Request,
    current_user: User = Depends(login_required),
    ngrok_token: str = Form(...)
):
    config = load_ngrok_config()
    config["token"] = ngrok_token
    save_ngrok_config(config)
    
    # También podemos configurarlo inmediatamente
    try:
        from pyngrok import conf
        conf.get_default().auth_token = ngrok_token
    except ImportError:
        pass  # pyngrok no está instalado
    
    return RedirectResponse(url="/config?success=El token de ngrok ha sido guardado correctamente", status_code=303)

@app.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    # Si ya está autenticado, redirigir a la página principal
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=303)
    
    # Si es la primera ejecución, redirigir al registro
    if is_first_run(db):
        return RedirectResponse(url="/register", status_code=303)
    
    # Verificar si el registro está abierto
    registration_open = is_registration_open(db)
    
    return templates.TemplateResponse(
        "login.html", 
        {"request": request, "registration_open": registration_open}
    )

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, username, password)
    
    if not user:
        return templates.TemplateResponse(
            "login.html", 
            {
                "request": request, 
                "error": "Usuario o contraseña incorrectos",
                "registration_open": is_registration_open(db)
            },
            status_code=400
        )
    
    # Guardar el ID de usuario en la sesión
    request.session["user_id"] = user.id
    
    return RedirectResponse(url="/", status_code=303)

@app.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    # Si ya está autenticado, redirigir a la página principal
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=303)
    
    # Verificar si es la primera ejecución o si el registro está abierto
    first_run = is_first_run(db)
    if not first_run and not is_registration_open(db):
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse(
        "register.html", 
        {"request": request, "is_first_run": first_run}
    )

@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    allow_registration: bool = Form(False),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db)
):
    # Verificar si es la primera ejecución
    first_run = is_first_run(db)
    
    # Si no es la primera ejecución y el registro no está abierto, redirigir
    if not first_run and not is_registration_open(db):
        return RedirectResponse(url="/login", status_code=303)
    
    # Verificar que las contraseñas coincidan
    if password != password_confirm:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request, 
                "error": "Las contraseñas no coinciden",
                "is_first_run": first_run
            },
            status_code=400
        )
    
    # Verificar si el usuario ya existe
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request, 
                "error": "El nombre de usuario ya está en uso",
                "is_first_run": first_run
            },
            status_code=400
        )
    
    # Si es la primera ejecución, el usuario es admin
    if first_run:
        is_admin = True
    
    # Crear el usuario
    user = create_user(db, username, password, is_admin)
    
    # Si es admin y es la primera ejecución, configurar si se permite registro
    if is_admin and first_run:
        user.is_registration_open = allow_registration
        db.commit()
    
    # Iniciar sesión automáticamente
    request.session["user_id"] = user.id
    
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    # Limpiar la sesión
    request.session.clear()
    
    return RedirectResponse(url="/login", status_code=303)

# Ruta de configuración de usuarios
@app.post("/config/users")
def save_user_config(
    request: Request,
    allow_registration: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(login_required)
):
    # Verificar que el usuario actual es administrador
    if not current_user.is_admin:
        return RedirectResponse(url="/", status_code=303)
    
    # Actualizar la configuración
    current_user.is_registration_open = allow_registration
    db.commit()
    
    return RedirectResponse(url="/config?user_success=User settings have been saved successfully", status_code=303)


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    # Verificar que el usuario actual es administrador
    if not current_user.is_admin:
        return RedirectResponse(url="/", status_code=303)
    
    # Cargar configuraciones
    ngrok_config = load_ngrok_config()
    swagger_config = load_swagger_config()
    
    local_ip = get_local_ip()
    server_port = 5000  # Puerto donde corre AtlasServer
    
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request, 
            "user": current_user,
            "ngrok_token": ngrok_config.get("token", ""),
            "local_ip": local_ip,
            "server_port": server_port,
            "success_message": request.query_params.get("success", None),
            "user_success_message": request.query_params.get("user_success", None),
            "swagger_success_message": request.query_params.get("swagger_success", None),
            "registration_open": current_user.is_registration_open,
            # Configuración de Swagger
            "swagger_enabled": swagger_config.get("enabled", False),
            "use_admin_credentials": swagger_config.get("use_admin_credentials", False),
            "swagger_username": swagger_config.get("username", ""),
            "swagger_password": swagger_config.get("password", ""),
        }
    )

# Se supone que si lo dejo aqui, funciona?
# Ok, esto funciona si lo dejo aqui, es poco intuitivo pero funciona
app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_hex(32),  # Cambia esto a una clave segura en producción
    session_cookie="atlasserver_session",
    max_age=60 * 60 * 24 * 7  # 7 días
)



if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)