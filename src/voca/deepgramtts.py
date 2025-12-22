"""
Deepgram Text-to-Speech (TTS) integration for VOCA.
Converts LLM-generated text responses to speech using Deepgram's Aura models.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Union, BinaryIO

from deepgram import DeepgramClient

from src.voca.config import Config


class DeepgramTTS:
    """
    Deepgram Text-to-Speech service.
    Converts text to speech using Deepgram's Aura models.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "aura-2-thalia-en",
        output_format: str = "mp3",
    ):
        """
        Initialize Deepgram TTS client.
        
        Args:
            api_key: Deepgram API key (defaults to Config.deepgram_api_key)
            model: Deepgram TTS model to use (default: "aura-2-thalia-en")
            output_format: Audio output format (default: "mp3")
        """
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or Config.deepgram_api_key
        
        if not self.api_key:
            raise ValueError("Deepgram API key is required. Set DEEPGRAM_API_KEY environment variable.")
        
        self.model = model
        self.output_format = output_format
        self.client = DeepgramClient(api_key=self.api_key)
        self._is_ready = False
        
        # Try to initialize on creation
        try:
            self.load()
        except Exception as e:
            self.logger.warning(f"Failed to initialize Deepgram TTS on creation: {e}")
    
    def load(self):
        """Load/initialize the TTS service."""
        try:
            # Test the connection by creating a client
            # The actual API call happens in speak()
            self._is_ready = True
            self.logger.info(f"Deepgram TTS initialized with model: {self.model}")
        except Exception as e:
            self.logger.error(f"Failed to load Deepgram TTS: {e}")
            self._is_ready = False
            raise
    
    def is_ready(self) -> bool:
        """Check if TTS service is ready."""
        return self._is_ready and self.client is not None
    
    def get_model_info(self) -> dict:
        """
        Get real-time model information.
        
        Returns:
            Dictionary with model information including model name, output format, and readiness status
        """
        return {
            "model": self.model,
            "output_format": self.output_format,
            "is_ready": self.is_ready(),
        }
    
    def speak(
        self,
        text: str,
        output_path: Optional[Union[str, Path]] = None,
        return_bytes: bool = False,
    ) -> Optional[bytes]:
        """
        Convert text to speech.
        
        Args:
            text: Text to convert to speech (from LLM response)
            output_path: Optional path to save audio file. If None and return_bytes=False, uses temp file.
            return_bytes: If True, returns audio bytes instead of saving to file.
        
        Returns:
            Audio bytes if return_bytes=True, otherwise None (file is saved)
        """
        if not self.is_ready():
            self.logger.error("Deepgram TTS is not ready")
            raise RuntimeError("Deepgram TTS is not ready. Call load() first.")
        
        if not text or not text.strip():
            self.logger.warning("Empty text provided to TTS")
            return None
        
        try:
            # Map output_format to Deepgram encoding parameter
            encoding_map = {
                "mp3": "mp3",
                "wav": "linear16",  # WAV typically uses linear16
                "ogg": "opus",
                "flac": "flac",
            }
            encoding = encoding_map.get(self.output_format.lower(), "mp3")
            
            self.logger.debug(f"Generating speech for text (length: {len(text)} chars) with model {self.model}")
            
            # Use Deepgram SDK v3 API: client.speak.v1.audio.generate()
            # This returns an Iterator[bytes]
            audio_stream = self.client.speak.v1.audio.generate(
                text=text.strip(),
                model=self.model,
                encoding=encoding,
            )
            
            # Collect all audio bytes from the iterator
            audio_bytes = b"".join(audio_stream)
            
            if not audio_bytes:
                self.logger.error("No audio data received from Deepgram")
                return None
            
            if return_bytes:
                # Return bytes directly
                self.logger.debug(f"Generated {len(audio_bytes)} bytes of audio")
                return audio_bytes
            else:
                # Save to file - use temp file if no output_path provided
                if output_path is None:
                    # Use temp file if no path provided
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{self.output_format}") as tmp_file:
                        output_path = tmp_file.name
                
                output_path_str = str(output_path)
                with open(output_path_str, 'wb') as f:
                    f.write(audio_bytes)
                
                if os.path.exists(output_path_str):
                    file_size = os.path.getsize(output_path_str)
                    self.logger.info(f"Generated speech saved to {output_path_str} ({file_size} bytes)")
                    return None
                else:
                    self.logger.error(f"Failed to save audio file to {output_path_str}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error generating speech with Deepgram: {e}")
            raise
    
    def speak_to_file(
        self,
        text: str,
        output_path: Union[str, Path],
    ) -> bool:
        """
        Convert text to speech and save to file.
        
        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.speak(text, output_path=output_path, return_bytes=False)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save speech to file: {e}")
            return False
    
    def speak_to_bytes(self, text: str) -> Optional[bytes]:
        """
        Convert text to speech and return as bytes.
        
        Args:
            text: Text to convert to speech
        
        Returns:
            Audio bytes or None if failed
        """
        try:
            return self.speak(text, return_bytes=True)
        except Exception as e:
            self.logger.error(f"Failed to generate speech bytes: {e}")
            return None
    
    def speak_to_stream(
        self,
        text: str,
        stream: BinaryIO,
    ) -> bool:
        """
        Convert text to speech and write to a binary stream.
        
        Args:
            text: Text to convert to speech
            stream: Binary stream to write audio to
        
        Returns:
            True if successful, False otherwise
        """
        try:
            audio_bytes = self.speak_to_bytes(text)
            if audio_bytes:
                stream.write(audio_bytes)
                stream.flush()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to write speech to stream: {e}")
            return False


# Example usage:
if __name__ == "__main__":
    # Example: Convert LLM response to speech
    llm_response = "Your lab results show elevated cholesterol levels of 240 mg/dL; I recommend starting Atorvastatin 10 mg daily and scheduling a follow-up in eight weeks to reassess."
    
    # Initialize TTS
    tts = DeepgramTTS(
        model="aura-2-thalia-en",
    )
    
    try:
        # Method 1: Save to file
        output_file = "audio.mp3"
        tts.speak_to_file(llm_response, output_file)
        print(f"Audio saved to {output_file}")
        
        # Method 2: Get as bytes
        audio_bytes = tts.speak_to_bytes(llm_response)
        if audio_bytes:
            print(f"Generated {len(audio_bytes)} bytes of audio")
        
        # Method 3: Use speak() directly
        tts.speak(llm_response, output_path="audio2.mp3")
        print("Audio saved to audio2.mp3")
        
    except Exception as e:
        print(f"Error: {e}")

