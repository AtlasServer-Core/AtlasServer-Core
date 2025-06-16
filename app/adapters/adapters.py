from app.models import AtlasAdapter
from app.db import get_db

class BaseAdapter:
    _registry = {}

    def __init__(self, name, command_init, stop_command,  config):
        self.name = name
        self.command_init = command_init
        self.stop_command = stop_command
        self.config = config
        db_gen = get_db()
        db = next(db_gen)
        self.db = db

        # Autoregistro al instanciar
        BaseAdapter._registry[name] = self

    def register(self):
        print(f"Registering adapter: {self.name}")
        try:
            adapter = AtlasAdapter(
                name=self.name,
                init_command=self.command_init,
                stop_command=self.stop_command,
                config=self.config
            )

            self.db.add(adapter)
            self.db.commit()

            print(f"The adapter has been registered successfully: {self.name}")

        except Exception as e:
            print(f"Erro: {e}")   

    @classmethod
    def get(cls, name):
        return cls._registry.get(name)

    @classmethod
    def all(cls):
        return list(cls._registry.values())

