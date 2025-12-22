"""
Twilio configuration and credentials management for VOCA project.
"""
import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class TwilioConfig:
    """Twilio configuration settings."""
    account_sid: str
    auth_token: str
    phone_number: str
    webhook_url: str
    api_key_sid: Optional[str] = None
    api_key_secret: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'TwilioConfig':
        """Load configuration from environment variables."""
        return cls(
            account_sid=os.getenv('TWILIO_ACCOUNT_SID', ''),
            auth_token=os.getenv('TWILIO_AUTH_TOKEN', ''),
            phone_number=os.getenv('TWILIO_PHONE_NUMBER', ''),
            webhook_url=os.getenv('TWILIO_WEBHOOK_URL', ''),
            api_key_sid=os.getenv('TWILIO_API_KEY_SID'),
            api_key_secret=os.getenv('TWILIO_API_KEY_SECRET')
        )
    
    def validate(self) -> bool:
        """Validate that required configuration is present."""
        required_fields = [self.account_sid, self.auth_token, self.phone_number]
        return all(field for field in required_fields)
    
    def get_webhook_url(self, base_url: str = "http://172.105.50.83:8000") -> str:
        """Get the webhook URL for Twilio callbacks."""
        if self.webhook_url:
            return self.webhook_url
        # Default to Linode server IP if webhook_url not set
        return f"{base_url}/webhook/voice"


# Global configuration instance - will be loaded when first accessed
twilio_config = None

def get_twilio_config():
    """Get the global Twilio configuration, loading it if necessary."""
    global twilio_config
    if twilio_config is None:
        twilio_config = TwilioConfig.from_env()
    return twilio_config
