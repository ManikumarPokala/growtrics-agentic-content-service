class GrowtricsException(Exception):
    """Base exception for Growtrics Content Service"""
    pass

class PipelineError(GrowtricsException):
    """Raised when the multi-agent pipeline encounters an unrecoverable failure"""
    pass

class LLMProviderError(GrowtricsException):
    """Raised when an external LLM provider fails"""
    def __init__(self, message: str, is_retryable: bool = False):
        super().__init__(message)
        self.is_retryable = is_retryable

class RateLimitError(LLMProviderError):
    """Raised when the LLM provider rate limits the request (HTTP 429)"""
    def __init__(self, message: str):
        super().__init__(message, is_retryable=True)

class JSONParseError(GrowtricsException):
    """Raised when the generated LLM response is not valid JSON or violates schema constraints"""
    def __init__(self, message: str, raw_content: str):
        super().__init__(message)
        self.raw_content = raw_content

class DatabaseError(GrowtricsException):
    """Raised when database interactions fail"""
    pass

class HeartbeatTimeoutError(GrowtricsException):
    """Raised when a job heartbeat has expired"""
    pass
