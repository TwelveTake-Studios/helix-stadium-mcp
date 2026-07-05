"""Snapshot-diff + validation tests on synthetic fixtures."""
from helix_stadium_mcp.preset import resolve_snapshot_index, snapshot_diff
from helix_stadium_mcp.validation import validate


class FakeCatalog:
    controls: dict = {}

    def friendly_name(self, model_id):
        return {"AmpX": "Amp X"}.get(model_id, model_id)

    def param_def(self, model_id, param_id):
        return None  # -> display_string falls back to a plain number

    def resolve(self, model_id):
        return {"name": "Amp X"} if model_id == "AmpX" else None


def _preset():
    snaps = [{"name": "Rhythm", "valid": True}, {"name": "Lead", "valid": True}]
    snaps += [{"name": f"S{i}", "valid": False} for i in range(3, 9)]
    return {
        "meta": {"name": "T"},
        "preset": {
            "snapshots": snaps,
            "flow": [{
                "b00": {
                    "type": "amp", "position": 0, "@enabled": {"value": True},
                    "slot": [{"model": "AmpX", "params": {
                        "Drive": {"value": 0.5, "snapshots": [0.5, 0.8, None, None, None, None, None, None]},
                        "Bass": {"value": 0.4, "snapshots": [0.4, 0.4, None, None, None, None, None, None]},
                    }}],
                },
            }],
        },
    }


def test_resolve_snapshot_index():
    obj = _preset()
    assert resolve_snapshot_index(obj, "Rhythm") == 0
    assert resolve_snapshot_index(obj, "lead") == 1     # case-insensitive
    assert resolve_snapshot_index(obj, "2") == 1        # 1-based number
    assert resolve_snapshot_index(obj, "nope") is None


def test_snapshot_diff_reports_only_changes():
    d = snapshot_diff(FakeCatalog(), _preset(), 0, 1)
    changed = {c["param"] for c in d["changes"]}
    assert "Drive" in changed        # 0.5 -> 0.8
    assert "Bass" not in changed     # 0.4 -> 0.4 (unchanged)
    assert d["a"]["name"] == "Rhythm" and d["b"]["name"] == "Lead"


def test_validate_ok():
    assert validate(_preset())["errors"] == []


def test_validate_structural_errors():
    assert any("preset" in e for e in validate({"meta": {}})["errors"])
    assert any("flow" in e for e in validate({"meta": {}, "preset": {"flow": "x"}})["errors"])


def test_validate_unknown_model_warns():
    obj = _preset()
    obj["preset"]["flow"][0]["b00"]["slot"][0]["model"] = "GhostModel"
    res = validate(obj, FakeCatalog())
    assert any("GhostModel" in w for w in res["warnings"])


def test_validate_source_reference():
    obj = _preset()
    obj["preset"]["sources"] = {"16843015": {"bypass": True}}
    en = obj["preset"]["flow"][0]["b00"]["@enabled"]
    en["controller"] = {"source": 99999}
    assert any("99999" in w for w in validate(obj)["warnings"])
    en["controller"]["source"] = 16843015          # now it resolves
    assert not any("not in preset.sources" in w for w in validate(obj)["warnings"])


_SYNC_NOTES = ["1/1", "1/2 Dotted", "1/2", "1/2 Triplet", "1/4 Dotted", "1/4",
               "1/4 Triplet", "1/8 Dotted", "1/8"]


class SyncCatalog:
    controls = {"sync_note": {"format": _SYNC_NOTES}}

    def param_def(self, model_id, param_id):
        if param_id == "Time":
            return {"id": "Time", "display_tag": "time_ms",
                    "sync": "TempoSync1", "note": "SyncSelect1"}
        return None

    def friendly_name(self, m):
        return m


def test_render_param_tempo_sync():
    from helix_stadium_mcp.preset import render_param
    params = {"TempoSync1": {"value": True}, "SyncSelect1": {"value": 7},
              "Time": {"value": 0.082}}
    cat = SyncCatalog()
    # synced Time -> note division; the SyncSelect param -> note name
    assert render_param(cat, "Delay", "Time", params["Time"], params) == "1/8 Dotted"
    assert render_param(cat, "Delay", "SyncSelect1", params["SyncSelect1"], params) == "1/8 Dotted"
