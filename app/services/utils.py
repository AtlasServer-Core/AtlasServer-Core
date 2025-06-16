from sqlalchemy.orm import Session
from app.models import Application, AtlasAdapter

BASE_APPS = {"flask", "fastapi", "django"}

def is_base_app(db: Session, app_id: int) -> bool:
    """
    Retorna True si la aplicación es de tipo 'flask', 'fastapi' o 'django'.
    """
    app = db.query(Application).get(app_id)
    if not app:
        raise ValueError(f"Application with id={app_id} not found")
    return app.app_type.lower() in BASE_APPS

def get_adapter_commands(db: Session, app_type: str) -> tuple[list[str], list[str]]:
    """
    Retorna (init_command, stop_command) para un adapter no-base.
    Lanza LookupError si no existe.
    """
    adapter = (
        db.query(AtlasAdapter)
          .filter(AtlasAdapter.name.ilike(app_type))
          .first()
    )
    if not adapter:
        raise LookupError(f"No adapter found for type '{app_type}'")
    return adapter.init_command, adapter.stop_command