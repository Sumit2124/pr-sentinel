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

        # Resolve provider: check each key source independently
        api_k, target_model = self._resolve_provider()

        # Build candidate models for fallback
        candidate_models = [target_model]
        if "groq" in target_model:
            # Query Groq API for live model list instead of hardcoding
            live_models = self._discover_groq_models(api_k)
            for m in live_models:
                if m not in candidate_models:
                    candidate_models.append(m)
        elif "gemini" in target_model:
            for alt in [
                "gemini/gemini-2.0-flash",
                "gemini/gemini-1.5-flash",
                "gemini/gemini-pro",
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
            except (litellm.NotFoundError, litellm.BadRequestError) as nf:
                print(f"[PR-Sentinel LLM] Model '{m}' unavailable ({type(nf).__name__}), trying next...")
                last_error = nf
                continue
            except Exception as e:
                err_msg = str(e).lower()
                if "not found" in err_msg or "decommissioned" in err_msg or "does not exist" in err_msg:
                    print(f"[PR-Sentinel LLM] Model '{m}' unavailable, trying next...")
                    last_error = e
                    continue
                raise e

        if last_error:
            raise last_error
        return ""

    def _resolve_provider(self):
        """Detect the best provider + API key + model combination."""
        # Priority 1: Explicit GROQ_API_KEY
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key and groq_key.startswith("gsk_"):
            return groq_key, "groq/openai/gpt-oss-120b"

        # Priority 2: Explicit OPENAI_API_KEY
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key and openai_key.startswith("sk-") and not openai_key.startswith("sk-live"):
            return openai_key, "gpt-4o-mini"

        # Priority 3: Explicit OPENROUTER_API_KEY
        or_key = os.environ.get("OPENROUTER_API_KEY")
        if or_key and or_key.startswith("sk-or-"):
            return or_key, "openrouter/meta-llama/llama-3.3-70b-instruct"

        # Priority 4: GEMINI_API_KEY (check if it's actually a Groq key stored under wrong name)
        gemini_key = self.api_key or settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            if gemini_key.startswith("gsk_"):
                os.environ["GROQ_API_KEY"] = gemini_key
                return gemini_key, "groq/openai/gpt-oss-120b"
            if gemini_key.startswith("sk-") and not gemini_key.startswith("sk-live"):
                os.environ["OPENAI_API_KEY"] = gemini_key
                return gemini_key, "gpt-4o-mini"
            if gemini_key.startswith("AIza"):
                return gemini_key, self.model  # Genuine Google AI Studio key
            # Unknown key format — try with configured model anyway
            return gemini_key, self.model

        return None, self.model

    @staticmethod
    def _discover_groq_models(api_key: str):
        """Query the Groq API to get currently active text generation models."""
        import urllib.request
        import urllib.error
        preferred_order = [
            "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile",
            "llama-4-scout-17b-16e-instruct",
        ]
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                available_ids = {m["id"] for m in data.get("data", [])}
                # Return models in preferred order, filtered to what's actually live
                result = []
                for model_id in preferred_order:
                    if model_id in available_ids:
                        result.append(f"groq/{model_id}")
                # Also add any other active chat models we didn't list
                for m in data.get("data", []):
                    groq_id = f"groq/{m['id']}"
                    if groq_id not in result and m.get("object") == "model":
                        result.append(groq_id)
                return result if result else [f"groq/{preferred_order[0]}"]
        except Exception as e:
            print(f"[PR-Sentinel LLM] Could not discover Groq models: {e}")
            return [f"groq/{preferred_order[0]}"]

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
