from dataclasses import dataclass


@dataclass(frozen=True)
class Anchor:
    block_num: int
    commitment: str


class OfflineModel:
    """Executable semantic fixture, not a claim to be the official Miden MockClient."""
    def __init__(self):
        self.notes = {}
        self.submissions = set()

    def summary(self, request: str, anchor: Anchor, fee: int, fee_asset: int) -> tuple:
        if fee <= 0 or fee_asset <= 0:
            raise ValueError("fee readiness")
        return request, anchor, fee, fee_asset

    def deliver(self, fingerprint: str, block_hint: int):
        self.notes.setdefault(fingerprint, {"status": "EXPECTED", "block_hint": block_hint})

    def apply_committed(self, fingerprint: str, tx_id: str):
        key = fingerprint, tx_id
        if key in self.submissions:
            return False
        self.submissions.add(key)
        self.notes[fingerprint]["status"] = "COMMITTED"
        return True


def test_summary_is_bound_to_one_anchor_and_fee_parameters():
    client = OfflineModel()
    anchor = Anchor(42, "abc")
    assert client.summary("pay", anchor, 7, 100) == client.summary("pay", anchor, 7, 100)
    assert client.summary("pay", anchor, 7, 100) != client.summary("pay", Anchor(43, "def"), 7, 100)


def test_private_note_progression_and_duplicate_submission_protection():
    client = OfflineModel()
    client.deliver("note-1", 40)
    assert client.notes["note-1"]["status"] == "EXPECTED"
    assert client.apply_committed("note-1", "tx-1") is True
    assert client.apply_committed("note-1", "tx-1") is False
    assert client.notes["note-1"]["status"] == "COMMITTED"
