"""End-to-end tests for the killer-demo Customer Escalation sample."""

from __future__ import annotations

from pathlib import Path

import pytest

from cloakroom.demo import load_sample
from cloakroom.detection.demo_rules import build_default_demo_ruleset
from cloakroom.models import VaultData, now_iso
from cloakroom.pipeline.anonymize import AnonymizePipeline
from cloakroom.pipeline.restore import RestorePipeline
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


@pytest.fixture
def workspace_ctx(tmp_path):
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault = Vault(tmp_path / "vault.enc")
    vault_data = VaultData(
        workspace_id="demo-id",
        workspace_name="demo-ws",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=24,
    )
    return WorkspaceContext(
        workspace_id="demo-id",
        workspace_name="demo-ws",
        vault=vault,
        vault_data=vault_data,
        token_generator=TokenGenerator(hmac_key),
        master_key=master_key,
    )


def _write_sample(tmp_path: Path, name: str) -> Path:
    sample_text = load_sample(name)
    target = tmp_path / name
    target.write_text(sample_text, encoding="utf-8")
    return target


def test_english_sample_tokens_match_killer_demo_prd(workspace_ctx, tmp_path):
    """The English Customer Escalation sample produces every expected token."""
    input_path = _write_sample(tmp_path, "customer_escalation_en.md")
    output_path = tmp_path / "ai_safe.md"

    pipeline = AnonymizePipeline(
        workspace_ctx,
        score_threshold=0.5,
        demo_ruleset=build_default_demo_ruleset(),
        language="en",
    )
    result = pipeline.run(input_path, output_path)

    safe_text = output_path.read_text(encoding="utf-8")

    expected_tokens = [
        "[PERSON_00001]",
        "[ORG_00001]",
        "[EMAIL_00001]",
        "[PROJECT_00001]",
        "[CUSTOMER_ID_00001]",
        "[CONTRACT_VALUE_00001]",
        "[PRICING_TERM_00001]",
        "[ADDRESS_00001]",
        "[STRATEGY_00001]",
        "[STRATEGY_00002]",
    ]
    for token in expected_tokens:
        assert token in safe_text, f"Expected {token} in AI-safe output, got:\n{safe_text}"

    forbidden_originals = [
        "Sarah Morgan",
        "Acme Health",
        "sarah.morgan@acmehealth.eu",
        "Project Lantern",
        "EU-CUST-88421",
        "$2.4M",
        "18 percent discount",
        "15 Farringdon Street, London",
        "Q3 churn containment plan",
        "pre-acquisition integration risk",
    ]
    for original in forbidden_originals:
        assert original not in safe_text, f"Original {original!r} leaked into AI-safe output"

    assert result.entities_found >= len(expected_tokens)


def test_english_sample_matches_prd_token_layout(workspace_ctx, tmp_path):
    """The AI-safe output matches the Killer Demo PRD section 6 layout."""
    input_path = _write_sample(tmp_path, "customer_escalation_en.md")
    output_path = tmp_path / "ai_safe.md"

    AnonymizePipeline(
        workspace_ctx,
        score_threshold=0.5,
        demo_ruleset=build_default_demo_ruleset(),
        language="en",
    ).run(input_path, output_path)

    expected = (
        "[PERSON_00001] at [ORG_00001] emailed [EMAIL_00001] about the "
        "[PROJECT_00001] renewal.\n"
        "The account is [CUSTOMER_ID_00001] and includes a "
        "[CONTRACT_VALUE_00001] contract with an [PRICING_TERM_00001] "
        "exception.\n"
        "Her phone number is [PHONE_00001] and the account address is "
        "[ADDRESS_00001].\n"
        "The team wants AI help summarizing the [STRATEGY_00001] and "
        "[STRATEGY_00002] before the [DATE_00001] renewal meeting.\n"
    )
    assert output_path.read_text(encoding="utf-8") == expected


def test_english_sample_round_trip_byte_identical(workspace_ctx, tmp_path):
    """Anonymize then restore returns exactly the original text."""
    original_text = load_sample("customer_escalation_en.md")
    input_path = tmp_path / "customer_escalation_en.md"
    input_path.write_text(original_text, encoding="utf-8")
    safe_path = tmp_path / "ai_safe.md"
    restored_path = tmp_path / "restored.md"

    AnonymizePipeline(
        workspace_ctx,
        score_threshold=0.5,
        demo_ruleset=build_default_demo_ruleset(),
        language="en",
    ).run(input_path, safe_path)

    RestorePipeline(workspace_ctx).run(safe_path, restored_path)

    assert restored_path.read_text(encoding="utf-8") == original_text


def test_hebrew_sample_produces_first_class_il_tokens(workspace_ctx, tmp_path):
    """The Hebrew sample produces HE_PERSON, TEUDAT_ZEHUT, IL_PHONE, IL_BANK_ACCOUNT tokens."""
    input_path = _write_sample(tmp_path, "customer_escalation_he.md")
    output_path = tmp_path / "ai_safe_he.md"

    pipeline = AnonymizePipeline(
        workspace_ctx,
        score_threshold=0.5,
        demo_ruleset=build_default_demo_ruleset(),
        language="he",
    )
    pipeline.run(input_path, output_path)

    safe_text = output_path.read_text(encoding="utf-8")

    # Israeli first-class types must appear; TEUDAT_ZEHUT must NOT be folded to SSN.
    assert "[TEUDAT_ZEHUT_00001]" in safe_text
    assert "[IL_PHONE_00001]" in safe_text
    assert "[IL_BANK_ACCOUNT_00001]" in safe_text
    assert "[SSN_" not in safe_text

    # Hebrew identifiers must not leak.
    assert "312345674" not in safe_text
    assert "050-123-4567" not in safe_text
    assert "12-345-6789012" not in safe_text


def test_hebrew_sample_round_trip_byte_identical(workspace_ctx, tmp_path):
    original_text = load_sample("customer_escalation_he.md")
    input_path = tmp_path / "customer_escalation_he.md"
    input_path.write_text(original_text, encoding="utf-8")
    safe_path = tmp_path / "ai_safe_he.md"
    restored_path = tmp_path / "restored_he.md"

    AnonymizePipeline(
        workspace_ctx,
        score_threshold=0.5,
        demo_ruleset=build_default_demo_ruleset(),
        language="he",
    ).run(input_path, safe_path)

    RestorePipeline(workspace_ctx).run(safe_path, restored_path)

    assert restored_path.read_text(encoding="utf-8") == original_text
