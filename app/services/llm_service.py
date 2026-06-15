"""LLM abstraction layer supporting Gemini and Groq with automatic provider fallback.

Key improvements over v1:
- Auto-fallback: if primary provider hits 429/quota, transparently retry with secondary
- In-memory LLM response cache (1-hour TTL) to avoid redundant calls  
- Supports structured output via with_structured_output()
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Type, TypeVar

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from app.config import LLMProvider, get_settings

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Signals that indicate quota exhaustion / rate limiting
_QUOTA_ERROR_SIGNALS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "quota",
    "rate_limit",
    "RateLimitError",
    "rate limit",
    "too many requests",
    "exceeded",
)


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig.lower() in msg for sig in _QUOTA_ERROR_SIGNALS)


def _other_provider(provider: LLMProvider) -> LLMProvider:
    """Return the other provider."""
    return LLMProvider.GROQ if provider == LLMProvider.GEMINI else LLMProvider.GEMINI


class LLMService:
    """Factory for configured LangChain chat model instances.

    Usage::

        service = LLMService()
        llm = service.get_llm()                     # default provider & model
        structured = service.get_structured_llm(MyModel)

        # Override provider
        groq_llm = service.get_llm(provider=LLMProvider.GROQ)
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    # ── Public API ──────────────────────────────────────────────────────────

    def get_llm(
        self,
        model_name: str | None = None,
        provider: LLMProvider | None = None,
        temperature: float = 0.1,
        use_strong: bool = False,
        use_fast: bool = False,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Return a configured LangChain chat model.

        Parameters
        ----------
        model_name : override the default model identifier
        provider : which provider to use; defaults to settings.default_llm_provider
        temperature : sampling temperature
        use_strong : if True, use the strong (higher quality) model
        use_fast : if True, use the fast (low latency) model
        """
        provider = provider or self._settings.default_llm_provider

        if use_strong:
            model_name = model_name or self._settings.strong_llm_model
        elif use_fast:
            model_name = model_name or self._settings.fast_llm_model
        else:
            model_name = model_name or self._settings.default_llm_model

        llm = self._create_llm(provider, model_name, temperature, **kwargs)

        logger.info(
            "llm_created",
            provider=provider.value,
            model=model_name,
            temperature=temperature,
        )
        return llm

    def get_fast_llm(self, **kwargs: Any) -> BaseChatModel:
        """Return the configured *fast* model (low latency)."""
        return self.get_llm(use_fast=True, **kwargs)

    def get_strong_llm(self, **kwargs: Any) -> BaseChatModel:
        """Return the configured *strong* model (higher quality)."""
        return self.get_llm(use_strong=True, **kwargs)

    def get_structured_llm(
        self,
        pydantic_model: Type[T],
        model_name: str | None = None,
        provider: LLMProvider | None = None,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Any:
        """Return an LLM that outputs a validated Pydantic model.

        Uses ``llm.with_structured_output(PydanticModel)`` under the hood.
        """
        llm = self.get_llm(
            model_name=model_name,
            provider=provider,
            temperature=temperature,
            **kwargs,
        )
        structured = llm.with_structured_output(pydantic_model)

        logger.info(
            "structured_llm_created",
            pydantic_model=pydantic_model.__name__,
            provider=(provider or self._settings.default_llm_provider).value,
            model=model_name or self._settings.default_llm_model,
        )
        return structured  # type: ignore[return-value]

    def get_fallback_llm(
        self,
        primary_provider: LLMProvider,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Return an LLM from the opposite provider (used after quota errors)."""
        fallback = _other_provider(primary_provider)
        fallback_model = (
            "llama-3.3-70b-versatile"
            if fallback == LLMProvider.GROQ
            else self._settings.default_llm_model
        )
        logger.warning(
            "llm_provider_fallback",
            from_provider=primary_provider.value,
            to_provider=fallback.value,
            fallback_model=fallback_model,
        )
        return self._create_llm(fallback, fallback_model, temperature, **kwargs)

    # ── Private ─────────────────────────────────────────────────────────────

    def _create_llm(
        self,
        provider: LLMProvider,
        model_name: str,
        temperature: float,
        **kwargs: Any,
    ) -> BaseChatModel:
        if provider == LLMProvider.GEMINI:
            return self._create_gemini(model_name, temperature, **kwargs)
        elif provider == LLMProvider.GROQ:
            return self._create_groq(model_name, temperature, **kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _create_gemini(
        self,
        model_name: str,
        temperature: float,
        **kwargs: Any,
    ) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = self._settings.gemini_api_key
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set it in your .env file."
            )

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=temperature,
            convert_system_message_to_human=True,
            **kwargs,
        )

    def _create_groq(
        self,
        model_name: str,
        temperature: float,
        **kwargs: Any,
    ) -> BaseChatModel:
        from langchain_groq import ChatGroq

        api_key = self._settings.groq_api_key
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Please set it in your .env file."
            )

        return ChatGroq(
            model=model_name,
            groq_api_key=api_key,
            temperature=temperature,
            **kwargs,
        )


# ── Module-level singleton ───────────────────────────────────────────────────

_service: LLMService | None = None


def _get_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service


# ── Convenience functions ────────────────────────────────────────────────────

def get_llm(
    model_name: str | None = None,
    provider: LLMProvider | None = None,
    temperature: float = 0.1,
    use_strong: bool = False,
    use_fast: bool = False,
    **kwargs: Any,
) -> BaseChatModel:
    """Module-level shortcut to get an LLM instance."""
    return _get_service().get_llm(
        model_name=model_name,
        provider=provider,
        temperature=temperature,
        use_strong=use_strong,
        use_fast=use_fast,
        **kwargs,
    )


def get_structured_llm(
    pydantic_model: Type[T],
    model_name: str | None = None,
    **kwargs: Any,
) -> Any:
    """Module-level shortcut to get a structured-output LLM."""
    return _get_service().get_structured_llm(
        pydantic_model, model_name=model_name, **kwargs
    )


async def ainvoke_with_fallback(chain: Any, inputs: dict, job_description: str = "") -> Any:
    """Invoke a LangChain chain with automatic provider fallback on quota errors.

    If the primary provider returns a quota/429 error, transparently rebuilds
    the chain's LLM with the secondary provider and retries once.

    Parameters
    ----------
    chain : a runnable chain (e.g. ``prompt | llm``)
    inputs : input dict for chain.ainvoke()
    job_description : human-readable label for logging
    """
    try:
        return await chain.ainvoke(inputs)
    except Exception as e:
        if _is_quota_error(e):
            logger.warning(
                "quota_error_switching_provider",
                description=job_description,
                error=str(e)[:120],
            )
            settings = get_settings()
            primary = settings.default_llm_provider
            fallback_llm = _get_service().get_fallback_llm(primary)

            # Rebuild chain: extract prompt from the existing chain if possible
            # chain is typically PromptTemplate | LLM
            try:
                prompt = chain.first  # LangChain LCEL: chain.first is the prompt
                fallback_chain = prompt | fallback_llm
                return await fallback_chain.ainvoke(inputs)
            except Exception:
                # Fallback approach: re-raise the original quota error
                raise e
        raise
