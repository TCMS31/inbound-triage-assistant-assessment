"""Built-in LLM providers.

Importing this package registers every built-in provider under its
`LLM_PROVIDER` name. Third-party providers can call `register_provider`
themselves without touching this file.
"""

from triage_backend.classification.providers.anthropic_provider import AnthropicProvider
from triage_backend.classification.providers.openai_provider import OpenAIProvider
from triage_backend.classification.providers.stub_provider import StubProvider

__all__ = ["AnthropicProvider", "OpenAIProvider", "StubProvider"]
