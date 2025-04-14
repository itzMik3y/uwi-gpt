#!/usr/bin/env python
"""
rag_api/llm_classes.py - Custom LLM classes for the RAG API
"""

import logging
# Updated Imports for streaming
from typing import Optional, List, Dict, Any, Iterator
from langchain.llms.base import LLM
from langchain.schema.output import GenerationChunk # Import GenerationChunk

# It's generally better to import libraries at the top level
try:
    import ollama
except ImportError:
    ollama = None # Handle gracefully if not installed

try:
    import google.generativeai as genai
except ImportError:
    genai = None # Handle gracefully if not installed


logger = logging.getLogger(__name__)

class OllamaLLM(LLM):
    """
    LLM wrapper for Ollama API.

    This class allows using local Ollama models as LangChain LLMs.
    Supports both regular calls and streaming.
    """
    model_name: str = "gemma3:12b"
    temperature: float = 0.0
    # Add other Ollama options if needed
    # top_k: Optional[int] = None
    # top_p: Optional[float] = None
    # num_predict: Optional[int] = None

    def __init__(self, model_name: str = "gemma3:12b", temperature: float = 0.0, **kwargs):
        """
        Initialize the Ollama LLM.

        Args:
            model_name: The name of the Ollama model to use
            temperature: The temperature to use for generation
            **kwargs: Additional Ollama options (e.g., top_k, top_p)
        """
        # Pass identifying params to super if required by Langchain/Pydantic validation
        super().__init__(model_name=model_name, temperature=temperature, **kwargs) # Pass relevant params up
        if ollama is None:
            raise ImportError("The 'ollama' library is required but could not be imported. Please install it.")
        # Assignment might be redundant if super() handles them, but safe to keep
        self.model_name = model_name
        self.temperature = temperature
        # Store other options if provided in kwargs
        # self.top_k = kwargs.get("top_k")
        # self.top_p = kwargs.get("top_p")
        # self.num_predict = kwargs.get("num_predict")
        self._chat_history = []  # Initialize as an instance variable

    @property
    def _llm_type(self) -> str:
        """Return the type of LLM."""
        return "ollama"

    def _get_ollama_options(self) -> Dict[str, Any]:
        """Helper to construct the options dictionary."""
        options = {
            "temperature": self.temperature,
        }
        # Add other configured options if they exist
        # if self.top_k is not None: options["top_k"] = self.top_k
        # if self.top_p is not None: options["top_p"] = self.top_p
        # if self.num_predict is not None: options["num_predict"] = self.num_predict
        return options

    def _manage_history(self, max_entries: int = 20):
         """Keep chat history to a reasonable size (pairs of user/assistant)."""
         if len(self._chat_history) > max_entries:
             # Remove the oldest pair (user + assistant)
             self._chat_history = self._chat_history[-max_entries:]


    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Call the Ollama API (non-streaming).

        Args:
            prompt: The prompt to send to the model
            stop: Optional list of stop sequences (Note: Ollama API might handle this differently in chat)

        Returns:
            The model's complete response
        """
        # Add the user's message to the chat history
        self._chat_history.append({"role": "user", "content": prompt})

        try:
            # Use ollama.chat to maintain context across calls (non-streaming)
            response = ollama.chat(
                model=self.model_name,
                messages=self._chat_history,
                stream=False, # Explicitly false for _call
                options=self._get_ollama_options(),
                # 'stop' might need to be passed via options if supported
            )

            # Extract the assistant's message from the response
            assistant_message = response.get('message', {}).get('content', '')

            # Add the assistant's response to the chat history
            self._chat_history.append({"role": "assistant", "content": assistant_message})

            # Keep chat history to a reasonable size
            self._manage_history()

            return assistant_message

        except Exception as e:
            logger.error(f"Error calling Ollama chat: {str(e)}", exc_info=True)
            # Remove the failed user message from history
            if self._chat_history and self._chat_history[-1]["role"] == "user":
                self._chat_history.pop()
            # Re-raise or return error message? LangChain expects string return
            return f"Error generating response from Ollama: {str(e)}"

    # --- Streaming Method ---
    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        """
        Stream the response from the Ollama API.

        Args:
            prompt: The prompt to send to the model
            stop: Optional list of stop sequences
            **kwargs: Additional keyword arguments (currently unused but required by interface)

        Yields:
            GenerationChunk: Chunks of the generated text
        """
        # Add the user's message *before* starting the stream
        self._chat_history.append({"role": "user", "content": prompt})
        accumulated_response = ""

        try:
            stream = ollama.chat(
                model=self.model_name,
                messages=self._chat_history, # Send current history
                stream=True,
                options=self._get_ollama_options(),
                # 'stop' might need to be passed via options if supported
            )

            for chunk in stream:
                message_chunk_content = chunk.get('message', {}).get('content')
                if message_chunk_content:
                    accumulated_response += message_chunk_content
                    yield GenerationChunk(text=message_chunk_content)
                # Check for stream end/metadata if needed (e.g., Ollama provides total duration)
                # done = chunk.get('done', False)
                # if done:
                #     logger.debug(f"Ollama stream finished. Stats: {chunk}")

            # After the stream finishes, add the complete assistant message to history
            self._chat_history.append({"role": "assistant", "content": accumulated_response})
            self._manage_history()

        except Exception as e:
            logger.error(f"Error streaming from Ollama chat: {str(e)}", exc_info=True)
             # Remove the failed user message from history
            if self._chat_history and self._chat_history[-1]["role"] == "user":
                self._chat_history.pop()
             # Yield the error message as the final chunk in the stream
            yield GenerationChunk(text=f"\nError during Ollama stream: {str(e)}")

    def clear_history(self):
        """Clear the chat history."""
        self._chat_history = []
        logger.debug("Ollama chat history cleared.")

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return the identifying parameters of the LLM."""
        # Include any other options set during init
        params = {"model_name": self.model_name, "temperature": self.temperature}
        # params.update({k: getattr(self, k) for k in ["top_k", "top_p", "num_predict"] if getattr(self, k) is not None})
        return params


class GeminiLLM(LLM):
    """
    LLM wrapper for Google's Gemini API.

    This class allows using Google's Gemini models as LangChain LLMs.
    Supports both regular calls and streaming.
    """

    # Consider using a model known for good chat performance like 'gemini-pro' or newer ones
    model_name: str = "models/gemini-1.5-flash-latest" # Updated model example
    temperature: float = 0.0
    top_p: Optional[float] = None # Gemini often uses default unless specified
    top_k: Optional[int] = None  # Gemini often uses default unless specified
    max_output_tokens: int = 2048 # More reasonable default
    # Define api_key as a class variable that Pydantic will validate
    api_key: str

    def __init__(self, api_key: str, model_name: str = "models/gemini-1.5-flash-latest",
                 temperature: float = 0.0, top_p: Optional[float] = None, top_k: Optional[int] = None,
                 max_output_tokens: int = 2048, **kwargs):
        """
        Initialize the Gemini LLM.

        Args:
            api_key: The API key for accessing Gemini (REQUIRED).
            model_name: The name of the Gemini model to use.
            temperature: The temperature to use for generation.
            top_p: The top_p value to use for generation.
            top_k: The top_k value to use for generation.
            max_output_tokens: The maximum number of tokens to generate.
            **kwargs: Additional arguments passed to the parent class.
        """
        # --- FIX APPLIED HERE ---
        # Pass the api_key and other relevant parameters explicitly to the superclass constructor.
        # This ensures Pydantic validation running during super().__init__ sees the required fields.
        super().__init__(
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_output_tokens,
            **kwargs
        )
        # --- END FIX ---

        if genai is None:
            raise ImportError("The 'google-generativeai' library is required but could not be imported. Please install it.")

        # The check below might be slightly redundant now if super().__init__ validation passed,
        # but it's a good safeguard.
        if not api_key:
            raise ValueError("Gemini API key is required.")

        # Assign attributes (may be redundant if super() handled them, but explicit is okay)
        # Note: We already passed these to super(), so self.api_key etc. should be set by Pydantic/BaseModel now.
        # Re-assigning them here is generally safe but potentially unnecessary.
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.max_output_tokens = max_output_tokens
        self._chat_history = []  # Initialize chat history

        # Configure the Gemini API (consider doing this once globally if possible)
        try:
            # Use self.api_key which should be correctly set by now
            genai.configure(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}", exc_info=True)
            # Depending on severity, might want to raise here

    @property
    def _llm_type(self) -> str:
        """Return the type of LLM."""
        return "gemini"

    def _get_generation_config(self) -> Dict[str, Any]:
        """Helper to construct the generation config."""
        config = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.top_p is not None: config["top_p"] = self.top_p
        if self.top_k is not None: config["top_k"] = self.top_k
        # Add stop sequences if needed: config["stop_sequences"] = stop
        return config

    def _get_chat_model(self) -> Any:
        """Helper to initialize the generative model and start chat."""
        if genai is None: # Check again in case it failed during init
            raise ImportError("Gemini library ('google-generativeai') is not available.")

        model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=self._get_generation_config()
            # safety_settings can be added here if needed
        )
        # Convert history to Gemini's format (parts must be non-empty)
        gemini_history = []
        for msg in self._chat_history:
            role = "user" if msg["role"] == "user" else "model"
            content = msg.get("content")
            # Gemini API requires non-empty parts
            if content is not None and content.strip():
                gemini_history.append({"role": role, "parts": [content]})
            elif msg["role"] == "user": # Need at least placeholder for user turn if content was empty
                gemini_history.append({"role": role, "parts": [" "]}) # Or handle differently


        # Start chat with history *excluding* the latest user prompt (which is handled by send_message)
        # The API expects the history to be valid turns up to the point *before* the user's new message
        chat = model.start_chat(history=gemini_history)
        return chat

    def _manage_history(self, max_entries: int = 20):
         """Keep chat history to a reasonable size (pairs of user/assistant)."""
         if len(self._chat_history) > max_entries:
             # Remove the oldest pair (user + assistant)
             self._chat_history = self._chat_history[-max_entries:]


    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Call the Gemini API (non-streaming).

        Args:
            prompt: The prompt to send to the model
            stop: Optional list of stop sequences (pass via generation_config if needed)

        Returns:
            The model's complete response
        """
        # Add user message to LangChain history
        self._chat_history.append({"role": "user", "content": prompt})

        try:
            chat = self._get_chat_model() # Gets model and chat with history up to *before* current prompt

            # Send the latest prompt (non-streaming)
            # Note: Pass 'stop' sequences via generation_config if needed during model init
            response = chat.send_message(prompt, stream=False)

            # Extract content safely
            assistant_message = ""
            try:
                # Accessing response.text directly is common
                assistant_message = response.text
            except ValueError as ve:
                # Handle cases where response might be blocked (e.g., safety settings)
                logger.warning(f"Gemini response might be empty or blocked: {ve}. Parts: {getattr(response, 'parts', [])}. Prompt Feedback: {getattr(response, 'prompt_feedback', None)}")
                # Check if there's candidate info even if .text fails
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    assistant_message = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text'))
                if not assistant_message:
                    assistant_message = f"Error: Gemini response was empty or blocked. Finish reason: {getattr(response.candidates[0], 'finish_reason', 'Unknown')}"


            # Add the assistant's response to LangChain history
            self._chat_history.append({"role": "assistant", "content": assistant_message})

            self._manage_history()

            return assistant_message
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}", exc_info=True)
            # Remove the failed user message from history
            if self._chat_history and self._chat_history[-1]["role"] == "user":
                self._chat_history.pop()
            return f"Error generating response from Gemini: {str(e)}"

    # --- Streaming Method ---
    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        """
        Stream the response from the Gemini API.

        Args:
            prompt: The prompt to send to the model
            stop: Optional list of stop sequences (pass via generation_config)
            **kwargs: Additional keyword arguments

        Yields:
            GenerationChunk: Chunks of the generated text
        """
        # Add user message to LangChain history *before* streaming
        self._chat_history.append({"role": "user", "content": prompt})
        accumulated_response = ""

        try:
            chat = self._get_chat_model() # Gets model and chat with history up to *before* current prompt

            # Send the latest prompt (streaming)
            response_stream = chat.send_message(prompt, stream=True)

            for chunk in response_stream:
                # Sometimes chunks might be empty or lack text, handle safely
                chunk_text = ""
                try:
                     # Accessing chunk.text is common
                     chunk_text = chunk.text
                except ValueError as ve:
                     # Handle cases where response might be blocked during streaming
                     logger.warning(f"Gemini stream chunk might be empty or blocked: {ve}. Parts: {getattr(chunk, 'parts', [])}. Prompt Feedback: {getattr(chunk, 'prompt_feedback', None)}")
                     # Check candidates like in _call
                     if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                        chunk_text = "".join(p.text for p in chunk.candidates[0].content.parts if hasattr(p, 'text'))
                     if not chunk_text:
                         chunk_text = f"\nWarning: Gemini stream chunk blocked. Finish reason: {getattr(chunk.candidates[0], 'finish_reason', 'Unknown')}\n"


                if chunk_text:
                    accumulated_response += chunk_text
                    yield GenerationChunk(text=chunk_text)

            # After the stream finishes, add the complete assistant message to LangChain history
            self._chat_history.append({"role": "assistant", "content": accumulated_response})
            self._manage_history()

        except Exception as e:
            logger.error(f"Error streaming from Gemini API: {str(e)}", exc_info=True)
            # Remove the failed user message from history
            if self._chat_history and self._chat_history[-1]["role"] == "user":
                self._chat_history.pop()
            yield GenerationChunk(text=f"\nError during Gemini stream: {str(e)}")


    def clear_history(self):
        """Clear the chat history."""
        self._chat_history = []
        logger.debug("Gemini chat history cleared.")

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return the identifying parameters of the LLM."""
        # Don't include the API key for security/privacy in logs/outputs
        params = {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens
        }
        if self.top_p is not None: params["top_p"] = self.top_p
        if self.top_k is not None: params["top_k"] = self.top_k
        # Ensure all relevant identifying params passed to super().__init__ are included here if needed
        return params