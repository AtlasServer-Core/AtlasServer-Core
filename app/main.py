#main.py

import logging
from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware import Middleware
from sqlalchemy.orm import Session
import os
import pathlib
import uvicorn
from starlette import status
from app.auth import authenticate_user, create_user, login_required, is_first_run, is_registration_open, get_current_user
from app.db import engine, Base, get_db
from app.models import User, Application, Log
from app.services import ProcessManager
from app.utils import get_local_ip
import sys
import secrets
from platformdirs import user_data_dir
from app.utils import get_local_ip
from app.configs import load_swagger_config
from app.auth import get_or_refresh_token
from app.routes import websockets, api, applications, configroutes, enviro
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

secret = get_or_refresh_token()


app = FastAPI(title="Application Administration Panel", docs_url=None, redoc_url=None)
app.include_router(websockets.router)
app.include_router(api.router)
app.include_router(applications.router)
app.include_router(configroutes.router)
app.include_router(enviro.router)

data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

package_dir = pathlib.Path(__file__).parent.absolute()
static_dir = os.path.join(package_dir, "static")
templates_dir = os.path.join(package_dir, "templates")

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory=templates_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

security = HTTPBasic()


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
                from app.auth import verify_password
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
                from app.auth import verify_password
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


app.add_middleware(
    SessionMiddleware,
    secret_key=secret,  # Cambia esto a una clave segura en producción
    session_cookie="atlasserver_session",
    max_age=60 * 60 * 24 * 7  # 7 días
)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)