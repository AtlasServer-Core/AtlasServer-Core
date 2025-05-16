# app/ai/tools.py
import platform
import logging
from typing import List, Any, Optional
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

def get_shell_tool() -> ShellTool:
    """Get a shell tool for command execution.
    
    Args:
        working_directory: Directory to execute commands in (default: current directory)
    
    Returns:
        ShellTool instance
    """
    try:
        # Check if we're on Windows, where ShellTool has limitations
        if get_os() == "Windows":
            logger.warning("ShellTool has limited support on Windows OS.")
        
        # Create the shell tool with the specified working directory
        shell_tool = ShellTool()
        return shell_tool
    except Exception as e:
        logger.error(f"Error creating ShellTool: {str(e)}")
        raise

def get_filesystem_tools(root_dir: Optional[str] = None) -> List[Any]:
    """Get tools for file system operations.
    
    Args:
        root_dir: Root directory to restrict file operations (default: current directory)
    
    Returns:
        List of filesystem tools
    """
    try:
        # Get all file management tools or a subset based on security considerations
        toolkit = FileManagementToolkit(
            root_dir=root_dir,
            selected_tools=[
                "read_file", 
                "write_file", 
                "list_directory",
                "file_search",
                "move_file",
                "copy_file"
            ]
        )
        return toolkit.get_tools()
    except Exception as e:
        logger.error(f"Error creating FileManagementToolkit: {str(e)}")
        raise