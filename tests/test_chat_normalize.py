"""Unit tests for chat payload normalization (no MLX required)."""

from __future__ import annotations

from mlx_server.proxy import _normalize_chat_messages_for_mlx


def test_normalize_keeps_string_content() -> None:
    data = {"messages": [{"role": "user", "content": "hello"}]}
    _normalize_chat_messages_for_mlx(data)
    assert data["messages"][0]["content"] == "hello"


def test_normalize_concatenates_text_parts() -> None:
    data = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "a"},
                    {"type": "text", "text": "b"},
                ],
            }
        ]
    }
    _normalize_chat_messages_for_mlx(data)
    assert data["messages"][0]["content"] == "ab"


def test_normalize_drops_nontext_parts() -> None:
    data = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "see image:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/x.png"},
                    },
                ],
            }
        ]
    }
    _normalize_chat_messages_for_mlx(data)
    assert data["messages"][0]["content"] == "see image:"


def test_normalize_skips_non_list_messages() -> None:
    data: dict = {"messages": "not-a-list"}
    _normalize_chat_messages_for_mlx(data)
    assert data["messages"] == "not-a-list"
