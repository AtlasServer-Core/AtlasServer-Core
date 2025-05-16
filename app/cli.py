#!/usr/bin/env python
# app/cli.py
import click
import os
import subprocess
import time
import psutil
import asyncio
import re
import json
from app.process_manager import get_db, Application, ProcessManager
from platformdirs import user_data_dir

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
    pass

@ai.command("setup")
@click.option("--provider", type=click.Choice(["ollama"]), default="ollama", 
              help="AI provider (only ollama in Core)")
@click.option("--model", default="qwen3:8b", help="Model to use (e.g.: qwen3:8b)")
def ai_setup(provider, model):
    """Configure the AI service for CLI."""
    from app.ai.ai_cli import AtlasServerAICLI
    ai_cli = AtlasServerAICLI()
    success = ai_cli.setup(provider, model, None)
    
    if success:
        click.echo(f"✅ AI configuration saved: {provider} / {model}")
    else:
        click.echo("❌ Error saving AI configuration")

@ai.command("suggest")
@click.argument("app_directory", type=click.Path(exists=True))
@click.option("--stream/--no-stream", default=True, help="Stream the AI response")
@click.option("--interactive/--no-interactive", default=True, 
              help="Use interactive file exploration")
@click.option("--debug/--no-debug", default=False, help="Show debug information")
@click.option("--language", type=click.Choice(["en", "es"]), default="en",
              help="Response language (English or Spanish)")
def ai_suggest_command(app_directory, stream, interactive, debug, language):
    """Suggest deployment commands for an application."""
    try:
        app_directory = os.path.abspath(app_directory)
        
        # Cargar configuración AI
        from app.ai.ai_cli import AtlasServerAICLI
        ai_cli = AtlasServerAICLI()
        configured_model = ai_cli.ai_config.get("model", "codellama:7b")
        
        click.echo(f"🤖 Using AI model: {configured_model}")
        
        # Verificar Ollama
        import requests
        try:
            response = requests.get("http://localhost:11434/api/version", timeout=2)
            if response.status_code != 200:
                click.echo("❌ Error: Could not connect to Ollama server")
                return
            else:
                if debug:
                    click.echo(f"✅ Connected to Ollama: {response.json()}")
        except Exception as e:
            click.echo(f"❌ Error: Ollama server is not running. {str(e)}")
            click.echo("   Run 'ollama serve' or ensure the Ollama service is running.")
            return
        
        if interactive:
            # Use el nuevo enfoque simplificado (sin herramientas complejas)
            from app.ai.ai_agent import AgentCLI
            agent = AgentCLI(model=configured_model, stream=stream, language=language)
            
            click.echo(f"🔍 Analyzing project at: {app_directory}")
            
            # Define callback para streaming si es necesario
            if stream:
                full_response_text = []
                
                def collect_response(chunk):
                    full_response_text.append(chunk)
                    click.echo(chunk, nl=False)
                
                # Ejecutar con streaming
                response = asyncio.run(agent.analyze_project(
                    app_directory, 
                    callback=collect_response
                ))
                
                # Si la respuesta está vacía pero tenemos texto, úsalo
                if not response and full_response_text:
                    response = ''.join(full_response_text)
                click.echo("\n")
            else:
                # Ejecutar sin streaming
                click.echo("⏳ This may take a moment...")
                response = asyncio.run(agent.analyze_project(app_directory))
            
            # Mostrar respuesta completa en modo debug
            if debug:
                click.echo("\n🔧 DEBUG - Raw response:")
                click.echo("-"*50)
                click.echo(response)
                click.echo("-"*50)
            
            # Procesar la respuesta para extraer JSON
            try:
                # Buscar bloque JSON en formato markdown
                json_match = re.search(r'```(?:json)?\s*({[\s\S]*?})\s*```', response, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                    except:
                        # Intentar limpiar el JSON antes de parsearlo
                        json_str = json_match.group(1)
                        # Eliminar líneas de comentarios o texto no-JSON
                        json_str = re.sub(r'^\s*//.*$', '', json_str, flags=re.MULTILINE)
                        try:
                            result = json.loads(json_str)
                        except:
                            result = {"type": "Unknown", "reasoning": response}
                else:
                    # Buscar JSON fuera de bloques markdown
                    json_match = re.search(r'({[\s\S]*})', response)
                    if json_match:
                        try:
                            result = json.loads(json_match.group(1))
                        except:
                            result = {"type": "Unknown", "reasoning": response}
                    else:
                        # No se encontró JSON, usar el texto completo
                        result = {"type": "Unknown", "reasoning": response}
            except Exception as e:
                if debug:
                    click.echo(f"Error parsing JSON: {str(e)}")
                result = {"type": "Unknown", "reasoning": response}
            
        else:
            # Usar el enfoque no interactivo original
            if stream:
                # Callback para streaming
                click.echo("🤖 Analyzing project structure...")
                
                def stream_callback(chunk):
                    click.echo(chunk, nl=False)
                
                # Ejecutar con streaming
                result = asyncio.run(ai_cli.suggest_deployment_command(
                    app_directory, 
                    stream=True, 
                    callback=stream_callback
                ))
                click.echo("\n")
            else:
                # Ejecutar sin streaming
                click.echo("🤖 Analyzing project structure...")
                result = asyncio.run(ai_cli.suggest_deployment_command(app_directory))
        
        # Mostrar resultados formateados
        click.echo("\n" + "="*50)
        click.echo("📊 DEPLOYMENT RECOMMENDATIONS")
        click.echo("="*50)
        
        if isinstance(result, dict):
            # Si es un diccionario (JSON parseado exitosamente)
            click.echo(f"📂 Detected project type: {result.get('type', 'Unknown')}")
            
            if result.get("command"):
                click.echo(f"🚀 Recommended command: {result['command']}")
            
            if result.get("port"):
                click.echo(f"🔌 Recommended port: {result['port']}")
                
            if result.get("environment_vars"):
                click.echo("\n📋 Recommended environment variables:")
                for key, value in result["environment_vars"].items():
                    click.echo(f"  {key}={value}")
            
            if result.get("reasoning"):
                click.echo("\n🔍 Analysis details:")
                click.echo("-"*50)
                reasoning = result["reasoning"]
                if isinstance(reasoning, str):
                    # Limitar longitud de líneas para mejor visualización
                    for line in reasoning.split("\n"):
                        if len(line) > 80:
                            parts = [line[i:i+80] for i in range(0, len(line), 80)]
                            for part in parts:
                                click.echo(f"  {part}")
                        else:
                            click.echo(f"  {line}")
                else:
                    click.echo(f"  {reasoning}")
        else:
            # Si no es un diccionario (string u otro tipo)
            click.echo(f"📂 Detected project type: Unknown")
            click.echo("\n🔍 Analysis details:")
            click.echo("-"*50)
            click.echo(f"  {result}")
        
        click.echo("\n" + "="*50)
                
        if click.confirm("Would you like to register this application with this configuration?"):
            # Código para registrar automáticamente
            click.echo("Automatic registration implementation pending.")
            
    except Exception as e:
        click.echo(f"❌ Error during analysis: {str(e)}")
        import traceback
        click.echo(traceback.format_exc())


if __name__ == "__main__":
    cli()