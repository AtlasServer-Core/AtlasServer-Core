from sqlalchemy.orm import Session
from app.models import Application, AtlasAdapter
from app.adapters import BaseAdapter
from typing import Optional, Tuple, List

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
