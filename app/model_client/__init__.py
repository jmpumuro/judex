"""
Model Client - HTTP client for calling Model Service.
Allows the app to run without models loaded locally.
"""
from app.model_client.client import ModelClient, get_model_client

__all__ = ["ModelClient", "get_model_client"]
