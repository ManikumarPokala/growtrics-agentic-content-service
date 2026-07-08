import asyncio
import random
import time
from typing import Dict, Tuple, Type
from pydantic import BaseModel
from app.domain.interfaces import LLMProvider
from app.core.exceptions import LLMProviderError, RateLimitError, JSONParseError
from app.providers.pricing.calculator import calculate_cost

class BaseLLMProvider(LLMProvider):
    def __init__(self, model_name: str):
        self.model_name = model_name

    def _strip_markdown_fences(self, text: str) -> str:
        """Strips markdown block wraps (e.g. ```json ... ```) to extract raw JSON."""
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        return stripped

    async def _execute_with_retry(self, api_call_func, *args, **kwargs) -> Tuple[str, Dict[str, any]]:
        """
        Executes the raw API call function with exponential backoff and jitter.
        Returns:
            Tuple[raw_response_string, metadata_dict]
        """
        base_delay = 2.0
        multiplier = 2.0
        max_retries = 4
        jitter_factor = 0.1

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                # Run the actual API call
                raw_response, input_tokens, output_tokens = await api_call_func(*args, **kwargs)
                latency_ms = int((time.time() - start_time) * 1000)

                cost = calculate_cost(self.model_name, input_tokens, output_tokens)

                metadata = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": latency_ms,
                    "cost": cost,
                    "model": self.model_name
                }
                return raw_response, metadata

            except Exception as e:
                last_exception = e
                # Classify exception
                error_str = str(e).lower()
                is_rate_limit = "429" in error_str or "rate limit" in error_str
                is_server_error = "500" in error_str or "503" in error_str or "timeout" in error_str or "connection" in error_str

                is_retryable = is_rate_limit or is_server_error

                if not is_retryable or attempt == max_retries:
                    # Non-retryable or we exhausted our retries
                    if is_rate_limit:
                        raise RateLimitError(f"LLM Provider rate limit exceeded: {str(e)}")
                    else:
                        raise LLMProviderError(f"LLM Provider error: {str(e)}", is_retryable=is_retryable)

                # Calculate backoff delay with jitter
                delay = base_delay * (multiplier ** attempt)
                jitter = delay * jitter_factor * random.uniform(-1, 1)
                final_delay = max(0.1, delay + jitter)

                await asyncio.sleep(final_delay)

        raise LLMProviderError(f"Failed after retries. Last error: {str(last_exception)}")
