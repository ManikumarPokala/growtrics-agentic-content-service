import json
from typing import Dict, Tuple, Type
from pydantic import BaseModel
import google.generativeai as genai
from app.core.config import settings
from app.core.exceptions import JSONParseError
from app.providers.llm.base import BaseLLMProvider

class GeminiProvider(BaseLLMProvider):
    def __init__(self, model_name: str = None, api_key: str = None):
        model = model_name or "gemini-1.5-flash"
        super().__init__(model)
        self.api_key = api_key or settings.GEMINI_API_KEY
        if self.api_key:
            genai.configure(api_key=self.api_key)

    async def generate_structured_output(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        response_model: Type[BaseModel], 
        temperature: float = 0.2
    ) -> Tuple[BaseModel, Dict[str, any]]:
        if not self.api_key:
            raise ValueError("Gemini API key is missing. Please set it in your environment / .env file.")

        async def _call_api():
            # Create the generative model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt
            )
            
            # Enforce JSON output format
            generation_config = genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=temperature
            )
            
            # Call the async generate method
            response = await model.generate_content_async(
                contents=user_prompt,
                generation_config=generation_config
            )
            
            content = response.text or ""
            # Estimate token usage if metadata is unavailable
            usage = response.usage_metadata
            input_tokens = usage.prompt_token_count if usage else len(system_prompt + user_prompt) // 4
            output_tokens = usage.candidates_token_count if usage else len(content) // 4
            
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
                message=f"Failed to parse Gemini structured output: {str(e)}",
                raw_content=raw_text
            )
