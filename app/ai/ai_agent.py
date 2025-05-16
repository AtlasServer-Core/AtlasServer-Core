from ollama import chat, ChatResponse
import os

class AgentCLI:
    def __init__(self, model, stream=False, systemprompt=None, tools=None):
        self.model = model
        self.stream = stream
        self.systemprompt = systemprompt
        self.tools = tools