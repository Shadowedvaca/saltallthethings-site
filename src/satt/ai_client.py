"""Async AI client — raw httpx calls to Anthropic and OpenAI.

No Anthropic or OpenAI Python SDKs — uses httpx directly to keep the
dependency footprint minimal and consistent with the original JS approach.
"""

from __future__ import annotations

import base64
import httpx

from satt.config import get_settings


async def call_claude(
    system_prompt: str,
    user_prompt: str,
    config: dict,
    images: list[dict] | None = None,
) -> str:
    """Call Anthropic API. Returns raw text response.

    images: optional list of {"data": "<base64>", "mime_type": "image/jpeg"}
    """
    settings = get_settings()

    if images:
        content: list | str = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img["mime_type"],
                    "data": img["data"],
                },
            }
            for img in images
        ] + [{"type": "text", "text": user_prompt}]
    else:
        content = user_prompt

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
                "messages": [{"role": "user", "content": content}],
            },
        )
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        block["text"] for block in data["content"] if block.get("type") == "text"
    )


async def call_openai(
    system_prompt: str,
    user_prompt: str,
    config: dict,
    images: list[dict] | None = None,
) -> str:
    """Call OpenAI API. Returns raw text response.

    images: optional list of {"data": "<base64>", "mime_type": "image/jpeg"}
    """
    settings = get_settings()

    if images:
        user_content: list | str = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['mime_type']};base64,{img['data']}",
                    "detail": "high",
                },
            }
            for img in images
        ] + [{"type": "text", "text": user_prompt}]
    else:
        user_content = user_prompt

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
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.7,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"] or ""


async def call_ai(
    system_prompt: str,
    user_prompt: str,
    config: dict,
    images: list[dict] | None = None,
) -> str:
    """Dispatch to call_claude or call_openai based on config.aiModel."""
    ai_model = config.get("aiModel", "claude")
    if ai_model == "claude":
        return await call_claude(system_prompt, user_prompt, config, images)
    if ai_model == "openai":
        return await call_openai(system_prompt, user_prompt, config, images)
    raise ValueError(f"Unknown AI model: {ai_model!r}")


async def call_gpt_image_1(prompt: str, config: dict) -> bytes:
    """Call gpt-image-1 via /v1/images/generations. Returns raw PNG bytes.

    Note: the public images API does not support image reference inputs —
    that capability is ChatGPT-interface-only. Style context is handled via
    the GPT-4o art direction step instead.
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.ai_request_timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {config['openaiApiKey']}",
                "content-type": "application/json",
            },
            json={
                "model": "gpt-image-1",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "medium",
                "response_format": "b64_json",
            },
        )
    resp.raise_for_status()
    data = resp.json()
    b64 = data["data"][0].get("b64_json") or data["data"][0].get("url")
    if not b64:
        raise ValueError(f"No image data in gpt-image-1 response: {data}")
    return base64.b64decode(b64)


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
