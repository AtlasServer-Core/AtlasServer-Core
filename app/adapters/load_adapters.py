from app.models import AtlasAdapter
from app.db import get_db

def load_adapters_from_db() -> list[dict]:
    """
    Lee todos los adapters de la BD y devuelve una lista de dicts con:
      - name
      - init_command
      - stop_command
      - config
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        rows = db.query(AtlasAdapter).all()
        adapters = []
        for row in rows:
            adapters.append({
                "name": row.name,
                "init_command": row.init_command,
                "stop_command": row.stop_command,
                "config": row.config
            })
        return adapters

    finally:
        # cierra la sesión de get_db()
        try:
            next(db_gen)
        except StopIteration:
            pass