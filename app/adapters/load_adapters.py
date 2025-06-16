from app.models import AtlasAdapter
from app.db import get_db
from app.adapters import BaseAdapter

def load_adapters_from_db():
    """
    Lee todos los adapters de la BD usando get_db()
    y los registra en BaseAdapter._registry.
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        rows = db.query(AtlasAdapter).all()
        for row in rows:
            BaseAdapter(
                name=row.name,
                command=row.command,
                config=row.config
            )
    finally:
        # cierra la sesión
        try:
            next(db_gen)
        except StopIteration:
            pass