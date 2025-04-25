#process_manager.py

import subprocess
import os
import psutil
from sqlalchemy.orm import Session
import sqlalchemy
import logging
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
import datetime
import socket
from contextlib import closing
import json
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./applications.db"
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=sqlalchemy.pool.QueuePool,
    pool_size=20,
    max_overflow=20,
    pool_timeout=60,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

NGROK_CONFIG_FILE = "ngrok_config.json"

# Función para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def check_port_available(port):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex(('localhost', port)) != 0

def find_available_port(start_port=8000, end_port=9000):
    for port in range(start_port, end_port):
        if check_port_available(port):
            return port
    return None

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    directory = Column(String)
    main_file = Column(String)
    app_type = Column(String)  # "flask" o "fastapi"
    port = Column(Integer, nullable=True)
    status = Column(String, default="stopped")  # "running", "stopped", "error"
    pid = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    logs = relationship("Log", back_populates="application", cascade="all, delete-orphan")
    ngrok_enabled = Column(Boolean, default=False)
    ngrok_url = Column(String, nullable=True)

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    message = Column(String)
    level = Column(String, default="info")  # "info", "error", "warning"
    
    application = relationship("Application", back_populates="logs")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # Almacenaremos contraseñas hasheadas
    is_admin = Column(Boolean, default=True)  # El primer usuario será admin
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_registration_open = Column(Boolean, default=False)  # Control de registro

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
            port = find_available_port()
            if not port:
                self._add_log(app_id, "No se encontraron puertos disponibles", "error")
                return False
            application.port = port
        
        # Verificar que el puerto sigue disponible
        if not find_available_port(application.port, application.port + 1):
            new_port = find_available_port()
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
        
        if application.app_type.lower() == "flask":
            # Formato esperado: python -m waitress --port=8000 module:app
            module_name = os.path.splitext(application.main_file)[0].replace("/", ".")
            cmd = [
                "python", "-m", "waitress",
                f"--port={application.port}",
                "--host=0.0.0.0",
                f"{module_name}:app"
            ]
        elif application.app_type.lower() == "fastapi":
            # Formato esperado: uvicorn module:app --port 8000
            module_name = os.path.splitext(application.main_file)[0].replace("\\", ".").replace("/", ".")
            cmd = [
                "python", "-m", "uvicorn",  
                f"{module_name}:app", 
                f"--port={application.port}",
                "--host=0.0.0.0",
            ]
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
        
        
    
    def get_local_ip():
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