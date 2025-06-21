from app.adapters import BaseAdapter

adapter = BaseAdapter(
    name="Spring",
    command_init_tpl=[
        "java", "-jar", "{main_file}", ## We use the "{main_file}" to specify where the path of the main file will be placed later when we want to launch the app, as well as with the host and port
        "server.address={host}",
        "server.port={port}"
    ],
    stop_command_tpl=[
        "java", "-jar", "{main_file}", "--stop" ## Same here
    ],
    config={"env": {"JAVA_OPTS": "-Xmx512m"}}
)

adapter.register()