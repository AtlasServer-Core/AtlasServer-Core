#main.py
from fastapi import Depends, WebSocket, APIRouter
from sqlalchemy.orm import Session
import os
from app.db import get_db
from app.models import Application
from app.utils import tail_file

router = APIRouter(prefix="/api/applications", tags=["websockets"])

@router.websocket("/api/applications/{app_id}/stdout-logs/")
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

@router.websocket("/api/applications/{app_id}/stderr-logs/")
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