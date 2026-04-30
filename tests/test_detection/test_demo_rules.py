"""Unit tests for the demo-rule deterministic detector."""

from __future__ import annotations

from cloakroom.detection.demo_rules import DemoRuleSet, build_default_demo_ruleset
from cloakroom.models import EntityType


def test_dictionary_match_case_insensitive():
    rs = DemoRuleSet()
    rs.add_dictionary(EntityType.ORGANIZATION, ["Acme Health"])
    entities = rs.detect("Sarah at acme health called.")
    assert len(entities) == 1
    assert entities[0].entity_type is EntityType.ORGANIZATION
    assert entities[0].text == "acme health"


def test_dictionary_does_not_match_substring():
    rs = DemoRuleSet()
    rs.add_dictionary(EntityType.PROJECT, ["Lantern"])
    entities = rs.detect("Project Lanterns are bright.")
    # "Lantern" inside "Lanterns" must NOT match (whole-token).
    assert entities == []


def test_regex_match():
    rs = DemoRuleSet()
    rs.add_regex(EntityType.CUSTOMER_ID, r"\bEU-CUST-\d{4,}\b")
    entities = rs.detect("Account EU-CUST-88421 is escalated.")
    assert len(entities) == 1
    assert entities[0].entity_type is EntityType.CUSTOMER_ID
    assert entities[0].text == "EU-CUST-88421"


def test_default_ruleset_finds_killer_demo_entities():
    rs = build_default_demo_ruleset()
    text = (
        "Sarah Morgan at Acme Health emailed sarah.morgan@acmehealth.eu about "
        "the Project Lantern renewal. The account is EU-CUST-88421 and "
        "includes a $2.4M contract with an 18 percent discount exception. "
        "The team wants AI help summarizing the Q3 churn containment plan "
        "and pre-acquisition integration risk before the renewal."
    )
    entities = rs.detect(text)
    by_type = {entity.entity_type: entity.text for entity in entities}

    assert by_type[EntityType.ORGANIZATION] == "Acme Health"
    assert by_type[EntityType.PROJECT] == "Project Lantern"
    assert by_type[EntityType.CUSTOMER_ID] == "EU-CUST-88421"
    assert by_type[EntityType.CONTRACT_VALUE] == "$2.4M"
    assert by_type[EntityType.PRICING_TERM] == "18 percent discount"

    strategies = [e.text for e in entities if e.entity_type is EntityType.STRATEGY]
    assert "Q3 churn containment plan" in strategies
    assert "pre-acquisition integration risk" in strategies


def test_overlapping_rules_keep_higher_score():
    rs = DemoRuleSet()
    rs.add_regex(EntityType.STRATEGY, r"churn", score=0.5)
    rs.add_dictionary(EntityType.STRATEGY, ["Q3 churn containment plan"], score=1.0)
    entities = rs.detect("The Q3 churn containment plan is risky.")
    assert len(entities) == 1
    assert entities[0].text == "Q3 churn containment plan"


def test_no_rules_returns_empty():
    rs = DemoRuleSet()
    assert rs.detect("anything") == []


def test_empty_text_returns_empty():
    rs = build_default_demo_ruleset()
    assert rs.detect("") == []
