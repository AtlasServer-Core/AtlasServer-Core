from abc import ABC
from typing import Tuple, List, Optional, Union
from app.models import AtlasAdapter
from app.db import SessionLocal
from sqlalchemy.exc import IntegrityError

class BaseAdapter(ABC):
    _registry: dict[str, "BaseAdapter"] = {}

    def __init__(
        self,
        name: str,
        command_init_tpl: List[str],
        stop_command_tpl: Union[List[str], dict],
        config: dict = None
    ):
        """
        command_init_tpl and stop_command_tpl contain placeholders:
        '{main_file}', '{host}', '{port}'
        config holds other options (e.g. env vars).
        """
        self.name = name
        self._cmd_init_tpl = command_init_tpl
        self._cmd_stop_tpl = stop_command_tpl
        self.config = config or {}

        if name in BaseAdapter._registry:
            raise ValueError(f"Adapter '{name}' already registered")
        BaseAdapter._registry[name] = self

    def register(self):
        """
        Save the raw templates to the database unchanged.
        """
        adapter = AtlasAdapter(
            name=self.name,
            init_command=self._cmd_init_tpl,
            stop_command=self._cmd_stop_tpl,
            config=self.config
        )
        try:
            with SessionLocal() as db:
                db.add(adapter)
                db.commit()
            print(f"[OK] Adapter registered: {self.name}")
        except IntegrityError:
            print(f"[!] Adapter '{self.name}' already exists in DB.")
        except Exception as e:
            print(f"[ERROR] registering '{self.name}': {e}")

    def expand_commands(
        self,
        main_file: str,
        host: Optional[str] = None,
        port: Optional[int] = None
    ) -> Tuple[List[str], List[str]]:
        """
        Replace placeholders in the stored templates and return
        (init_command, stop_command) ready for execution.
        """
        vars = {
            "main_file": main_file,
            "host": host or "",
            "port": port if port is not None else ""
        }

        def _expand(tpl):
            if isinstance(tpl, list):
                return [s.format(**vars) for s in tpl]
            elif isinstance(tpl, dict):
                return tpl
            else:
                raise TypeError(f"Unsupported command template type: {type(tpl)}")

        return _expand(self._cmd_init_tpl), _expand(self._cmd_stop_tpl)

    @classmethod
    def get(cls, name: str) -> Optional["BaseAdapter"]:
        return cls._registry.get(name)

    @classmethod
    def all(cls) -> List["BaseAdapter"]:
        return list(cls._registry.values())

    @classmethod
    def expand_for(
        cls,
        name: str,
        main_file: str,
        host: Optional[str] = None,
        port: Optional[int] = None
    ) -> Tuple[List[str], List[str]]:
        """
        Retrieve a registered adapter by name, then expand its commands
        with provided values. Raises if adapter not found.
        """
        adapter = cls.get(name)
        if not adapter:
            raise KeyError(f"Adapter with name '{name}' not found")
        return adapter.expand_commands(main_file=main_file, host=host, port=port)