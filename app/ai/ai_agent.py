import os
import logging
import re
import json
from typing import Dict, Any, Optional, Callable

from ollama import chat

from app.ai.tools import list_directory, read_file

logger = logging.getLogger(__name__)

class AgentCLI:
    """AI Agent for command line operations."""
    
    def __init__(self, model="codellama:7b", stream=False, system_prompt=None, language="en"):
        """Initialize the AI Agent.
        
        Args:
            model: The Ollama model to use
            stream: Whether to stream responses
            system_prompt: Custom system prompt
        """
        self.model = model
        self.stream = stream
        self.language = language
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        
    def _get_default_system_prompt(self) -> str:
        """Get the default system prompt."""
        base_prompt = """You are an AI assistant specialized in analyzing software projects.
        Your task is to determine the type of project (like Flask, FastAPI, Django, etc.) 
        and suggest the optimal deployment command for AtlasServer.
        
        Use the tools provided to explore the project structure:
        - list_directory: To see the contents of directories
        - read_file: To examine key files like main.py, requirements.txt
        - execute_command: To run shell commands that help explore the filesystem
        
        Start by using execute_command with "ls -la" (or "dir" on Windows) to see the project contents.
        Then locate and read important files like:
        - app/main.py or main.py
        - requirements.txt
        - pyproject.toml
        - setup.py
        - app/__init__.py
        
        Be thorough in your analysis and explain your reasoning clearly.
        When you've completed your analysis, respond in JSON format with these fields:
        {
            "type": "Project type (Flask, FastAPI, Django, etc.)",
            "command": "Exact command to run the application",
            "environment_vars": {"ENV_VAR1": "value1", "ENV_VAR2": "value2"},
            "port": "Recommended port number",
            "reasoning": "Detailed explanation of your analysis and recommendations"
        }
        """
        
        # Agregar instrucción de idioma
        if self.language == "es":
            base_prompt += "\n\nIMPORTANT: Provide your explanation in the 'reasoning' field in Spanish, while keeping the JSON structure and field names in English."
        
        return base_prompt
    
    async def analyze_project(self, project_dir: str, callback: Optional[Callable[[str], None]] = None) -> str:
        """Analyze a project directory using tools to explore files.
        
        Args:
            project_dir: Path to the project directory
            callback: Optional callback for streaming output
            
        Returns:
            Analysis result as a string
        """
        try:
            # Verificar que el directorio existe
            if not os.path.isdir(project_dir):
                error_msg = f"El directorio '{project_dir}' no existe"
                logger.error(error_msg)
                return error_msg
                
            # Mensaje inicial
            if callback:
                callback("🔍 Explorando proyecto y leyendo archivos...\n")
            
            # Configurar herramientas
            
            tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List files and folders in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Path to the directory to list"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to read"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a shell command to navigate or explore the filesystem",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of shell commands to execute"
                            }
                        },
                        "required": ["commands"]
                    }
                }
            }
        ]
            
            # Mensaje inicial para exploración
            prompt = f"""
            I need you to thoroughly analyze the project in this directory: {project_dir}
            
            Your first steps should be:
            1. List the directory structure to understand the project organization
            2. Find and READ the main Python files (especially app/main.py if it exists)
            3. Read requirements.txt or package.json if they exist
            
            Use the available tools to explore directories and read files.
            DO NOT make assumptions about file contents - READ key files first.
            
            After exploring and reading key files, determine the project type and suggest
            the optimal deployment command for AtlasServer.
            """
            
            # Configurar mensajes
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            # Máximo de iteraciones
            max_iterations = 10
            
            # Bucle principal de análisis
            for iteration in range(max_iterations):
                if callback:
                    callback(f"\n[Iteración {iteration+1}] Analizando...\n")
                
                # Llamar al modelo (siempre sin streaming para herramientas)
                response = chat(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    stream=False  # Importante: usar False para herramientas
                )
                
                # Si no hay llamadas a herramientas, es la respuesta final
                if 'tool_calls' not in response.get('message', {}):
                    final_response = response['message'].get('content', "")
                    # Filtrar etiquetas <think>
                    final_response = re.sub(r'<think>[\s\S]*?</think>', '', final_response).strip()
                    
                    if callback:
                        callback(f"\n[Análisis Completado]\n{final_response}\n")
                    
                    return final_response
                
                # Procesar llamadas a herramientas
                tool_calls = response['message'].get('tool_calls', [])
                if not tool_calls:
                    break  # Salir si no hay herramientas para llamar
                
                # Añadir mensaje del asistente
                messages.append(response['message'])
                
                # Procesar cada herramienta
                for tool_call in tool_calls:
                    tool_name = tool_call.get('function', {}).get('name')
                    tool_id = tool_call.get('id')
                    
                    # Parsear argumentos
                    try:
                        arguments_value = tool_call.get('function', {}).get('arguments', '{}')
                        if isinstance(arguments_value, dict):
                        # Si ya es un diccionario, úsalo directamente
                            arguments = arguments_value
                        else:
                        # Si es una cadena, intenta parsearlo
                            arguments = json.loads(arguments_value)
                    except json.JSONDecodeError:
                        error_msg = f"Error al parsear argumentos de herramienta: {arguments_value}"
                        logger.error(error_msg)
                        
                        # Añadir error como resultado de herramienta
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": error_msg
                        })
                        continue
                    
                    if callback:
                        callback(f"\n[Herramienta] Ejecutando {tool_name}: {json.dumps(arguments)}\n")
                    
                    # Ejecutar herramienta
                    try:
                        result = await self._execute_tool(tool_name, arguments, project_dir)
                        
                        # Limitar tamaño para visualización
                        if callback:
                            max_display = 500  # Limitar caracteres mostrados
                            if len(result) > max_display:
                                display_result = result[:max_display] + "... [truncado]"
                            else:
                                display_result = result
                            callback(f"\n[Resultado]\n{display_result}\n")
                        
                        # Añadir resultado
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": result
                        })
                    except Exception as e:
                        error_msg = f"Error al ejecutar herramienta: {str(e)}"
                        logger.error(error_msg)
                        
                        # Añadir error como resultado
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": error_msg
                        })
            
            # Si llegamos aquí, hemos alcanzado el límite de iteraciones
            return "El análisis ha excedido el máximo de iteraciones sin llegar a una conclusión."
            
        except Exception as e:
            error_msg = f"Error durante el análisis: {str(e)}"
            logger.error(error_msg)
            return error_msg
            
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any], working_dir: str) -> str:
        """Ejecuta la herramienta especificada con los argumentos dados."""
        try:
            if tool_name == "list_directory":
                directory = arguments.get("directory", working_dir)
            
                # Convertir rutas relativas a absolutas
                if not os.path.isabs(directory):
                    directory = os.path.join(working_dir, directory)
            
                # Verificar que el directorio existe
                if not os.path.isdir(directory):
                    return f"Error: El directorio '{directory}' no existe"
                
                return list_directory(directory)
        
            elif tool_name == "read_file":
                file_path = arguments.get("file_path")
                if not file_path:
                    return "Error: No se especificó un archivo para leer"
            
                # Convertir rutas relativas a absolutas
                if not os.path.isabs(file_path):
                    file_path = os.path.join(working_dir, file_path)
            
                # Verificar que el archivo existe
                if not os.path.isfile(file_path):
                    return f"Error: El archivo '{file_path}' no existe"
                
                return read_file(file_path)
        
            elif tool_name == "execute_command":
                commands = arguments.get("commands", [])
                if not commands:
                    return "Error: No se especificaron comandos para ejecutar"
            
                from app.ai.tools import execute_command
                # Ejecutar en el directorio del proyecto
                result = execute_command(commands)
                return result
        
            else:
                return f"Error: Herramienta desconocida '{tool_name}'"
    
        except Exception as e:
            logger.error(f"Error ejecutando herramienta '{tool_name}': {str(e)}")
            return f"Error ejecutando herramienta '{tool_name}': {str(e)}"