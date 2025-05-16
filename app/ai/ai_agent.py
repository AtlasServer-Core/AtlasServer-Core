# app/ai/ai_agent.py
import logging
from typing import List, Dict, Any
import json
from ollama import chat
from app.ai.tools import get_shell_tool, get_filesystem_tools, search

logger = logging.getLogger(__name__)

class AgentCLI:
    """AI Agent for command line operations."""
    
    def __init__(self, model="codellama:7b", stream=False, system_prompt=None, tools=None):
        """Initialize the AI Agent.
        
        Args:
            model: Ollama model to use
            stream: Whether to stream responses
            system_prompt: Custom system prompt to set agent behavior
            tools: List of tools to provide to the agent
        """
        self.model = model
        self.stream = stream
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        self.tools = tools or self._get_default_tools()
        
    def _get_default_system_prompt(self) -> str:
        """Get the default system prompt for the agent."""
        return """You are an AI assistant specialized in development and deployment tasks.
        Help users analyze and deploy applications efficiently using AtlasServer.
        Be concise, accurate, and focus on practical solutions."""
    
    def _get_default_tools(self) -> List[Dict[str, Any]]:
        """Get the default set of tools for the agent."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "commands": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "The commands to execute"
                            },
                            "directory": {
                                "type": "string",
                                "description": "The directory to execute the command in"
                            }
                        },
                        "required": ["commands"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "List files in a directory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Directory path to list (defaults to current)"
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
            }
        ]
    
    async def run(self, prompt: str, tools_enabled: bool = True):
        """Run the agent with the given prompt.
        
        Args:
            prompt: User's query or request
            tools_enabled: Whether to enable tools for this request
            
        Returns:
            Agent's response
        """
        try:
            # Initialize messages with system prompt
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            # Call Ollama chat API
            response = chat(
                model=self.model,
                messages=messages,
                stream=self.stream,
                tools=self.tools if tools_enabled else None
            )
            
            # If tool calls were made, we need to process them
            if not self.stream and 'tool_calls' in response.get('message', {}):
                return await self._process_tool_calls(response, messages)
            
            return response
        except Exception as e:
            logger.error(f"Error running agent: {str(e)}")
            return {"error": str(e)}
    
    async def _process_tool_calls(self, response, messages):
        """Process tool calls from the model response.
        
        Args:
            response: Initial model response with tool calls
            messages: Current message history
            
        Returns:
            Updated response after tool execution
        """
        tool_calls = response['message'].get('tool_calls', [])
        
        if not tool_calls:
            return response
        
        # Add the assistant's message with tool calls
        messages.append(response['message'])
        
        # Process each tool call
        for tool_call in tool_calls:
            tool_name = tool_call.get('function', {}).get('name')
            arguments = json.loads(tool_call.get('function', {}).get('arguments', '{}'))
            
            # Execute the appropriate tool
            tool_result = await self._execute_tool(tool_name, arguments)
            
            # Add the tool response to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get('id'),
                "name": tool_name,
                "content": str(tool_result)
            })
        
        # Get a new response from the model with the tool results
        final_response = chat(
            model=self.model,
            messages=messages,
            stream=self.stream
        )
        
        return final_response
    
    async def _execute_tool(self, tool_name, arguments):
        """Execute the specified tool with the given arguments.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
            
        Returns:
            Result from the tool execution
        """
        try:
            if tool_name == "search":
                return search(arguments.get("query", ""))
            
            elif tool_name == "execute_command":
                commands = arguments.get("commands", [])
                directory = arguments.get("directory")
                
                shell_tool = get_shell_tool()
                return shell_tool.run({"commands": commands})
            
            elif tool_name == "list_directory":
                directory = arguments.get("directory", ".")
                
                # Get just the list directory tool
                fs_tools = get_filesystem_tools(root_dir=None)
                list_dir_tool = next((t for t in fs_tools if t.__class__.__name__ == "ListDirectoryTool"), None)
                
                if list_dir_tool:
                    return list_dir_tool.invoke({"directory": directory})
                else:
                    return f"Error: Could not find list directory tool"
            
            elif tool_name == "read_file":
                file_path = arguments.get("file_path")
                
                # Get just the read file tool
                fs_tools = get_filesystem_tools(root_dir=None)
                read_file_tool = next((t for t in fs_tools if t.__class__.__name__ == "ReadFileTool"), None)
                
                if read_file_tool:
                    return read_file_tool.invoke({"file_path": file_path})
                else:
                    return f"Error: Could not find read file tool"
            
            else:
                return f"Error: Unknown tool '{tool_name}'"
        
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {str(e)}")
            return f"Error executing tool '{tool_name}': {str(e)}"