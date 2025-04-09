#!/usr/bin/env python
"""
rag_api/llm_classes.py - Custom LLM classes for the RAG API
"""

import logging
from typing import Optional, List, Dict, Any
from langchain.llms.base import LLM

logger = logging.getLogger(__name__)

class OllamaLLM(LLM):
    """
    LLM wrapper for Ollama API.
    
    This class allows using local Ollama models as LangChain LLMs.
    """
    model_name: str = "gemma3:12b"
    temperature: float = 0.0
    
    def __init__(self, model_name: str = "gemma3:12b", temperature: float = 0.0):
        """
        Initialize the Ollama LLM.
        
        Args:
            model_name: The name of the Ollama model to use
            temperature: The temperature to use for generation
        """
        super().__init__()
        self.model_name = model_name
        self.temperature = temperature
        self._chat_history = []  # Initialize as an instance variable
    
    @property
    def _llm_type(self) -> str:
        """Return the type of LLM."""
        return "ollama"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Call the Ollama API.
        
        Args:
            prompt: The prompt to send to the model
            stop: Optional list of stop sequences
            
        Returns:
            The model's response
        """
        try:
            import ollama
            
            # Add the user's message to the chat history
            self._chat_history.append({"role": "user", "content": prompt})
            
            # Use ollama.chat to maintain context across calls
            response = ollama.chat(
                model=self.model_name,
                messages=self._chat_history,
                options={
                    "temperature": self.temperature,
                    # Add other options as needed
                    # "num_predict": 128,
                    # "top_k": 40,
                    # "top_p": 0.9,
                }
            )
            
            # Extract the assistant's message from the response
            assistant_message = response.get('message', {}).get('content', '')
            
            # Add the assistant's response to the chat history
            self._chat_history.append({"role": "assistant", "content": assistant_message})
            
            # Keep chat history to a reasonable size to prevent context overflow
            if len(self._chat_history) > 20:  # Adjust this limit as needed
                # Remove oldest messages but keep the most recent ones
                self._chat_history = self._chat_history[-20:]
            
            return assistant_message
        except Exception as e:
            logger.error(f"Error calling Ollama chat: {str(e)}")
            return f"Error generating response: {str(e)}"
    
    def clear_history(self):
        """Clear the chat history."""
        self._chat_history = []
    
    @property
    def _identifying_params(self):
        """Return the identifying parameters of the LLM."""
        return {"model_name": self.model_name, "temperature": self.temperature}


class GeminiLLM(LLM):
    """
    LLM wrapper for Google's Gemini API.
    
    This class allows using Google's Gemini models as LangChain LLMs.
    """
    
    model_name: str = "models/gemini-2.0-flash-lite"
    temperature: float = 0.0
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 2048
    
    def __init__(self, api_key: str, model_name: str = "models/gemini-2.0-flash-lite", 
                 temperature: float = 0.0, top_p: float = 0.95, top_k: int = 40,
                 max_output_tokens: int = 2048):
        """
        Initialize the Gemini LLM.
        
        Args:
            api_key: The API key for accessing Gemini
            model_name: The name of the Gemini model to use
            temperature: The temperature to use for generation
            top_p: The top_p value to use for generation
            top_k: The top_k value to use for generation
            max_output_tokens: The maximum number of tokens to generate
        """
        super().__init__()
        self._api_key = api_key  # Store as private attribute
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.max_output_tokens = max_output_tokens
        self._chat_history = []  # Initialize chat history
        
        # Configure the Gemini API
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
    
    @property
    def _llm_type(self) -> str:
        """Return the type of LLM."""
        return "gemini"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Call the Gemini API.
        
        Args:
            prompt: The prompt to send to the model
            stop: Optional list of stop sequences
            
        Returns:
            The model's response
        """
        try:
            import google.generativeai as genai
            
            # Add the user's message to the chat history
            self._chat_history.append({"role": "user", "content": prompt})
            
            # Initialize the model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "max_output_tokens": self.max_output_tokens,
                }
            )
            
            # Convert chat history to Gemini's format
            chat_history = []
            for msg in self._chat_history:
                if msg["role"] == "user":
                    chat_history.append({"role": "user", "parts": [msg["content"]]})
                elif msg["role"] == "assistant":
                    chat_history.append({"role": "model", "parts": [msg["content"]]})
            
            # Start a chat session based on history
            chat = model.start_chat(history=chat_history[:-1] if len(chat_history) > 1 else [])
            
            # Get response for the last message
            response = chat.send_message(chat_history[-1]["parts"][0])
            
            # Extract content
            assistant_message = response.text
            
            # Add the assistant's response to the chat history
            self._chat_history.append({"role": "assistant", "content": assistant_message})
            
            # Keep chat history to a reasonable size to prevent context overflow
            if len(self._chat_history) > 20:  # Adjust this limit as needed
                self._chat_history = self._chat_history[-20:]
            
            return assistant_message
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            return f"Error generating response: {str(e)}"
    
    def clear_history(self):
        """Clear the chat history."""
        self._chat_history = []
    
    @property
    def _identifying_params(self):
        """Return the identifying parameters of the LLM."""
        # Don't include the API key in the identifying parameters
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens
        }