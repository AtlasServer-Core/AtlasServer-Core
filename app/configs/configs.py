import os
from platformdirs import user_data_dir
import json
import secrets
from datetime import datetime, timedelta

data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
os.makedirs(data_dir, exist_ok=True)

NGROK_CONFIG_FILE = os.path.join(data_dir, "ngrok_config.json")

SWAGGER_CONFIG_FILE = os.path.join(data_dir, "swagger_config.json")


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