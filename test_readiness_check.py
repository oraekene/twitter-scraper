"""Self-check for the readiness evidence scanner.

Run: python test_readiness_check.py
"""
import tempfile
from pathlib import Path

from readiness_check import load_checklist, project_aliases, scan_text


def main():
    checklist = load_checklist(Path(__file__).with_name("readiness_checklists.json"))
    checks = checklist["checks"]
    pricing = next(check for check in checks if check["id"] == "build.payment_or_waitlist")

    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "pricing.md"
        empty.write_text("No implementation details here.", encoding="utf-8")
        assert not scan_text(empty.read_text(encoding="utf-8"), checks, str(empty))[pricing["id"]]

        empty.write_text("The pricing plan uses a Stripe checkout session.", encoding="utf-8")
        evidence = scan_text(empty.read_text(encoding="utf-8"), checks, str(empty))[pricing["id"]]
        assert evidence
        assert evidence[0]["path"] == str(empty)

    aliases = project_aliases("oraekene__Solar_Sizer_SDK2")
    assert "solar sizer sdk2" in aliases
    assert "solarsizersdk2" in aliases

    variants = {
        "build.scoped_mvp": "Build a one week app.",
        "build.onboarding": "Reduce time to first value.",
        "build.payment_or_waitlist": "Use priceid for checkout.",
        "build.quality_and_safety": "Run an end to end test.",
        "funding.legal_cap_table": "The founders' agreement is signed.",
        "opportunities.application_assets": "Prepare a one page pitch.",
        "marketing.launch_plan": "Write a pre launch plan.",
    }
    for check_id, text in variants.items():
        assert scan_text(text, checks, "variant")[check_id], check_id

    print("readiness_check self-check: green")


if __name__ == "__main__":
    main()
