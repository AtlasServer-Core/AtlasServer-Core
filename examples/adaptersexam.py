from app.adapters import BaseAdapter

class JavaAdapter(BaseAdapter):
    def __init__(self, name, command, config):
        super().__init__(name, command, config)

    def register(self):
        super().register()

adapter = JavaAdapter("Spring", ["java", "-jar", "app.jar"], {"port": 8080})
adapter.register()