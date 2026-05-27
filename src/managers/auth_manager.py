# -*- coding: utf-8 -*-
import keyring
from typing import Optional
from src.utils.logger import logger

class ApiKeyManager:
    """Manages secure storage and retrieval of API keys using the system's keyring."""
    
    def store_key(self, service_name: str, api_key: str) -> bool:
        """Stores an API key for a given service in the system's keyring."""
        try:
            # We use 'api_key' as the username to store one secret per service
            keyring.set_password(service_name, "api_key", api_key)
            logger.info(f"Successfully stored API key for '{service_name}' in keyring.")
            return True
        except Exception as e:
            logger.error(f"Failed to store API key for '{service_name}': {e}")
            return False

    def get_key(self, service_name: str) -> Optional[str]:
        """Retrieves an API key for a given service from the system's keyring."""
        try:
            api_key = keyring.get_password(service_name, "api_key")
            if api_key:
                logger.info(f"Successfully retrieved API key for '{service_name}'.")
            else:
                logger.debug(f"No saved API key found for '{service_name}'.")
            return api_key
        except Exception as e:
            logger.error(f"Failed to retrieve API key for '{service_name}': {e}")
            return None

class CredentialManager:
    """
    Manages secure storage and retrieval of user credentials 
    (usernames and passwords) using the system's keyring.
    """
    def __init__(self, service_namespace: str = "PySatTrack"):
        # Create a unique service name for the application
        self.base_service = service_namespace

    def store_credentials(self, account_type: str, username: str, password: str) -> bool:
        """Stores a username and password for a specific account type (e.g., Space-Track)."""
        if not username or not password:
            logger.error("CredentialManager: Username and password cannot be empty.")
            return False
        
        service_id = f"{self.base_service}-{account_type}"
        try:
            keyring.set_password(service_id, username, password)
            logger.info(f"Stored credentials for '{username}' in '{service_id}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to store credentials in keyring: {e}")
            return False

    def get_password(self, account_type: str, username: str) -> Optional[str]:
        """Retrieves a password for a given username and account type."""
        service_id = f"{self.base_service}-{account_type}"
        try:
            password = keyring.get_password(service_id, username)
            if password:
                logger.info(f"Retrieved stored password for '{username}' from '{service_id}'.")
            return password
        except Exception as e:
            logger.error(f"Failed to retrieve credentials from keyring: {e}")
            return None