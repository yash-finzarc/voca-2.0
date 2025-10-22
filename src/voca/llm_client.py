from typing import Dict, Optional

import logging
import time
import google.generativeai as genai

from src.voca.config import Config


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key if api_key is not None else Config.gemini_api_key
        genai.configure(api_key=key)
        self.model_name = model or "gemini-2.5-flash"
        self.model = genai.GenerativeModel(self.model_name)
        self.log = logging.getLogger("voca.llm")

    def is_configured(self) -> bool:
        return bool(Config.gemini_api_key)

    def complete_chat(self, messages: list[Dict[str, str]], temperature: float = None, max_tokens: int = None) -> str:
        temperature = Config.llm_temperature if temperature is None else temperature
        max_tokens = Config.llm_max_tokens if max_tokens is None else max_tokens
        # Convert OpenAI-style messages to a single prompt with system + user
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        user = "\n".join(m["content"] for m in messages if m["role"] == "user")
        prompt = (system + "\n\n" + user).strip() if system else user
        self.log.info(f"LLM request: model={self.model_name}, temp={temperature}, max_tokens={max_tokens}")
        last_err = None
        for attempt in range(1, Config.llm_retries + 1):
            try:
                resp = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        candidate_count=1,
                        top_p=0.9,
                        top_k=40,
                    ),
                )
                text = resp.text.strip() if hasattr(resp, "text") and resp.text else ""
                if not text:
                    self.log.warning(f"Empty response from Gemini. Response object: {resp}")
                    # Check if response was blocked
                    if hasattr(resp, 'candidates') and resp.candidates:
                        candidate = resp.candidates[0]
                        if hasattr(candidate, 'finish_reason'):
                            self.log.warning(f"Finish reason: {candidate.finish_reason}")
                        if hasattr(candidate, 'safety_ratings'):
                            self.log.warning(f"Safety ratings: {candidate.safety_ratings}")
                    text = "I apologize, but I couldn't generate a response to that question."
                self.log.info(f"LLM response length={len(text)} chars")
                return text
            except Exception as e:
                last_err = e
                self.log.warning(f"LLM call failed (attempt {attempt}/{Config.llm_retries}): {e}")
                time.sleep(min(2 * attempt, 5))
        raise RuntimeError(f"LLM call failed after {Config.llm_retries} attempts: {last_err}")


