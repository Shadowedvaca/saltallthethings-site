"""Async AI client — raw httpx calls to Anthropic and OpenAI.

No Anthropic or OpenAI Python SDKs — uses httpx directly to keep the
dependency footprint minimal and consistent with the original JS approach.
"""

from __future__ import annotations

import base64
import httpx

from satt.config import get_settings


async def call_claude(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Call Anthropic API. Returns raw text response."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config["claudeApiKey"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.get("claudeModelId") or "claude-sonnet-4-5-20250929",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        block["text"] for block in data["content"] if block.get("type") == "text"
    )


async def call_openai(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Call OpenAI API. Returns raw text response."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config['openaiApiKey']}",
                "content-type": "application/json",
            },
            json={
                "model": config.get("openaiModelId") or "gpt-4o",
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"] or ""


async def call_ai(system_prompt: str, user_prompt: str, config: dict) -> str:
    """Dispatch to call_claude or call_openai based on config.aiModel."""
    ai_model = config.get("aiModel", "claude")
    if ai_model == "claude":
        return await call_claude(system_prompt, user_prompt, config)
    if ai_model == "openai":
        return await call_openai(system_prompt, user_prompt, config)
    raise ValueError(f"Unknown AI model: {ai_model!r}")


async def call_dalle(prompt: str, config: dict) -> bytes:
    """Call DALL-E 3 image generation. Returns raw PNG bytes."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {config['openaiApiKey']}",
                "content-type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "b64_json",
            },
        )
    resp.raise_for_status()
    data = resp.json()
    b64 = data["data"][0]["b64_json"]
    return base64.b64decode(b64)
