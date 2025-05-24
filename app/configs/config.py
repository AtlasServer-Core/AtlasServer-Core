import os
from platformdirs import user_data_dir
import json
import secrets
from datetime import datetime, timedelta

data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

NGROK_CONFIG_FILE = os.path.join(data_dir, "ngrok_config.json")

SWAGGER_CONFIG_FILE = os.path.join(data_dir, "swagger_config.json")

SESSIONMIDDLEWARE_FILE = os.path.join(data_dir, "sessionmiddleware.json")

ROTATION_DAYS = 0

def load_swagger_config():
    if os.path.exists(SWAGGER_CONFIG_FILE):
        try:
            with open(SWAGGER_CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {"enabled": False, "username": "", "password": "", "use_admin_credentials": False}
    return {"enabled": False, "username": "", "password": "", "use_admin_credentials": False}

def save_swagger_config(config):
    with open(SWAGGER_CONFIG_FILE, "w") as f:
        json.dump(config, f)

# Funciones para cargar y guardar la configuración de ngrok
def load_ngrok_config():
    if os.path.exists(NGROK_CONFIG_FILE):
        try:
            with open(NGROK_CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_ngrok_config(config):
    with open(NGROK_CONFIG_FILE, "w") as f:
        json.dump(config, f)

def load_middleware_config():
    if os.path.exists(SESSIONMIDDLEWARE_FILE):
        try:
            with open(SESSIONMIDDLEWARE_FILE, "r") as f:
                data = json.load(f)
            # Si no es un dict con los campos adecuados, lo descartamos
            if (
                isinstance(data, dict)
                and "token" in data
                and "generated_at" in data
            ):
                gen_time = datetime.fromisoformat(data["generated_at"])
                # Si tiene más de ROTATION_DAYS, forzamos regeneración
                if datetime.utcnow() - gen_time < timedelta(days=ROTATION_DAYS):
                    return data  # token aún válido
        except (json.JSONDecodeError, ValueError):
            pass
    # Si llegamos aquí, hay que generar uno nuevo
    return {"token": None, "generated_at": None}

def save_middleware_config(config):
    with open(SESSIONMIDDLEWARE_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_or_refresh_token():
    print(f"[DEBUG] Entrando en get_or_refresh_token(), ruta de config: {SESSIONMIDDLEWARE_FILE}")
    config = load_middleware_config()
    # Si no había token, o expiró (token es None)
    if not config.get("token"):
        new_token = secrets.token_hex(32)
        config["token"] = new_token
        config["generated_at"] = datetime.utcnow().isoformat()
        save_middleware_config(config)
    return config["token"]