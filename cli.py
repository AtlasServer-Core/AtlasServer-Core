#!/usr/bin/env python
# cli.py
import click
import os
import sys
import signal
import subprocess
import time
import json
import psutil
from sqlalchemy.orm import Session

# Aseguramos que la ruta del proyecto esté en el path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importamos módulos del proyecto
from app.process_manager import get_db, Application, ProcessManager


SERVER_PID_FILE = "atlas_server.pid"

def get_server_pid():
    """Obtiene el PID del servidor si está en ejecución"""
    if os.path.exists(SERVER_PID_FILE):
        with open(SERVER_PID_FILE, "r") as f:
            try:
                pid = int(f.read().strip())
                # Verificar si el proceso existe
                try:
                    process = psutil.Process(pid)
                    if "uvicorn" in " ".join(process.cmdline()):
                        return pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            except (ValueError, TypeError):
                pass
    return None


@click.group()
def cli():
    """AtlasServer - CLI para administrar el servidor y aplicaciones."""
    pass


@cli.command("start")
@click.option("--host", default="0.0.0.0", help="Host del servidor")
@click.option("--port", default=5000, help="Puerto del servidor")
@click.option("--reload", is_flag=True, help="Activar recarga automática")
def start_server(host, port, reload):
    """Iniciar el servidor AtlasServer."""
    pid = get_server_pid()
    if pid:
        click.echo(f"⚠️ El servidor ya está en ejecución (PID: {pid})")
        return

    reload_flag = "--reload" if reload else ""
    
    cmd = f"uvicorn app.main:app --host {host} --port {port} {reload_flag}"
    click.echo(f"🚀 Iniciando AtlasServer en {host}:{port}...")
    
    # Iniciar servidor como proceso independiente
    process = subprocess.Popen(
        cmd, 
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True
    )
    
    # Guardar PID
    with open(SERVER_PID_FILE, "w") as f:
        f.write(str(process.pid))
    
    # Esperar un poco para ver si inicia correctamente
    time.sleep(2)
    if process.poll() is None:
        click.echo(f"✅ AtlasServer iniciado correctamente (PID: {process.pid})")
        click.echo(f"📌 Accede a http://{host}:{port}")
    else:
        click.echo("❌ Error al iniciar AtlasServer")
        stdout, stderr = process.communicate()
        click.echo(stderr.decode())


@cli.command("stop")
def stop_server():
    """Detener el servidor AtlasServer."""
    pid = get_server_pid()
    if not pid:
        click.echo("⚠️ AtlasServer no está en ejecución")
        return
    
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        
        # Terminar hijos
        for child in children:
            child.terminate()
        
        # Terminar proceso principal
        parent.terminate()
        
        # Esperar a que terminen los procesos
        gone, alive = psutil.wait_procs(children + [parent], timeout=5)
        
        # Si alguno sigue vivo, lo mata forzosamente
        for p in alive:
            p.kill()
        
        # Eliminar archivo PID
        if os.path.exists(SERVER_PID_FILE):
            os.remove(SERVER_PID_FILE)
            
        click.echo("✅ AtlasServer detenido correctamente")
    except Exception as e:
        click.echo(f"❌ Error al detener AtlasServer: {str(e)}")


@cli.command("status")
def server_status():
    """Verificar el estado del servidor AtlasServer."""
    pid = get_server_pid()
    if pid:
        try:
            process = psutil.Process(pid)
            mem = process.memory_info().rss / (1024 * 1024)
            cpu = process.cpu_percent(interval=0.1)
            
            click.echo(f"✅ AtlasServer está en ejecución")
            click.echo(f"   PID: {pid}")
            click.echo(f"   Memoria: {mem:.2f} MB")
            click.echo(f"   CPU: {cpu:.1f}%")
            click.echo(f"   Tiempo activo: {time.time() - process.create_time():.0f} segundos")
        except psutil.NoSuchProcess:
            click.echo("⚠️ El archivo PID existe pero el proceso no está en ejecución")
            if os.path.exists(SERVER_PID_FILE):
                os.remove(SERVER_PID_FILE)
    else:
        click.echo("❌ AtlasServer no está en ejecución")


# Grupo de comandos para aplicaciones
@cli.group()
def app():
    """Comandos para gestionar aplicaciones."""
    pass


@app.command("list")
def list_apps():
    """Listar todas las aplicaciones registradas."""
    db = next(get_db())
    try:
        apps = db.query(Application).all()
        
        if not apps:
            click.echo("No hay aplicaciones registradas")
            return
        
        click.echo("\n📋 Aplicaciones registradas:")
        click.echo("ID | Nombre | Estado | Tipo | Puerto | PID")
        click.echo("-" * 60)
        
        for app in apps:
            status_icon = "🟢" if app.status == "running" else "⚪" if app.status == "stopped" else "🔴"
            click.echo(f"{app.id} | {app.name} | {status_icon} {app.status} | {app.app_type} | {app.port or 'N/A'} | {app.pid or 'N/A'}")
    finally:
        db.close()


@app.command("start")
@click.argument("app_id", type=int)
def start_app(app_id):
    """Iniciar una aplicación específica."""
    db = next(get_db())
    try:
        process_manager = ProcessManager(db)
        app = db.query(Application).filter(Application.id == app_id).first()
        
        if not app:
            click.echo(f"❌ Aplicación con ID {app_id} no encontrada")
            return
        
        click.echo(f"🚀 Iniciando aplicación '{app.name}'...")
        result = process_manager.start_application(app_id)
        
        if result:
            app = db.query(Application).filter(Application.id == app_id).first()
            click.echo(f"✅ Aplicación iniciada correctamente")
            click.echo(f"   Puerto: {app.port}")
            click.echo(f"   PID: {app.pid}")
            if app.ngrok_url:
                click.echo(f"   URL pública: {app.ngrok_url}")
        else:
            click.echo("❌ Error al iniciar la aplicación")
    finally:
        db.close()


@app.command("stop")
@click.argument("app_id", type=int)
def stop_app(app_id):
    """Detener una aplicación específica."""
    db = next(get_db())
    try:
        process_manager = ProcessManager(db)
        app = db.query(Application).filter(Application.id == app_id).first()
        
        if not app:
            click.echo(f"❌ Aplicación con ID {app_id} no encontrada")
            return
        
        click.echo(f"🛑 Deteniendo aplicación '{app.name}'...")
        result = process_manager.stop_application(app_id)
        
        if result:
            click.echo(f"✅ Aplicación detenida correctamente")
        else:
            click.echo("❌ Error al detener la aplicación")
    finally:
        db.close()


@app.command("restart")
@click.argument("app_id", type=int)
def restart_app(app_id):
    """Reiniciar una aplicación específica."""
    db = next(get_db())
    try:
        process_manager = ProcessManager(db)
        app = db.query(Application).filter(Application.id == app_id).first()
        
        if not app:
            click.echo(f"❌ Aplicación con ID {app_id} no encontrada")
            return
        
        click.echo(f"🔄 Reiniciando aplicación '{app.name}'...")
        result = process_manager.restart_application(app_id)
        
        if result:
            app = db.query(Application).filter(Application.id == app_id).first()
            click.echo(f"✅ Aplicación reiniciada correctamente")
            click.echo(f"   Puerto: {app.port}")
            click.echo(f"   PID: {app.pid}")
        else:
            click.echo("❌ Error al reiniciar la aplicación")
    finally:
        db.close()


@app.command("info")
@click.argument("app_id", type=int)
def app_info(app_id):
    """Mostrar información detallada de una aplicación."""
    db = next(get_db())
    try:
        app = db.query(Application).filter(Application.id == app_id).first()
        
        if not app:
            click.echo(f"❌ Aplicación con ID {app_id} no encontrada")
            return
        
        status_icon = "🟢" if app.status == "running" else "⚪" if app.status == "stopped" else "🔴"
        
        click.echo(f"\n📌 Información de '{app.name}':")
        click.echo(f"   ID: {app.id}")
        click.echo(f"   Estado: {status_icon} {app.status}")
        click.echo(f"   Tipo: {app.app_type}")
        click.echo(f"   Puerto: {app.port or 'No asignado'}")
        click.echo(f"   PID: {app.pid or 'N/A'}")
        click.echo(f"   Directorio: {app.directory}")
        click.echo(f"   Archivo principal: {app.main_file}")
        click.echo(f"   Creada: {app.created_at}")
        
        if app.ngrok_enabled:
            click.echo(f"   Ngrok habilitado: Sí")
            if app.ngrok_url:
                click.echo(f"   URL pública: {app.ngrok_url}")
        
        if app.status == "running" and app.pid:
            try:
                process = psutil.Process(app.pid)
                mem = process.memory_info().rss / (1024 * 1024)
                cpu = process.cpu_percent(interval=0.1)
                
                click.echo(f"\n   Rendimiento:")
                click.echo(f"   - Memoria: {mem:.2f} MB")
                click.echo(f"   - CPU: {cpu:.1f}%")
                click.echo(f"   - Tiempo activo: {time.time() - process.create_time():.0f} segundos")
            except psutil.NoSuchProcess:
                click.echo(f"\n   ⚠️ El PID existe pero el proceso no está en ejecución")
    finally:
        db.close()


if __name__ == "__main__":
    cli()