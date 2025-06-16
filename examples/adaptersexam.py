from app.adapters import BaseAdapter

class JavaAdapter(BaseAdapter):
    def __init__(self, name, command, config):
        super().__init__(name, command, config)

    def register(self):
        super().register()

## PLEASE do not include the main file in the command to start the service, 
## because errors may occur when trying to start it from the web dashboard

## MISUSE OF THE CLASS
adapter = JavaAdapter("Spring", ["java", "-jar", "app.jar"], {"port": 8080})

## GOOD USE OF THE CLASS
adapter = JavaAdapter("Spring", ["java", "-jar"], {"port": 8080})

adapter.register()