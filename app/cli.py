#!/usr/bin/env python
# app/cli.py
import click
import os
import subprocess
import time
import psutil
from app.models import Application
from app.db import get_db
from app.services import ProcessManager
from platformdirs import user_data_dir
import pathlib

package_dir = pathlib.Path(__file__).parent.absolute()
data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

# Definir la ruta completa del archivo PID
SERVER_PID_FILE = os.path.join(data_dir, "atlas_server.pid")

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
    """AtlasServer - CLI for managing the server and applications."""
    pass


@cli.command("start")
@click.option("--host", default="0.0.0.0", help="Server host")
@click.option("--port", default=5000, help="Server port")
@click.option("--reload", is_flag=True, help="Enable automatic reload")
def start_server(host, port, reload):
    """Start the AtlasServer service."""
    pid = get_server_pid()
    if pid:
        click.echo(f"⚠️ Server is already running (PID: {pid})")
        return

    reload_flag = "--reload" if reload else ""
    
    cmd = f"uvicorn app.main:app --host {host} --port {port} {reload_flag}"
    click.echo(f"🚀 Starting AtlasServer on {host}:{port}...")
    
    # Iniciar servidor como proceso independiente
    process = subprocess.Popen(
        cmd, 
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True
    )
    
    # Guardar PID en la ruta actualizada
    with open(SERVER_PID_FILE, "w") as f:
        f.write(str(process.pid))
    
    # Esperar un poco para ver si inicia correctamente
    time.sleep(2)
    if process.poll() is None:
        click.echo(f"✅ AtlasServer started successfully (PID: {process.pid})")
        click.echo(f"📌 Access at http://{host}:{port}")
    else:
        click.echo("❌ Error starting AtlasServer")
        stdout, stderr = process.communicate()
        click.echo(stderr.decode())

@cli.command("stop")
def stop_server():
    """Detener el servidor AtlasServer."""
    pid = get_server_pid()
    if not pid:
        click.echo("⚠️ AtlasServer is not running")
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
            
        click.echo("✅ AtlasServer stopped successfully")
    except Exception as e:
        click.echo(f"❌ Error stopping AtlasServer: {str(e)}")


@cli.command("status")
def server_status():
    """Verificar el estado del servidor AtlasServer."""
    pid = get_server_pid()
    if pid:
        try:
            process = psutil.Process(pid)
            mem = process.memory_info().rss / (1024 * 1024)
            cpu = process.cpu_percent(interval=0.1)
            
            click.echo(f"✅ AtlasServer is running")
            click.echo(f"   PID: {pid}")
            click.echo(f"   Memory: {mem:.2f} MB")
            click.echo(f"   CPU: {cpu:.1f}%")
            click.echo(f"   Uptime: {time.time() - process.create_time():.0f} seconds")
        except psutil.NoSuchProcess:
            click.echo("⚠️ PID file exists but the process is not running")
            if os.path.exists(SERVER_PID_FILE):
                os.remove(SERVER_PID_FILE)
    else:
        click.echo("❌ AtlasServer is not running")


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
            click.echo("No registered applications")
            return
        
        click.echo("\n📋 Registered applications:")
        click.echo("ID | Name | State | Type | Port | PID")
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
            click.echo(f"❌ Application with ID {app_id} not found")
            return
        
        click.echo(f"🚀 Starting application '{app.name}'...")
        result = process_manager.start_application(app_id)
        
        if result:
            app = db.query(Application).filter(Application.id == app_id).first()
            click.echo(f"✅ Application started successfully")
            click.echo(f"   Port: {app.port}")
            click.echo(f"   PID: {app.pid}")
            if app.ngrok_url:
                click.echo(f"   Public URL: {app.ngrok_url}")
        else:
            click.echo("❌ Error starting application")
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
            click.echo(f"❌ Application with ID {app_id} not found")
            return
        
        click.echo(f"🛑 Stopping application '{app.name}'...")
        result = process_manager.stop_application(app_id)
        
        if result:
            click.echo(f"✅ Application stopped successfully")
        else:
            click.echo("❌ Error stopping application")
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
            click.echo(f"❌ Application with ID {app_id} not found")
            return
        
        click.echo(f"🔄 Restarting application '{app.name}'...")
        result = process_manager.restart_application(app_id)
        
        if result:
            app = db.query(Application).filter(Application.id == app_id).first()
            click.echo(f"✅ Application restarted successfully")
            click.echo(f"   Port: {app.port}")
            click.echo(f"   PID: {app.pid}")
        else:
            click.echo("❌ Error restarting application")
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
            click.echo(f"❌ Application with ID {app_id} not found")
            return
        
        status_icon = "🟢" if app.status == "running" else "⚪" if app.status == "stopped" else "🔴"
        
        click.echo(f"\n📌 Information for '{app.name}':")
        click.echo(f"   ID: {app.id}")
        click.echo(f"   Status: {status_icon} {app.status}")
        click.echo(f"   Type: {app.app_type}")
        click.echo(f"   Port: {app.port or 'Not assigned'}")
        click.echo(f"   PID: {app.pid or 'N/A'}")
        click.echo(f"   Directory: {app.directory}")
        click.echo(f"   Main file: {app.main_file}")
        click.echo(f"   Created: {app.created_at}")
        
        if app.ngrok_enabled:
            click.echo(f"   Ngrok enabled: Yes")
            if app.ngrok_url:
                click.echo(f"   Public URL: {app.ngrok_url}")
        
        if app.status == "running" and app.pid:
            try:
                process = psutil.Process(app.pid)
                mem = process.memory_info().rss / (1024 * 1024)
                cpu = process.cpu_percent(interval=0.1)
                
                click.echo(f"\n   Performance:")
                click.echo(f"   - Memory: {mem:.2f} MB")
                click.echo(f"   - CPU: {cpu:.1f}%")
                click.echo(f"   - Uptime: {time.time() - process.create_time():.0f} seconds")
            except psutil.NoSuchProcess:
                click.echo(f"\n   ⚠️ PID exists but the process is not running")
    finally:
        db.close()


@cli.group()
def ai():
    """AI-assisted commands for deployment."""
    try:
        # Solo verificamos que el módulo esté disponible
        import atlasai
    except ImportError:
        import click
        click.echo("Error: To use AI commands, install AtlasAI-CLI:")
        click.echo("pip install atlasai-cli")
        raise click.Abort()

# Después de definir el grupo 'ai', añadimos esta parte
try:
    # Importamos el grupo de comandos de AtlasAI-CLI
    from atlasai.cli import ai as atlasai_commands
    
    # Iteramos sobre cada comando en el grupo 'ai' de AtlasAI
    for cmd_name, cmd in atlasai_commands.commands.items():
        # Añadimos cada comando al grupo 'ai' de AtlasServer-Core
        ai.add_command(cmd)
        
except ImportError:
    pass


if __name__ == "__main__":
    cli()