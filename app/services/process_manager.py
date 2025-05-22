#process_manager.py

import subprocess
import os
import psutil
from sqlalchemy.orm import Session
import logging
import json
from app.configs import NGROK_CONFIG_FILE
from app.models import Application, Log
from app.utils import find_available_port, check_port_available

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProcessManager:
    def __init__(self, db: Session):
        self.db = db

        self.ngrok_token = None

        try:
            if os.path.exists(NGROK_CONFIG_FILE):
                with open(NGROK_CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.ngrok_token = config.get("token", None)
        except Exception as e:
            print(f"Error al cargar la configuración de ngrok: {str(e)}")
        
    def start_application(self, app_id: int):
        application = self.db.query(Application).filter(Application.id == app_id).first()
        if not application:
            self._add_log(app_id, "Aplicación no encontrada", "error")
            return False
        
        if application.status == "running":
            self._add_log(app_id, "La aplicación ya está en ejecución", "warning")
            return True
        
        # Asignar un puerto si no tiene uno
        if not application.port:
            port = find_available_port(self.db, exclude_app_id=app_id)
            if not port:
                self._add_log(app_id, "No se encontraron puertos disponibles", "error")
                return False
            application.port = port
        
        # Verificar que el puerto sigue disponible
        if not check_port_available(application.port):
            new_port = find_available_port(self.db, exclude_app_id=app_id)
            if not new_port:
                self._add_log(app_id, "No se encontraron puertos disponibles", "error")
                return False
            application.port = new_port
            self._add_log(app_id, f"Puerto reasignado a {new_port}", "warning")
        
        # Construir el comando según el tipo de aplicación
        cmd = []
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        cwd = application.directory

        python_cmd = "python"  # Por defecto
    
        if application.environment_type == "virtualenv":
            if application.environment_path:
                python_bin = os.path.join(application.environment_path, "bin", "python")
                if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
                    python_cmd = python_bin
                else:
                    self._add_log(app_id, f"Entorno virtual no encontrado: {application.environment_path}", "error")
                    return False
    
        elif application.environment_type == "conda":
            # Para conda, necesitamos crear un script de activación
            if application.environment_path:
                conda_script = f"""
                #!/bin/bash
                source ~/anaconda3/etc/profile.d/conda.sh || source ~/miniconda3/etc/profile.d/conda.sh
                conda activate {application.environment_path}
                exec "$@"
                """
                script_path = os.path.join(cwd, ".conda_runner.sh")
                with open(script_path, "w") as f:
                    f.write(conda_script)
                os.chmod(script_path, 0o755)
            
                # Ahora el comando usará el script de activación
                cmd = [script_path]
                python_cmd = "python"
        
        if application.app_type.lower() == "flask":
            # Formato esperado: python -m waitress --port=8000 module:app
            module_name = os.path.splitext(application.main_file)[0].replace("/", ".")
            if application.environment_type == "conda":
                cmd.extend([python_cmd, "-m", "waitress", f"--port={application.port}", "--host=0.0.0.0", f"{module_name}:app"])
            else:
                cmd = [python_cmd, "-m", "waitress", f"--port={application.port}", "--host=0.0.0.0", f"{module_name}:app"]
        elif application.app_type.lower() == "fastapi":
            # Formato esperado: uvicorn module:app --port 8000
            module_name = os.path.splitext(application.main_file)[0].replace("\\", ".").replace("/", ".")
            if application.environment_type == "conda":
                cmd.extend([python_cmd, "-m", "uvicorn", f"{module_name}:app", f"--port={application.port}", "--host=0.0.0.0"])
            else:
                cmd = [python_cmd, "-m", "uvicorn", f"{module_name}:app", f"--port={application.port}", "--host=0.0.0.0"]

        elif application.app_type.lower() == "django":
            project_dirs = [d for d in os.listdir(application.directory) 
                   if os.path.isdir(os.path.join(application.directory, d)) 
                   and os.path.exists(os.path.join(application.directory, d, 'wsgi.py'))]

            if not project_dirs:
                self._add_log(app_id, "No se pudo detectar el módulo WSGI de Django", "error")
                return False

            project_name = project_dirs[0]
            env["DJANGO_SETTINGS_MODULE"] = f"{project_name}.settings"

            if application.environment_type == "conda":
                cmd.extend([python_cmd, "-m", "gunicorn", f"{project_name}.wsgi:application", "--bind", f"0.0.0.0:{application.port}"])
            else:
                cmd = [python_cmd, "-m", "gunicorn", f"{project_name}.wsgi:application", "--bind", f"0.0.0.0:{application.port}"]
        else:
            self._add_log(app_id, f"Tipo de aplicación no soportado: {application.app_type}", "error")
            return False
        
        self._add_log(app_id, f"Ejecutando comando: {' '.join(cmd)}", "info")
        self._add_log(app_id, f"En directorio: {cwd}", "info")

        
        
        try:
            # Crear archivos para stdout y stderr
            logs_dir = os.path.join(cwd, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            
            stdout_file = open(os.path.join(logs_dir, "stdout.log"), "a")
            stderr_file = open(os.path.join(logs_dir, "stderr.log"), "a")
            
            # Iniciar el proceso
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                bufsize=0,
                start_new_session=True  # Crea un nuevo grupo de procesos
            )
            
            # Actualizar el estado de la aplicación
            application.pid = process.pid
            application.status = "running"
            self.db.commit()
            
            self._add_log(app_id, f"Aplicación iniciada en el puerto {application.port} con PID {process.pid}", "info")

            if application.ngrok_enabled and application.port:
                try:
                    from pyngrok import ngrok, conf
            
                    # Configura el token de ngrok si está disponible
                    if self.ngrok_token:
                        conf.get_default().auth_token = self.ngrok_token
            
                    # Inicia el túnel ngrok
                    ngrok_tunnel = ngrok.connect(application.port)
            
                    # Guarda la URL pública
                    application.ngrok_url = ngrok_tunnel.public_url
                    self.db.commit()
            
                    self._add_log(app_id, f"Túnel ngrok creado: {ngrok_tunnel.public_url}", "info")
                except Exception as e:
                    self._add_log(app_id, f"Error al crear túnel ngrok: {str(e)}", "error")
    
            return True
            
        except Exception as e:
            import traceback
            self._add_log(app_id, f"Error al iniciar la aplicación: {str(e)}", "error")
            self._add_log(app_id, f"Detalles del error: {traceback.format_exc()}", "error")
            application.status = "error"
            self.db.commit()
            return False
        
        
    
    def get_local_ip(self):
        import socket
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
    
    def stop_application(self, app_id: int):
        application = self.db.query(Application).filter(Application.id == app_id).first()
        if not application:
            return False
        
        if application.status != "running" or not application.pid:
            application.status = "stopped"
            self.db.commit()
            return True
        
        try:
            # Intenta terminar el proceso y todos sus hijos
            parent = psutil.Process(application.pid)
            children = parent.children(recursive=True)
            
            for child in children:
                child.terminate()
            
            # Termina el proceso principal
            parent.terminate()
            
            # Espera a que terminen los procesos
            gone, alive = psutil.wait_procs(children + [parent], timeout=5)
            
            # Si alguno sigue vivo, lo mata forzosamente
            for p in alive:
                p.kill()
            
            application.status = "stopped"
            application.pid = None
            self.db.commit()

            if application.ngrok_url:
                try:
                    from pyngrok import ngrok
                    # Extraer el puerto del túnel de la URL
                    public_url = application.ngrok_url
                    ngrok.disconnect(public_url)
                    application.ngrok_url = None
                    self._add_log(app_id, f"Túnel ngrok cerrado: {public_url}", "info")
                except Exception as e:
                    self._add_log(app_id, f"Error al cerrar túnel ngrok: {str(e)}", "warning")
            
            self._add_log(app_id, "Aplicación detenida correctamente", "info")
            return True
            
        except psutil.NoSuchProcess:
            # El proceso ya no existe
            application.status = "stopped"
            application.pid = None
            self.db.commit()
            self._add_log(app_id, "El proceso ya no existe", "warning")
            return True
            
        except Exception as e:
            self._add_log(app_id, f"Error al detener la aplicación: {str(e)}", "error")
            return False
    
    def restart_application(self, app_id: int):
        if self.stop_application(app_id):
            return self.start_application(app_id)
        return False
    
    def check_application_status(self, app_id: int):
        application = self.db.query(Application).filter(Application.id == app_id).first()
        if not application or not application.pid:
            return
        
        try:
            process = psutil.Process(application.pid)
            if process.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                application.status = "error"
                self._add_log(app_id, "El proceso está en estado zombie", "error")
                self.db.commit()
        except psutil.NoSuchProcess:
            application.status = "stopped"
            application.pid = None
            self._add_log(app_id, "El proceso ya no existe", "warning")
            self.db.commit()
    
    def _add_log(self, app_id: int, message: str, level: str = "info"):
        log = Log(application_id=app_id, message=message, level=level)
        self.db.add(log)
        self.db.commit()
        logger.info(f"App {app_id}: {message}")