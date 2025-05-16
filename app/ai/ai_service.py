# app/ai/ai_service.py
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class AIService:
    """Base class for AI services."""
    
    def __init__(self, model: str):
        """Initialize the AI service.
        
        Args:
            model: Model identifier to use
        """
        self.model = model
    
    async def generate_response(self, prompt: str, structured_output: bool = False) -> str:
        """Generate a response from the AI service.
        
        Args:
            prompt: User's query or instruction
            structured_output: Whether the response should be structured (e.g., JSON)
            
        Returns:
            Model's response as a string
        """
        raise NotImplementedError("The base service does not implement generate_response")

class OllamaService(AIService):
    """AI service using local Ollama models."""
    
    def __init__(self, model: str = "codellama:7b"):
        """Initialize the Ollama service.
        
        Args:
            model: Ollama model identifier (default: codellama:7b)
        """
        super().__init__(model)
        
    async def generate_response(self, prompt: str, structured_output: bool = False) -> str:
        """Generate a response using Ollama.
        
        Args:
            prompt: User's query or instruction
            structured_output: Whether the response should be structured (e.g., JSON)
            
        Returns:
            Model's response as a string
        """
        try:
            from ollama import chat
            
            # Prepare system prompt
            system_prompt = """You are an AI assistant specialized in application deployment.
            Your task is to analyze code and configurations to suggest deployment strategies.
            Be precise and concise in your responses."""
            
            if structured_output:
                system_prompt += """ Respond only in valid JSON format with no additional text.
                Ensure your response can be parsed directly by json.loads()."""
                
            # Call the Ollama API
            response = chat(
                model=self.model,
                messages=[
                    {
                        'role': 'system',
                        'content': system_prompt
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            )
            
            return response['message']['content']
        except Exception as e:
            logger.error(f"Error generating response with Ollama: {str(e)}")
            return f"Error generating response: {str(e)}"

async def get_ai_service(provider: str = "ollama", model: str = "qwen3:8b", api_key: Optional[str] = None) -> AIService:
    """Factory to get the appropriate AI service implementation.
    
    Args:
        provider: AI service provider (e.g., "ollama")
        model: Model identifier
        api_key: API key for the service (if required)
        
    Returns:
        AIService instance
    """
    if provider.lower() == "ollama":
        return OllamaService(model=model)
    else:
        # In Core, we only support Ollama
        logger.warning(f"Provider {provider} not supported in AtlasServer-Core. Using Ollama.")
        return OllamaService(model=model)