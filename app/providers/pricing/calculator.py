PRICING_MAP = {
    "gpt-4o-mini": {
        "input_cost_per_token": 0.15 / 1_000_000,
        "output_cost_per_token": 0.60 / 1_000_000
    },
    "gemini-1.5-flash": {
        "input_cost_per_token": 0.075 / 1_000_000,
        "output_cost_per_token": 0.30 / 1_000_000
    },
    "gemini-2.5-flash": {
        "input_cost_per_token": 0.075 / 1_000_000,
        "output_cost_per_token": 0.30 / 1_000_000
    },
    "claude-3-5-haiku": {
        "input_cost_per_token": 0.80 / 1_000_000,
        "output_cost_per_token": 4.00 / 1_000_000
    },
    "claude-3-5-sonnet": {
        "input_cost_per_token": 3.00 / 1_000_000,
        "output_cost_per_token": 15.00 / 1_000_000
    }
}

DEFAULT_PRICING = {
    "input_cost_per_token": 10.00 / 1_000_000,
    "output_cost_per_token": 30.00 / 1_000_000
}

def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    # Lowercase match
    normalized_name = model_name.lower()
    
    # Try to find a substring match in the map
    pricing = DEFAULT_PRICING
    for key, val in PRICING_MAP.items():
        if key in normalized_name:
            pricing = val
            break
            
    input_cost = input_tokens * pricing["input_cost_per_token"]
    output_cost = output_tokens * pricing["output_cost_per_token"]
    return input_cost + output_cost
