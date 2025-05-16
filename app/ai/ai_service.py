# app/ai/ai_service.py 
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class AIService:
    """Base class for AI services."""
    
    def __init__(self, model: str):
        self.model = model
    
    async def generate_response(self, prompt: str, structured_output: bool = False) -> str:
        """Generate a response from the AI service."""
        raise NotImplementedError("The base service does not implement generate_response")
        
    async def generate_response_stream(self, prompt: str, callback: Callable[[str], None]) -> str:
        """Generate a streaming response with callback for each chunk."""
        raise NotImplementedError("The base service does not implement streaming")

class OllamaService(AIService):
    """AI service using local Ollama models."""
    
    def __init__(self, model: str = "qwen3:8b"):
        super().__init__(model)
        
    async def generate_response(self, prompt: str, structured_output: bool = False) -> str:
        try:
            from ollama import chat
            
            # Prepare system prompt
            system_prompt = """You are an AI assistant specialized in application deployment.
            Your task is to analyze code and configurations to suggest deployment strategies.
            Be precise and provide detailed reasoning for your suggestions."""
            
            if structured_output:
                system_prompt += """ Include a 'reasoning' field in your JSON response that 
                explains the rationale behind your suggestions in detail."""
                
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
            
    async def generate_response_stream(self, prompt: str, callback: Callable[[str], None]) -> str:
        """Generate streaming response with Ollama.
        
        Args:
            prompt: User query or instruction
            callback: Function to call with each chunk of text
            
        Returns:
            Complete response when finished
        """
        try:
            from ollama import chat
            
            # Prepare system prompt
            system_prompt = """You are an AI assistant specialized in application deployment.
            Your task is to analyze code and configurations to suggest deployment strategies.
            Be precise and provide detailed reasoning for your suggestions."""
            
            # Call Ollama API with streaming
            full_response = ""
            for chunk in chat(
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
                ],
                stream=True
            ):
                if 'message' in chunk and 'content' in chunk['message']:
                    text_chunk = chunk['message']['content']
                    full_response += text_chunk
                    callback(text_chunk)
            
            return full_response
        except Exception as e:
            error_msg = f"Error generating streaming response: {str(e)}"
            logger.error(error_msg)
            callback(error_msg)
            return error_msg

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