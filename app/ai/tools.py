from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.tools import ShellTool
import platform

def GetOS():
    system = platform.uname()
    return system.system

def Search(query):
    search = DuckDuckGoSearchRun()
    return search.invoke(query)

def Shell(command):
    pass

def FileSystem():
    pass