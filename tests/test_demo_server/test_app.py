"""Tests for the local-only killer-demo FastAPI backend."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cloakroom.demo_server.app import DemoRuntime, create_app, demo_url, validate_bind_host


@pytest.fixture
def client(tmp_path):
    runtime = DemoRuntime(tmp_path / "demo-runtime")
    return TestClient(create_app(runtime))


def test_demo_server_shield_restore_and_trust_center(client):
    sample = client.post(
        "/api/demo/load-sample",
        json={"name": "customer_escalation_en.md"},
    )
    assert sample.status_code == 200
    original_text = sample.json()["original_text"]
    assert "Sarah Morgan" in original_text

    shield = client.post(
        "/api/shield",
        json={
            "text": original_text,
            "sample_name": "customer_escalation_en.md",
        },
    )
    assert shield.status_code == 200
    shield_payload = shield.json()
    assert shield_payload["ok"] is True
    assert "[PERSON_00001]" in shield_payload["ai_safe_text"]
    assert "Sarah Morgan" not in shield_payload["ai_safe_text"]
    assert shield_payload["leak_check"]["leaked_items"] == 0
    assert shield_payload["report"]["chain_verified"] is True
    assert "file_path" not in shield_payload["report"]

    trust = client.get("/api/trust-center")
    assert trust.status_code == 200
    trust_payload = trust.json()
    assert trust_payload["vault"]["encrypted"] is True
    assert trust_payload["vault"]["local_only"] is True
    assert trust_payload["local_only_proof"]["bind_host"] == "127.0.0.1"
    assert trust_payload["local_only_proof"]["external_ai_calls"] == 0
    assert trust_payload["reports"]
    assert "file_path" not in trust_payload["reports"][0]

    restored = client.post(
        "/api/restore",
        json={"text": shield_payload["simulated_ai_response"]},
    )
    assert restored.status_code == 200
    restored_payload = restored.json()
    assert restored_payload["ok"] is True
    assert restored_payload["verification_passed"] is True
    assert "Sarah Morgan" in restored_payload["restored_text"]
    assert "[PERSON_00001]" not in restored_payload["restored_text"]


def test_demo_server_serves_phase4_ui(client):
    index = client.get("/")
    assert index.status_code == 200
    assert "text/html" in index.headers["content-type"]
    assert 'id="cloakroom-app"' in index.text
    assert "Shield for AI" in index.text
    assert "Trust Center" in index.text

    app_js = client.get("/static/app.js")
    assert app_js.status_code == 200
    assert "POST" in app_js.text
    assert "/api/shield" in app_js.text

    styles = client.get("/static/styles.css")
    assert styles.status_code == 200
    assert ".shield-grid" in styles.text


def test_demo_server_mixed_sample_shields_english_and_il_values(client):
    sample = client.post(
        "/api/demo/load-sample",
        json={"name": "customer_escalation_mixed.md"},
    )
    assert sample.status_code == 200
    sample_payload = sample.json()
    assert sample_payload["language"] == "auto"
    assert "Sarah Morgan" in sample_payload["original_text"]
    assert "312345674" in sample_payload["original_text"]

    shield = client.post(
        "/api/shield",
        json={
            "text": sample_payload["original_text"],
            "sample_name": "customer_escalation_mixed.md",
        },
    )
    assert shield.status_code == 200
    payload = shield.json()
    assert payload["ok"] is True
    assert payload["leak_check"]["leaked_items"] == 0
    assert "Sarah Morgan" not in payload["ai_safe_text"]
    assert "312345674" not in payload["ai_safe_text"]
    assert "[TEUDAT_ZEHUT_00001]" in payload["ai_safe_text"]
    assert payload["review_items"]
    assert "Sarah Morgan" not in str(payload["review_items"])


def test_demo_server_restore_blocks_mutated_token(client):
    sample = client.post(
        "/api/demo/load-sample",
        json={"name": "customer_escalation_en.md"},
    ).json()
    shield = client.post(
        "/api/shield",
        json={
            "text": sample["original_text"],
            "sample_name": "customer_escalation_en.md",
        },
    ).json()

    restored = client.post(
        "/api/restore",
        json={"text": shield["mutated_ai_response"]},
    )
    assert restored.status_code == 200
    payload = restored.json()
    assert payload["ok"] is False
    assert payload["restore_blocked"] is True
    assert payload["restored_text"] == ""
    assert payload["error"]["code"] == "HallucinationDetectedError"


def test_demo_server_reset_returns_clean_workspace(client):
    sample = client.post(
        "/api/demo/load-sample",
        json={"name": "customer_escalation_en.md"},
    ).json()
    client.post(
        "/api/shield",
        json={
            "text": sample["original_text"],
            "sample_name": "customer_escalation_en.md",
        },
    )
    assert client.get("/api/trust-center").json()["vault"]["mappings_count"] > 0

    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200
    trust = reset.json()["trust_center"]
    assert trust["vault"]["mappings_count"] == 0
    assert trust["activity"]["anonymize_count"] == 0
    assert trust["reports"] == []


def test_demo_server_rejects_unknown_sample(client):
    response = client.post(
        "/api/demo/load-sample",
        json={"name": "../secret.md"},
    )
    assert response.status_code == 404


def test_demo_server_validates_loopback_bind_host():
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("localhost") == "localhost"
    with pytest.raises(ValueError):
        validate_bind_host("0.0.0.0")


def test_demo_url_formats_loopback_hosts():
    assert demo_url("127.0.0.1", 8765) == "http://127.0.0.1:8765/"
    assert demo_url("::1", 8765) == "http://[::1]:8765/"
    with pytest.raises(ValueError):
        demo_url("0.0.0.0", 8765)
