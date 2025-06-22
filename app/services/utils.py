from sqlalchemy.orm import Session
from app.models import Application, AtlasAdapter
from app.adapters import BaseAdapter
from typing import Optional, Tuple, List
import os
import psutil
import signal

import logging
logger = logging.getLogger(__name__)

BASE_APPS = {"flask", "fastapi", "django"}

def is_base_app(db: Session, app_id: int) -> bool:
    """
    Retorna True si la aplicación es de tipo 'flask', 'fastapi' o 'django'.
    """
    app = db.query(Application).get(app_id)
    if not app:
        raise ValueError(f"Application with id={app_id} not found")
    return app.app_type.lower() in BASE_APPS

def get_adapter_commands(
    db: Session,
    app_type: str,
    main_file: str,
    host: Optional[str] = None,
    port: Optional[int] = None
) -> Tuple[List[str], List[str]]:
    """
    Returns (init_command, stop_command) for an adapter by type, expanded with
    provided main_file, host, and port values. Raises LookupError if not found.
    """
    row = (
        db.query(AtlasAdapter)
          .filter(AtlasAdapter.name.ilike(app_type))
          .first()
    )
    if not row:
        raise LookupError(f"No adapter found for type '{app_type}'")
    # register in memory if not already
    if app_type not in BaseAdapter._registry:
        BaseAdapter(
            name=row.name,
            command_init_tpl=row.init_command,
            stop_command_tpl=row.stop_command,
            config=row.config
        )
    # expand from registry
    return BaseAdapter.expand_for(
        name=row.name,
        main_file=main_file,
        host=host,
        port=port
    )



def kill_process_tree(pid: int, sig: int = signal.SIGINT, timeout: float = 5.0) -> bool:
    """
    Envía `sig` al proceso `pid` y a todos sus hijos recursivamente.
    - Primero intenta graceful (sig), espera `timeout` segundos.
    - Luego fuerza con SIGKILL a los que queden vivos.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess as e:
        logger.error(f"Error: {e}")
        return False

    procs = [parent] + parent.children(recursive=True)

    # 1) Graceful
    for p in procs:
        try:
            os.kill(p.pid, sig)
        except Exception as e:
            logger.error(f"Error: {e}")
            pass

    # 2) Esperar
    gone, alive = psutil.wait_procs(procs, timeout=timeout)

    # 3) Forzar
    for p in alive:
        try:
            os.kill(p.pid, signal.SIGKILL)
        except Exception as e:
            logger.error(f"Error: {e}")
            pass

    return True