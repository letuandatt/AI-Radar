"""Ollama local LLM integration using LangChain."""

from .ollama_client import create_ollama_chat_model

__all__ = ["create_ollama_chat_model"]
