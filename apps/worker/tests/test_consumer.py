from pathlib import Path

import pytest

from dndn_worker.consumer import ConsumerConfig, _parse_payload, _resolve_heartbeat_interval_seconds


def test_parse_payload_returns_dict():
    payload = _parse_payload('{"type":"WEEKLY","account_id":"123456789012"}')

    assert payload["type"] == "WEEKLY"
    assert payload["account_id"] == "123456789012"


def test_parse_payload_rejects_non_object_json():
    with pytest.raises(ValueError, match="JSON object payload"):
        _parse_payload('["not", "an", "object"]')


def test_resolve_heartbeat_interval_returns_zero_without_visibility_timeout():
    config = ConsumerConfig(
        queue_url="https://example.com/queue",
        repo_root=Path("."),
        out_root=Path("out"),
        visibility_timeout=None,
        heartbeat_interval_seconds=0,
    )

    assert _resolve_heartbeat_interval_seconds(config) == 0


def test_resolve_heartbeat_interval_auto_calculates_from_visibility_timeout():
    config = ConsumerConfig(
        queue_url="https://example.com/queue",
        repo_root=Path("."),
        out_root=Path("out"),
        visibility_timeout=30,
        heartbeat_interval_seconds=0,
    )

    assert _resolve_heartbeat_interval_seconds(config) == 10


def test_resolve_heartbeat_interval_rejects_visibility_timeout_one():
    config = ConsumerConfig(
        queue_url="https://example.com/queue",
        repo_root=Path("."),
        out_root=Path("out"),
        visibility_timeout=1,
        heartbeat_interval_seconds=0,
    )

    with pytest.raises(ValueError, match="greater than 1"):
        _resolve_heartbeat_interval_seconds(config)


def test_resolve_heartbeat_interval_rejects_invalid_custom_interval():
    config = ConsumerConfig(
        queue_url="https://example.com/queue",
        repo_root=Path("."),
        out_root=Path("out"),
        visibility_timeout=30,
        heartbeat_interval_seconds=30,
    )

    with pytest.raises(ValueError, match="smaller than visibility timeout"):
        _resolve_heartbeat_interval_seconds(config)
