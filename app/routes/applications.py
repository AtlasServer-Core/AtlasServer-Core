from fastapi import Depends, Request, Form, APIRouter
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from typing import Optional
from app.auth import login_required
from app.db import get_db
from app.models import User, Application, Log
from app.services import ProcessManager
from app.utils import find_available_port, detect_environments
from app.cli import package_dir

templates_dir = os.path.join(package_dir, "templates")

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory=templates_dir)

router = APIRouter(prefix="/applications", tags=["applications"])

@router.post("/new")
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

@router.post("/{app_id}/start")
def start_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    process_manager.start_application(app_id)
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)

@router.post("/{app_id}/stop")
def stop_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    process_manager.stop_application(app_id)
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)

@router.post("/{app_id}/restart")
def restart_application_form(app_id: int, current_user: User = Depends(login_required), db: Session = Depends(get_db)):
    process_manager = ProcessManager(db)
    process_manager.restart_application(app_id)
    return RedirectResponse(url=f"/applications/{app_id}", status_code=303)

@router.post("/{app_id}/delete")
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