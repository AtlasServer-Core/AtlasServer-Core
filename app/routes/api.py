from fastapi import Depends, HTTPException, APIRouter
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db import get_db
import datetime
import os
import json
import tempfile
import csv
import io
from starlette.background import BackgroundTask
from app.auth import login_required
from app.models import User, Application, Log
import subprocess

router = APIRouter(prefix="/api/applications", tags=["applications_api"])

@router.get("/{app_id}/logs/download")
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


@router.get("/{app_id}/output-logs/download")
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


@router.get("/{app_id}/django-migrations")
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