from fastapi import Depends, Request, Form, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os
from sqlalchemy.orm import Session
from app.auth import login_required
from app.db import get_db
from app.models import User
from app.utils import get_local_ip
from app.utils import get_local_ip
from app.configs import load_ngrok_config, load_swagger_config, save_ngrok_config, save_swagger_config
from app.cli import package_dir

templates_dir = os.path.join(package_dir, "templates")

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory=templates_dir)

router = APIRouter(prefix="/config", tags=["config"])

@router.post("/swagger")
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

@router.post("/ngrok")
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


@router.post("/users")
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

@router.get("/", response_class=HTMLResponse)
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