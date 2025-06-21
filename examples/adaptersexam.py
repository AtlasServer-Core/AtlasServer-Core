from app.adapters import BaseAdapter

#adapter = BaseAdapter(
#    name="Spring",
#    command_init_tpl=[
#        "java", "-jar", "{main_file}", ## We use the "{main_file}" to specify where the path of the 
                                        ##main file will be placed later when we want to launch the app, as well as with the host and port
#        "server.address={host}",
#        "server.port={port}"
#    ],
#    stop_command_tpl=[
#        "java", "-jar", "{main_file}", "--stop" ## Same here
#    ],
#    config={"env": {"JAVA_OPTS": "-Xmx512m"}}
#)

#adapter.register()


adapter_js = BaseAdapter(
    name="Vite2",
    command_init_tpl=[
        "npx", "vite", "{main_file}", ## We use the "{main_file}" to specify where the path of the main file will be 
                                    ##placed later when we want to launch the app, as well as with the host and port
        "--host", "{host}",
        "--port", "{port}"
    ],
    stop_command_tpl={
        "signal_SIGINT": True ## This is an option I included for JS frameworks because they don't have a specific command, 
        ## and this sends a signal like Ctrl + C that stops the process immediately. 
        ##However, it's also compatible with any other framework that only stops with commands like Ctrl + C.
    },
)

adapter_js.register()