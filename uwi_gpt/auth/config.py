# auth/config.py
from pydantic_settings import BaseSettings
from datetime import timedelta

class JWTSettings(BaseSettings):
    jwt_secret_key: str = "YOUR_SECRET_KEY_CHANGE_THIS_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Convert to seconds for consistency in expiration time calculations
    @property
    def access_token_expire_seconds(self) -> int:
        return self.access_token_expire_minutes * 60
    
    @property
    def refresh_token_expire_seconds(self) -> int:
        return self.refresh_token_expire_days * 24 * 60 * 60

    class Config:
        env_prefix = "JWT_"  # Load settings from environment variables with JWT_ prefix

# Load settings from environment variables
jwt_settings = JWTSettings()