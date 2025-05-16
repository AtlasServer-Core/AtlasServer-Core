# app/ai/ai_cli.py
import os
import json
import logging
from typing import Dict, Any, Optional, Callable
import re


from app.ai.ai_service import get_ai_service

logger = logging.getLogger(__name__)

class AtlasServerAICLI:
    """Class that handles AI functionality for the AtlasServer CLI."""
    
    def __init__(self, config_path=None):
        """Initialize AI service for CLI.
        
        Args:
            config_path: Path to the configuration file (optional)
        """
        from platformdirs import user_data_dir
        data_dir = user_data_dir("atlasserver", "AtlasServer-Core")
        os.makedirs(data_dir, exist_ok=True)
        
        self.config_path = config_path or os.path.join(data_dir, "ai_config.json")
        self.ai_config = self._load_config()
        self.ai_service = None  # Will be initialized on demand
    
    def _load_config(self) -> Dict[str, Any]:
        """Load AI configuration from file.
        
        Returns:
            Configuration dictionary
        """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading AI configuration: {str(e)}")
                return {"provider": "ollama", "model": "qwen3:8b"}
        return {"provider": "ollama", "model": "qwen3:8b"}
    
    def setup(self, provider: str, model: str, api_key: Optional[str] = None) -> bool:
        """Configure the AI service.
        
        Args:
            provider: AI service provider
            model: Model identifier
            api_key: API key for the service (if required)
            
        Returns:
            True if configuration was saved successfully, False otherwise
        """
        self.ai_config = {
            "provider": provider,
            "model": model,
        }
        
        if api_key:
            self.ai_config["api_key"] = api_key
            
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(self.ai_config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving AI configuration: {str(e)}")
            return False
    
    async def _ensure_ai_service(self):
        """Initialize AI service if not already available."""
        if not self.ai_service:
            self.ai_service = await get_ai_service(
                provider=self.ai_config.get("provider", "ollama"),
                model=self.ai_config.get("model", "codellama:7b"),
                api_key=self.ai_config.get("api_key")
            )
    
    def _collect_project_info(self, directory: str) -> Dict[str, Any]:
        """Collect project information for analysis.
        
        Args:
            directory: Project directory path
            
        Returns:
            Dictionary with project information
        """
        info = {
            "directory_structure": "",
            "package_json": "",
            "requirements_txt": "",
            "main_files": []
        }
        
        # Get directory structure (limit to 100 files)
        file_list = []
        for root, dirs, files in os.walk(directory):
            rel_path = os.path.relpath(root, directory)
            if rel_path == '.':
                for file in files[:20]:  # Limit files in root directory
                    file_list.append(file)
            else:
                file_list.append(f"{rel_path}/")
                for file in files[:5]:  # Some files per subdirectory
                    file_list.append(f"{rel_path}/{file}")
            
            if len(file_list) > 100:  # Limit total size
                file_list.append("... (more files)")
                break
                
        info["directory_structure"] = "\n".join(file_list)
        
        # Read package.json if exists
        package_json_path = os.path.join(directory, "package.json")
        if os.path.exists(package_json_path):
            try:
                with open(package_json_path, "r") as f:
                    info["package_json"] = f.read()
            except Exception:
                info["package_json"] = "Error reading package.json"
        
        # Read requirements.txt if exists
        requirements_path = os.path.join(directory, "requirements.txt")
        if os.path.exists(requirements_path):
            try:
                with open(requirements_path, "r") as f:
                    info["requirements_txt"] = f.read()
            except Exception:
                info["requirements_txt"] = "Error reading requirements.txt"
        
        # Find and read important files
        important_files = [
            "app.py", "main.py", "index.py", "server.py", 
            "wsgi.py", "asgi.py", "manage.py"
        ]
        
        for filename in important_files:
            file_path = os.path.join(directory, filename)
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        content = f.read(1000)  # First 1000 chars
                        info["main_files"].append({
                            "name": filename,
                            "content": content
                        })
                except Exception:
                    pass
        
        return info
    
    async def suggest_deployment_command(self, directory: str, stream: bool = False, 
                                     callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """Analyze a project and suggest the optimal deployment command.
        
        Args:
            directory: Project directory path
            stream: Whether to stream the response
            callback: Function to call with each chunk in streaming mode
            
        Returns:
            Deployment suggestion with detailed explanation
        """
        await self._ensure_ai_service()
        
        # Collect project information
        project_info = self._collect_project_info(directory)
        
        # Generate prompt for AI
        prompt = f"""
        Analyze this project structure and suggest the best command to deploy it with AtlasServer:
        
        Directory structure: 
        {project_info['directory_structure']}
        
        Package.json (if exists):
        {project_info['package_json']}
        
        Requirements.txt (if exists):
        {project_info['requirements_txt']}
        
        Main files:
        {json.dumps([f["name"] for f in project_info["main_files"]])}
        
        Please provide a detailed analysis including:
        1. The project type (Flask, FastAPI, Django, Node, Express, Next.js, etc.)
        2. The exact command to deploy it
        3. Required environment variables
        4. Recommended port
        5. DETAILED EXPLANATION of your reasoning and analysis
        
        Respond in JSON format with this structure:
        {{
            "type": "Project type",
            "command": "Deployment command",
            "environment_vars": {{"VAR1": "value1", "VAR2": "value2"}},
            "port": "Recommended port",
            "reasoning": "Your detailed explanation of the analysis and recommendations"
        }}
        """
        
        # Choose between streaming and regular response
        if stream and callback:
            raw_response = await self.ai_service.generate_response_stream(prompt, callback)
        else:
            raw_response = await self.ai_service.generate_response(prompt, structured_output=True)
        
        # Parse and format the response
        return self._parse_deployment_suggestion(raw_response)
        
    def _parse_deployment_suggestion(self, response: str) -> Dict[str, Any]:
        """Parse AI response and format it."""
        try:
            # Try to parse as JSON
            data = json.loads(response)
            return {
                "detected_type": data.get("type", "Unknown"),
                "command": data.get("command", ""),
                "environment_vars": data.get("environment_vars", {}),
                "port": data.get("port", ""),
                "reasoning": data.get("reasoning", "No detailed explanation provided.")
            }
        except json.JSONDecodeError:
            # Fallback for when response is not JSON
            detected_type_match = re.search(r"type of project[:\s]+([\w\s\.\-]+)", response, re.IGNORECASE)
            command_match = re.search(r"command[:\s]+([\w\s\.\-]+)", response, re.IGNORECASE)
            port_match = re.search(r"port[:\s]+(\d+)", response, re.IGNORECASE)
            
            # Try to extract reasoning
            reasoning_match = re.search(r"reasoning[:\s]+([\s\S]+?)(?=\n\n|\Z)", response, re.IGNORECASE)
            
            return {
                "detected_type": detected_type_match.group(1) if detected_type_match else "Unknown",
                "command": command_match.group(1) if command_match else "",
                "environment_vars": {},
                "port": port_match.group(1) if port_match else "",
                "reasoning": reasoning_match.group(1).strip() if reasoning_match else response
            }