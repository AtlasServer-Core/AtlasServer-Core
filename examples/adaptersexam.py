from app.adapters import BaseAdapter

class JavaAdapter(BaseAdapter):
    def __init__(self, name, command, config):
        super().__init__(name, command, config)

    def register(self):
        super().register()

## PLEASE do not include the main file in the command to start the service, 
## because errors may occur when trying to start it from the web dashboard

## MISUSE OF THE CLASS
adapter = JavaAdapter(name="Spring", command_init=["java", "-jar", "app.jar"], stop_command=["java","-jar","app.jar","--stop"], config={"env": {"JAVA_OPTS": "-Xmx512m"}})

## GOOD USE OF THE CLASS
## Ok I've noticed that making this more adaptable requires a few more things, 
## for now we'll leave this as good use, but I need to add some logic so we can correctly specify everything needed.
adapter = JavaAdapter(name="Spring", command_init=["java", "-jar"], stop_command=["java","-jar","app.jar","--stop"], config={"env": {"JAVA_OPTS": "-Xmx512m"}}) 

adapter.register()