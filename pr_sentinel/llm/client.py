import os
import json
import re
from typing import Dict, Any, Optional, Type, TypeVar
from pydantic import BaseModel
import litellm
from pr_sentinel.config import settings

# Suppress noisy litellm logs
litellm.suppress_debug_info = True

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Unified LLM client for Gemini, OpenAI, Claude, and Ollama."""

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
    ):
        self.model = model or settings.llm_model
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.api_key = api_key

        # Inject environment keys if present in settings
        if settings.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        if settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Standard raw text completion."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        api_k = self.api_key or settings.gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        
        # Candidate model names to try in order if the primary model throws 404 Not Found
        candidate_models = [self.model]
        if "gemini" in self.model:
            for alt in [
                "gemini/gemini-1.5-flash-002",
                "gemini/gemini-1.5-flash-latest",
                "gemini/gemini-2.0-flash",
                "gemini/gemini-1.5-flash",
                "gemini/gemini-pro",
                "gemini/gemini-1.5-pro-002",
            ]:
                if alt not in candidate_models:
                    candidate_models.append(alt)

        last_error = None
        for m in candidate_models:
            try:
                response = litellm.completion(
                    model=m,
                    messages=messages,
                    temperature=self.temperature,
                    api_key=api_k,
                )
                self.model = m  # Keep the working model
                return response.choices[0].message.content or ""
            except litellm.NotFoundError as nf:
                last_error = nf
                continue
            except Exception as e:
                raise e

        if last_error:
            raise last_error
        return ""

    def complete_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema_model: Optional[Type[T]] = None,
        mock_fallback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generates structured JSON adhering to the specified schema model."""
        enhanced_system = (system_prompt or "") + "\n\nYou MUST respond strictly in valid JSON matching the requested structure. Do not output markdown blocks or conversational text outside the JSON object."
        
        try:
            raw_text = self.complete(prompt, system_prompt=enhanced_system)
            return self._extract_json(raw_text)
        except Exception as e:
            print(f"[PR-Sentinel LLM] Warning: LLM completion error ({type(e).__name__}): {e}")
            if mock_fallback is not None:
                return mock_fallback
            raise RuntimeError(f"Failed LLM structured generation: {e}")

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extracts JSON object from text even if enclosed in markdown code fences."""
        text = text.strip()
        # Remove ```json ... ``` wrapper if present
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if json_match:
            text = json_match.group(1).strip()
        
        # Try direct load
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find first { and last }
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1:
                sub_text = text[first_brace : last_brace + 1]
                return json.loads(sub_text)
            raise ValueError(f"Could not parse valid JSON from text: {text[:200]}...")
