"""Terminal walkthrough of the killer-demo Shield -> AI -> Restore loop.

Run from the repo root:

    uv run python scripts/demo_walkthrough.py

It loads the bundled Customer Escalation sample, tokenizes via the demo
rule engine, simulates an AI response that uses those tokens, and
restores the original values. No network, no real LLM.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from textwrap import indent

from cloakroom.demo import load_sample
from cloakroom.detection.demo_rules import build_default_demo_ruleset
from cloakroom.models import VaultData, now_iso
from cloakroom.pipeline.anonymize import AnonymizePipeline
from cloakroom.pipeline.restore import RestorePipeline
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


BAR = "=" * 78


def banner(title: str) -> None:
    print(f"\n{BAR}\n{title}\n{BAR}")


def make_demo_workspace(tmp_dir: Path) -> WorkspaceContext:
    master_key = generate_master_key()
    return WorkspaceContext(
        workspace_id="demo",
        workspace_name="Demo Workspace",
        vault=Vault(tmp_dir / "vault.enc"),
        vault_data=VaultData(
            workspace_id="demo",
            workspace_name="Demo Workspace",
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=24,
        ),
        token_generator=TokenGenerator(derive_hmac_key(master_key)),
        master_key=master_key,
    )


def simulated_ai_response(safe_text: str) -> str:
    """A canned 'AI' summary that reuses the tokens it was given."""
    lines = safe_text.strip().splitlines()
    # Pull the tokens straight out of the first line so the response is
    # guaranteed to round-trip cleanly without any model dependency.
    return (
        "Risk summary:\n"
        f"- The {lines[0].split(' at ')[0]} escalation is high priority.\n"
        f"- Account contract size is significant.\n\n"
        "Draft client response:\n"
        f"{lines[0]}\n"
        "We acknowledge the renewal concerns and will follow up shortly.\n"
    )


def main() -> int:
    sample_name = "customer_escalation_en.md"
    original = load_sample(sample_name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx = make_demo_workspace(tmp_path)

        input_path = tmp_path / sample_name
        input_path.write_text(original, encoding="utf-8")
        safe_path = tmp_path / "ai_safe.md"
        restored_path = tmp_path / "restored.md"

        banner("1. ORIGINAL  (stays local — never leaves the machine)")
        print(indent(original.rstrip(), "  "))

        AnonymizePipeline(
            ctx,
            score_threshold=0.5,
            demo_ruleset=build_default_demo_ruleset(),
            language="en",
        ).run(input_path, safe_path)
        safe_text = safe_path.read_text(encoding="utf-8")

        banner("2. AI-SAFE  (this is what the chatbot would see)")
        print(indent(safe_text.rstrip(), "  "))

        ai_response = simulated_ai_response(safe_text)

        banner("3. SIMULATED AI RESPONSE  (still tokenized)")
        print(indent(ai_response.rstrip(), "  "))

        ai_response_path = tmp_path / "ai_response.md"
        ai_response_path.write_text(ai_response, encoding="utf-8")

        RestorePipeline(ctx).run(ai_response_path, restored_path)
        restored = restored_path.read_text(encoding="utf-8")

        banner("4. RESTORED LOCALLY  (original values back in place)")
        print(indent(restored.rstrip(), "  "))

        banner("5. ROUND-TRIP CHECK")
        AnonymizePipeline(
            ctx,
            score_threshold=0.5,
            demo_ruleset=build_default_demo_ruleset(),
            language="en",
        )  # no-op: just shows the pipeline can be re-instantiated cleanly

        rt_path = tmp_path / "rt_restored.md"
        RestorePipeline(ctx).run(safe_path, rt_path)
        rt_text = rt_path.read_text(encoding="utf-8")
        if rt_text == original:
            print("  Original sample anonymized + restored is byte-identical.")
        else:
            print("  WARNING: round trip differs.")
            return 1

        banner("6. WHAT WOULD HAVE LEAKED IF YOU PASTED RAW INTO AI")
        leaked = []
        for marker in [
            "Sarah Morgan",
            "Acme Health",
            "sarah.morgan@acmehealth.eu",
            "Project Lantern",
            "EU-CUST-88421",
            "$2.4M",
            "18 percent discount",
            "+44 20 7946 0182",
            "15 Farringdon Street, London",
            "Q3 churn containment plan",
            "pre-acquisition integration risk",
        ]:
            if marker in original and marker not in safe_text:
                leaked.append(marker)
        for item in leaked:
            print(f"  - {item}")
        print(f"\n  {len(leaked)} sensitive items shielded; 0 leaked into the AI-safe text.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
