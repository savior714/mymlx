from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from mlx_server.proxy import run_unload


class _StubPromptCache:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


def test_run_unload_clears_provider_and_prompt_cache(monkeypatch) -> None:
    class _StubMetal:
        @staticmethod
        def is_available() -> bool:
            return False

    class _StubMx:
        metal = _StubMetal()

    monkeypatch.setitem(sys.modules, "mlx.core", _StubMx())

    model_provider = SimpleNamespace(
        model=object(),
        tokenizer=object(),
        model_key=("some-model", None, None),
        draft_model=object(),
    )
    prompt_cache = _StubPromptCache()
    backend = SimpleNamespace(model_provider=model_provider, prompt_cache=prompt_cache)

    asyncio.run(run_unload(backend))  # type: ignore[arg-type]

    assert model_provider.model is None
    assert model_provider.tokenizer is None
    assert model_provider.model_key is None
    assert model_provider.draft_model is None
    assert prompt_cache.cleared is True
