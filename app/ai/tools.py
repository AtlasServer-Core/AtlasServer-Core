# app/ai/tools.py
import platform
import logging
import os
import subprocess
from typing import List
from langchain_community.tools import DuckDuckGoSearchRun, ShellTool
from langchain_community.agent_toolkits import FileManagementToolkit

logger = logging.getLogger(__name__)

def get_os():
    """Return the current operating system."""
    system = platform.uname()
    return system.system

def search(query: str) -> str:
    """Search the web using DuckDuckGo."""
    try:
        search = DuckDuckGoSearchRun()
        return search.invoke(query)
    except Exception as e:
        logger.error(f"Error searching with DuckDuckGo: {str(e)}")
        return f"Error performing search: {str(e)}"

def list_directory(directory: str = ".") -> str:
    """Lista archivos en el directorio especificado.
    
    Args:
        directory: Ruta a listar (valor predeterminado: directorio actual)
    
    Returns:
        String con el contenido del directorio
    """
    try:
        if not os.path.isdir(directory):
            return f"Error: '{directory}' no es un directorio válido"
        
        # Usar directamente el comando 'ls' o 'dir' dependiendo del sistema
        if platform.system() == "Windows":
            result = subprocess.run(["dir", "/b", directory], capture_output=True, text=True)
        else:
            result = subprocess.run(["ls", "-la", directory], capture_output=True, text=True)
            
        if result.returncode != 0:
            return f"Error listando directorio: {result.stderr}"
        
        return result.stdout
    except Exception as e:
        logger.error(f"Error listando directorio {directory}: {str(e)}")
        return f"Error listando directorio: {str(e)}"

def read_file(file_path: str) -> str:
    """Read the contents of a file.
    
    Args:
        file_path: Path to the file to read
    
    Returns:
        Contents of the file
    """
    try:
        toolkit = FileManagementToolkit(root_dir=None)
        read_tool = None
        
        # Get the read file tool
        for tool in toolkit.get_tools():
            if tool.__class__.__name__ == "ReadFileTool":
                read_tool = tool
                break
                
        if read_tool:
            return read_tool.invoke({"file_path": file_path})
        else:
            return f"Error: Could not create file reading tool"
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
        return f"Error reading file: {str(e)}"

def execute_command(commands: List[str]) -> str:
    """Ejecuta comandos de shell.
    
    Args:
        commands: Lista de comandos a ejecutar
        
    Returns:
        Salida del comando
    """
    try:
        # Limitar comandos a operaciones seguras de solo lectura
        safe_commands = ["ls", "dir", "cat", "type", "find", "grep", "head", "tail"]
        
        # Verificar que los comandos son seguros
        for cmd in commands:
            cmd_parts = cmd.split()
            if not cmd_parts:
                continue
                
            base_cmd = cmd_parts[0].lower()
            if base_cmd not in safe_commands:
                return f"Error: Comando no permitido '{base_cmd}'. Solo se permiten comandos de lectura."
        
        # Usar ShellTool para ejecutar comandos
        shell_tool = ShellTool()
        return shell_tool.run({"commands": commands})
    except Exception as e:
        logger.error(f"Error ejecutando comandos {commands}: {str(e)}")
        return f"Error ejecutando comandos: {str(e)}"