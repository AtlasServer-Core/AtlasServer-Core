from fastapi import Depends, APIRouter
from app.auth import login_required
from app.models import User

router = APIRouter(prefix="/api", tags=["detect-environments"])

@router.get("/detect-environments")
def api_detect_environments(
    directory: str, 
    current_user: User = Depends(login_required)
):
    import os
    import sys
    import json
    import subprocess
    from pathlib import Path
    
    if not os.path.exists(directory):
        return {"success": False, "error": "El directorio no existe"}
    
    # Log para depuración
    print(f"🔍 Buscando entornos en: {directory}")
    
    # Definimos un diccionario básico con el entorno del sistema
    environments = {
        "system": {
            "name": "Sistema (Global)",
            "path": sys.executable,
            "type": "system"
        }
    }
    
    # Función para verificar si una ruta es un entorno Python válido
    def is_valid_python_env(path, env_type="virtualenv"):
        """Verifica si la ruta contiene un entorno Python válido."""
        if not os.path.exists(path):
            print(f"  ❌ Ruta no existe: {path}")
            return False
            
        # Determinar la ruta al ejecutable de Python según el sistema
        if os.name == 'nt':  # Windows
            python_bin = os.path.join(path, "Scripts", "python.exe")
        else:  # Unix/Mac
            python_bin = os.path.join(path, "bin", "python")
        
        # Verificar si existe el ejecutable y tiene permisos
        if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
            print(f"  ✅ Entorno válido encontrado: {path} ({env_type})")
            return {
                "path": path,
                "type": env_type,
                "python_bin": python_bin
            }
        
        print(f"  ❌ No es un entorno válido: {path}")
        return False
    
    # ===== 1. BUSCAR ENTORNOS VIRTUALES ESTÁNDAR =====
    env_folders = ["venv", ".venv", "env", ".env", "virtualenv", "pyenv"]
    project_dir = Path(directory)
    
    # Buscar en el directorio principal
    print("🔎 Buscando entornos virtuales estándar...")
    for folder in env_folders:
        env_path = os.path.join(directory, folder)
        env_info = is_valid_python_env(env_path)
        
        if env_info:
            env_id = f"local:{folder}"
            environments[env_id] = {
                "name": f"Entorno del proyecto ({folder})",
                "path": env_path,
                "type": "virtualenv",
                "local": True,
                "python_bin": env_info["python_bin"],
                "preferred": True
            }
    
    # ===== 2. BUSCAR CARPETAS QUE CONTENGAN "ENV" EN SU NOMBRE =====
    print("🔎 Buscando carpetas con 'env' en su nombre...")
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        # Verificar si es un directorio y si contiene 'env' en su nombre (case insensitive)
        if os.path.isdir(item_path) and 'env' in item.lower() and item.lower() not in [f.lower() for f in env_folders]:
            env_info = is_valid_python_env(item_path, "custom_env")
            if env_info:
                env_id = f"custom:{item}"
                environments[env_id] = {
                    "name": f"Entorno personalizado ({item})",
                    "path": item_path,
                    "type": "virtualenv",
                    "local": True,
                    "python_bin": env_info["python_bin"],
                    "preferred": True  # También les damos alta prioridad
                }
    
    # ===== 3. BUSCAR CONFIGURACIÓN DE POETRY =====
    print("🔎 Buscando entornos Poetry...")
    poetry_lock = os.path.join(directory, "poetry.lock")
    pyproject_toml = os.path.join(directory, "pyproject.toml")
    
    if os.path.exists(poetry_lock) or os.path.exists(pyproject_toml):
        print("  📄 Configuración Poetry detectada")
        # Poetry normalmente usa .venv en el directorio del proyecto
        poetry_venv = os.path.join(directory, ".venv")
        env_info = is_valid_python_env(poetry_venv, "poetry")
        
        if env_info:
            environments["local:poetry"] = {
                "name": "Entorno Poetry (.venv)",
                "path": poetry_venv,
                "type": "poetry",
                "local": True,
                "python_bin": env_info["python_bin"],
                "preferred": True
            }
    
    # ===== 4. BUSCAR PIPENV =====
    print("🔎 Buscando entornos Pipenv...")
    pipfile = os.path.join(directory, "Pipfile")
    
    if os.path.exists(pipfile):
        print("  📄 Pipfile detectado, intentando localizar entorno...")
        try:
            # Intentar obtener la ubicación del entorno Pipenv
            result = subprocess.run(
                ["pipenv", "--venv"],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                pipenv_path = result.stdout.strip()
                print(f"  📍 Entorno Pipenv encontrado en: {pipenv_path}")
                
                env_info = is_valid_python_env(pipenv_path, "pipenv")
                if env_info:
                    environments["local:pipenv"] = {
                        "name": "Entorno Pipenv",
                        "path": pipenv_path,
                        "type": "pipenv",
                        "local": True,
                        "python_bin": env_info["python_bin"],
                        "preferred": True
                    }
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"  ⚠️ Error al detectar entorno Pipenv: {e}")
    
    # ===== 5. BUSCAR ENTORNOS CONDA =====
    print("🔎 Buscando entornos Conda...")
    environment_yml = os.path.join(directory, "environment.yml")
    conda_env_dir = None
    
    if os.path.exists(environment_yml):
        print("  📄 Archivo environment.yml de Conda detectado")
        
        try:
            # Intentar obtener el nombre del entorno desde environment.yml
            with open(environment_yml, 'r') as f:
                import yaml
                try:
                    env_config = yaml.safe_load(f)
                    conda_env_name = env_config.get('name')
                    
                    if conda_env_name:
                        print(f"  🐍 Nombre del entorno Conda: {conda_env_name}")
                        
                        # Intentar localizar el entorno conda
                        try:
                            result = subprocess.run(
                                ["conda", "env", "list", "--json"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            
                            if result.returncode == 0:
                                conda_envs = json.loads(result.stdout)
                                
                                for env_path in conda_envs.get("envs", []):
                                    env_name = os.path.basename(env_path)
                                    
                                    if env_name == conda_env_name:
                                        conda_env_dir = env_path
                                        break
                                
                                if conda_env_dir:
                                    print(f"  ✅ Entorno Conda encontrado: {conda_env_dir}")
                                    
                                    # En Conda, el binario de Python está en diferentes lugares según el sistema
                                    if os.name == 'nt':  # Windows
                                        python_bin = os.path.join(conda_env_dir, "python.exe")
                                    else:  # Unix/Mac
                                        python_bin = os.path.join(conda_env_dir, "bin", "python")
                                    
                                    if os.path.exists(python_bin) and os.access(python_bin, os.X_OK):
                                        environments[f"conda:{conda_env_name}"] = {
                                            "name": f"Entorno Conda ({conda_env_name})",
                                            "path": conda_env_dir,
                                            "type": "conda",
                                            "local": True,
                                            "python_bin": python_bin,
                                            "preferred": True
                                        }
                        except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError) as e:
                            print(f"  ⚠️ Error al buscar entorno Conda: {e}")
                except yaml.YAMLError:
                    print("  ⚠️ No se pudo parsear environment.yml")
        except Exception as e:
            print(f"  ⚠️ Error al leer environment.yml: {e}")
    
    # ===== 6. BÚSQUEDA RECURSIVA DE ENTORNOS EN SUBDIRECTORIOS (con límite) =====
    print("🔎 Buscando entornos en subdirectorios (profundidad limitada)...")
    
    max_depth = 2  # Máxima profundidad de búsqueda
    searched_dirs = set()  # Para evitar búsquedas duplicadas
    
    def search_envs_in_subdirs(base_path, current_depth=0):
        if current_depth > max_depth or base_path in searched_dirs:
            return
            
        searched_dirs.add(base_path)
        
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                
                # Saltar directorios ya conocidos como entornos
                if any(env.get("path") == item_path for env in environments.values()):
                    continue
                    
                # Saltar directorios comunes que no contienen entornos
                if item in [".git", "node_modules", "__pycache__", "dist", "build"]:
                    continue
                
                # Comprobar si es un directorio
                if os.path.isdir(item_path):
                    # Verificar si este directorio parece un entorno virtual
                    # Ahora también detectamos nombres que contengan "env"
                    if item in env_folders or 'env' in item.lower():
                        env_info = is_valid_python_env(item_path)
                        if env_info:
                            rel_path = os.path.relpath(item_path, directory)
                            env_id = f"subdir:{rel_path}"
                            environments[env_id] = {
                                "name": f"Entorno en subdirectorio ({rel_path})",
                                "path": item_path,
                                "type": "virtualenv",
                                "local": True,
                                "python_bin": env_info["python_bin"],
                                "preferred": False
                            }
                    
                    # Buscar recursivamente, pero sólo en subdirectorios que podrían contener código
                    search_envs_in_subdirs(item_path, current_depth + 1)
        except PermissionError:
            print(f"  ⚠️ Sin permisos para leer {base_path}")
        except Exception as e:
            print(f"  ⚠️ Error al explorar {base_path}: {e}")
    
    # Iniciar búsqueda recursiva
    search_envs_in_subdirs(directory)
    
    # ===== 7. ENCONTRAR ENTORNO PREFERIDO =====
    preferred_env = None
    preferred_priority = {
        "local:.venv": 10,      # .venv en el directorio del proyecto (convención moderna)
        "local:venv": 9,        # venv en el directorio del proyecto
        "local:poetry": 8,      # Entorno poetry
        "local:pipenv": 7,      # Entorno pipenv
        "conda:": 6,            # Entornos conda (prefijo)
        "local:env": 5,         # Otros entornos en el directorio
        "custom:": 5,           # Entornos personalizados con "env" en el nombre
        "subdir:": 4,           # Entornos en subdirectorios (prefijo)
    }
    
    highest_priority = -1
    
    for env_id, env in environments.items():
        if env_id == "system":
            continue
            
        priority = 0
        
        # Buscar prioridad exacta
        if env_id in preferred_priority:
            priority = preferred_priority[env_id]
        else:
            # Buscar prioridad por prefijo
            for prefix, prio in preferred_priority.items():
                if env_id.startswith(prefix):
                    priority = prio
                    break
        
        if priority > highest_priority:
            highest_priority = priority
            preferred_env = env_id
            
    print(f"🏆 Entorno preferido: {preferred_env}")
    print(f"🔢 Total de entornos encontrados: {len(environments)}")

    return {
        "success": True,
        "environments": environments,
        "preferred": preferred_env
    }