"""Tests for hallucination/mutation token detection."""

from cloakroom.hallucination.detector import detect_token_anomalies


class TestDetectTokenAnomalies:
    def test_flags_hallucinated_token(self):
        flags = detect_token_anomalies(
            text="Please review [PERSON_99999].",
            known_tokens={"[PERSON_00001]"},
        )
        assert len(flags) == 1
        assert flags[0].flag_type == "hallucinated"
        assert flags[0].token_text == "[PERSON_99999]"

    def test_flags_mutated_token(self):
        flags = detect_token_anomalies(
            text="Please review [PERSN_00001].",
            known_tokens={"[PERSON_00001]"},
        )
        assert len(flags) == 1
        assert flags[0].flag_type == "mutated"
        assert flags[0].nearest_match == "[PERSON_00001]"

    def test_flags_dropped_token(self):
        flags = detect_token_anomalies(
            text="[PERSON_00001] only",
            known_tokens={"[PERSON_00001]", "[ORG_00001]"},
            expected_tokens={"[PERSON_00001]", "[ORG_00001]"},
        )
        dropped = [flag for flag in flags if flag.flag_type == "dropped"]
        assert len(dropped) == 1
        assert dropped[0].token_text == "[ORG_00001]"

    def test_no_flags_for_known_legacy_forms(self):
        flags = detect_token_anomalies(
            text="PERSON_00001 and [ORG_00001]",
            known_tokens={"[PERSON_00001]", "[ORG_00001]"},
        )
        assert flags == []

