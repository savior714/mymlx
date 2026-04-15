"""Model discovery and resolution from local paths or Hugging Face Hub."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_model_path_cache: dict[tuple[str, str], str] = {}

def _resolve_model_cached(model_name: str, local_models_root: str) -> str:
    """Cache-backed model path resolution — avoids filesystem I/O on every request."""
    key = (model_name, local_models_root)
    cached = _model_path_cache.get(key)
    if cached is not None:
        return cached
    resolved = resolve_model_path(model_name, local_models_root)
    _model_path_cache[key] = resolved
    return resolved

def search_huggingface_models(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search Hugging Face Hub for MLX or general models."""
    from huggingface_hub import HfApi

    api = HfApi()
    try:
        # 1. Search for MLX-specific models first if query is broad
        tags = ["mlx"]
        models = api.list_models(search=query, tags=tags, limit=limit, sort="downloads", direction=-1)
        
        # 2. If no MLX models, search general
        results = list(models)
        if not results:
            models = api.list_models(search=query, limit=limit, sort="downloads", direction=-1)
            results = list(models)
        
        return [
            {
                "id": m.modelId,
                "downloads": getattr(m, "downloads", 0),
                "lastModified": getattr(m, "lastModified", ""),
                "tags": getattr(m, "tags", []),
            }
            for m in results
        ]
    except Exception as e:
        logger.error(f"HF search failed: {e}")
        return []

def resolve_model_path(model_id: str, local_models_root: str) -> str:
    """Resolve model path: 1. Absolute/Existing 2. Desktop models root 3. HF ID."""
    from pathlib import Path
    
    # 1. Existing path
    p = Path(model_id)
    if p.exists():
        return model_id
        
    # 2. Desktop models root
    root = Path(local_models_root).expanduser()
    possible = root / model_id
    if possible.exists() and possible.is_dir():
        logger.debug(f"Resolved model via Desktop models root: {possible}")
        return str(possible)
        
    # 3. HF ID Search (if not a path and no slash)
    if "/" not in model_id:
        resolved = resolve_hf_model_id(model_id)
        if resolved != model_id:
            logger.info(f"Resolved model '{model_id}' to '{resolved}' via HF Search")
            return resolved
            
    return model_id

def resolve_hf_model_id(model_id: str) -> str:
    """Try to find the full Org/Repo if a partial name is given."""
    if "/" in model_id:
        return model_id
    
    # Try searching for exact match or best match with the short name
    results = search_huggingface_models(model_id, limit=5)
    if not results:
        return model_id
        
    # If any result's id ends with /model_id, return the first one (most downloads)
    for r in results:
        if r["id"].endswith(f"/{model_id}"):
            return r["id"]
            
    # Fallback to the most downloaded match if it seems very related
    if results[0]["id"].lower().endswith(model_id.lower()):
         return results[0]["id"]
         
    return model_id
