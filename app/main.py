#main.py

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
import os
import json
import uvicorn
from pydantic import BaseModel
from typing import Optional, List
from starlette import status
from .auth import authenticate_user, create_user, login_required, is_first_run, is_registration_open, get_current_user
from .process_manager import *

# Crear las tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Panel de Administración de Aplicaciones")

NGROK_CONFIG_FILE = "ngrok_config.json"

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

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


@app.get("/api/applications", response_model=List[ApplicationResponse])
def get_applications(db: Session = Depends(get_db), current_user: User = Depends(login_required)):
    applications = db.query(Application).all()
    return applications

@app.post("/api/applications", response_model=ApplicationResponse)
def create_application(application: ApplicationCreate, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    # Validar que el directorio existe
    if not os.path.isdir(application.directory):
        raise HTTPException(status_code=400, detail="El directorio no existe")
    
    # Validar que el archivo principal existe
    main_file_path = os.path.join(application.directory, application.main_file)
    if not os.path.isfile(main_file_path):
        raise HTTPException(status_code=400, detail="El archivo principal no existe")
    
    # Validar el tipo de aplicación
    if application.app_type.lower() not in ["flask", "fastapi"]:
        raise HTTPException(status_code=400, detail="Tipo de aplicación no válido. Debe ser 'flask' o 'fastapi'")
    
    port_int = None
    port = application.port
    request = Request()
    if port and port.strip():
        try:
            port_int = int(port)
            if port_int < 1024 or port_int > 65535:
                return templates.TemplateResponse(
                    "new_application.html", 
                    {"request": request, "error": "El puerto debe estar entre 1024 y 65535", "form_data": locals()},
                    status_code=400
                )
        except ValueError:
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "El puerto debe ser un número entero", "form_data": locals()},
                status_code=400
            )
        
    # Asignar un puerto si no se proporciona
    if port_int is None:
        port_int = find_available_port()
        if not port_int:
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "No se encontraron puertos disponibles", "form_data": locals()},
                status_code=500
            )
    
    # Crear la aplicación en la base de datos
    db_application = Application(
        name=application.name,
        directory=application.directory,
        main_file=application.main_file,
        app_type=application.app_type,
        port=application.port,
        ngrok_enabled=application.ngrok_enabled
    )
    
    db.add(db_application)
    db.commit()
    db.refresh(db_application)
    
    # Añadir log de creación
    log = Log(application_id=db_application.id, message="Aplicación creada", level="info")
    db.add(log)
    db.commit()
    
    return db_application

@app.get("/api/applications/{app_id}", response_model=ApplicationResponse)
def get_application(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    application = db.query(Application).filter(Application.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")
    return application

@app.put("/api/applications/{app_id}", response_model=ApplicationResponse)
def update_application(app_id: int, application: ApplicationUpdate, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    db_application = db.query(Application).filter(Application.id == app_id).first()
    if not db_application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")
    
    # Actualizar los campos proporcionados
    for field, value in application.dict(exclude_unset=True).items():
        setattr(db_application, field, value)
    
    db.commit()
    db.refresh(db_application)
    
    return db_application

@app.delete("/api/applications/{app_id}")
def delete_application(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    db_application = db.query(Application).filter(Application.id == app_id).first()
    if not db_application:
        raise HTTPException(status_code=404, detail="Aplicación no encontrada")
    
    # Detener la aplicación si está en ejecución
    if db_application.status == "running":
        process_manager = ProcessManager(db)
        process_manager.stop_application(app_id)
    
    # Eliminar la aplicación
    db.delete(db_application)
    db.commit()
    
    return {"message": "Aplicación eliminada correctamente"}

@app.post("/api/applications/{app_id}/start")
def start_application(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    result = process_manager.start_application(app_id)
    
    if not result:
        raise HTTPException(status_code=500, detail="No se pudo iniciar la aplicación")
    
    return {"message": "Aplicación iniciada correctamente"}

@app.post("/api/applications/{app_id}/stop")
def stop_application(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    result = process_manager.stop_application(app_id)
    
    if not result:
        raise HTTPException(status_code=500, detail="No se pudo detener la aplicación")
    
    return {"message": "Aplicación detenida correctamente"}

@app.post("/api/applications/{app_id}/restart")
def restart_application(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    result = process_manager.restart_application(app_id)
    
    if not result:
        raise HTTPException(status_code=500, detail="No se pudo reiniciar la aplicación")
    
    return {"message": "Aplicación reiniciada correctamente"}

@app.get("/api/applications/{app_id}/logs", response_model=List[LogResponse])
def get_application_logs(app_id: int, limit: int = 100, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    logs = db.query(Log).filter(Log.application_id == app_id).order_by(Log.timestamp.desc()).limit(limit).all()
    response_logs = []
    for log in logs:
        response_logs.append({
            "id": log.id,
            "message": log.message,
            "level": log.level,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")  # Convertir datetime a string
        })
    
    return response_logs

# Rutas de la interfaz web
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    applications = db.query(Application).all()
    return templates.TemplateResponse("index.html", {"request": request, "applications": applications, "user": current_user})

@app.get("/applications/new", response_class=HTMLResponse)
def new_application_form(request: Request, current_user: User = Depends(login_required)):
    return templates.TemplateResponse("new_application.html", {"request": request, "user": current_user})

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
        
        # Validar que el archivo principal existe
        main_file_path = os.path.join(directory, main_file)
        if not os.path.isfile(main_file_path):
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "El archivo principal no existe", "form_data": locals()},
                status_code=400
            )
        
        # Validar el tipo de aplicación
        if app_type.lower() not in ["flask", "fastapi"]:
            return templates.TemplateResponse(
                "new_application.html", 
                {"request": request, "error": "Tipo de aplicación no válido. Debe ser 'flask' o 'fastapi'", "form_data": locals()},
                status_code=400
            )
        
        # Asignar un puerto si no se proporciona
        if not port:
            port = find_available_port()
            if not port:
                return templates.TemplateResponse(
                    "new_application.html", 
                    {"request": request, "error": "No se encontraron puertos disponibles", "form_data": locals()},
                    status_code=500
                )
        
        # Crear la aplicación en la base de datos
        db_application = Application(
            name=name,
            directory=directory,
            main_file=main_file,
            app_type=app_type,
            port=port,
            ngrok_enabled=ngrok_enabled 
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
            {"request": request, "error": f"Error: {str(e)}", "form_data": locals()},
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

@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    # Verificar que el usuario actual es administrador
    if not current_user.is_admin:
        return RedirectResponse(url="/", status_code=303)
    
    config = load_ngrok_config()
    local_ip = get_local_ip()
    server_port = 5000  # Puerto donde corre AtlasServer
    
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request, 
            "user": current_user,
            "ngrok_token": config.get("token", ""),
            "local_ip": local_ip,
            "server_port": server_port,
            "success_message": request.query_params.get("success", None),
            "user_success_message": request.query_params.get("user_success", None),
            "registration_open": current_user.is_registration_open
        }
    )

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
    
    return RedirectResponse(url="/config?user_success=La configuración de usuarios se ha guardado correctamente", status_code=303)

# Actualizar la ruta de configuración existente para incluir opciones de usuario
@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    # Verificar que el usuario actual es administrador
    if not current_user.is_admin:
        return RedirectResponse(url="/", status_code=303)
    
    config = load_ngrok_config()
    local_ip = get_local_ip()
    server_port = 5000  # Puerto donde corre AtlasServer
    
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request, 
            "ngrok_token": config.get("token", ""),
            "local_ip": local_ip,
            "server_port": server_port,
            "success_message": request.query_params.get("success", None),
            "user_success_message": request.query_params.get("user_success", None),
            "registration_open": current_user.is_registration_open
        }
    )

# Se supone que si lo dejo aqui, funciona?
# Ok, esto funciona si lo dejo aqui, es poco intuitivo pero funciona
app.add_middleware(
    SessionMiddleware,
    secret_key="ajajdhydu",  # Cambia esto a una clave segura en producción
    session_cookie="atlasserver_session",
    max_age=60 * 60 * 24 * 7  # 7 días
)



if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=5000, reload=True)