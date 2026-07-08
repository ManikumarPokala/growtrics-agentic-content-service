import json
from typing import Dict, Tuple, Type
from pydantic import BaseModel
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.exceptions import JSONParseError
from app.providers.llm.base import BaseLLMProvider

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model_name: str = None, api_key: str = None):
        model = model_name or settings.DEFAULT_MODEL
        super().__init__(model)
        key = api_key or settings.OPENAI_API_KEY
        self.client = AsyncOpenAI(api_key=key) if key else None

    async def generate_structured_output(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Type[BaseModel], 
        temperature: float = 0.2
    ) -> Tuple[BaseModel, Dict[str, any]]:
        if not self.client:
            raise ValueError("OpenAI API key is missing. Please set it in your environment / .env file.")

        async def _call_api():
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content or ""
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            return content, input_tokens, output_tokens

        # Run with backoff retry wrapper
        raw_text, metadata = await self._execute_with_retry(_call_api)
        
        # Clean JSON markdown fences
        clean_json_str = self._strip_markdown_fences(raw_text)
        
        try:
            parsed_dict = json.loads(clean_json_str)
            response_instance = response_model.model_validate(parsed_dict)
            return response_instance, metadata
        except Exception as e:
            raise JSONParseError(
                message=f"Failed to parse LLM structured output: {str(e)}",
                raw_content=raw_text
            )
