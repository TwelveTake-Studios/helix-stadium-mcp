"""Value-encoding tests with a synthetic fake catalog."""
from helix_stadium_mcp.encoding import display_string


class FakeCatalog:
    def __init__(self, params, controls):
        self._params = params
        self.controls = controls

    def param_def(self, model_id, param_id):
        return self._params.get(param_id)


def _cat(param_id, tag, ctrl=None):
    controls = {tag: ctrl} if ctrl is not None and isinstance(tag, str) else {}
    return FakeCatalog({param_id: {"id": param_id, "display_tag": tag}}, controls)


def test_domain_a_scale():
    cat = _cat("Drive", "generic_knob", {"dspToDisplayScale": 10, "format": "%.1f"})
    assert display_string(cat, "Amp", "Drive", 0.6)[0] == "6.0"


def test_domain_c_identity_db():
    cat = _cat("Threshold", "volume", {"formatUnits": "%+.1f dB"})
    assert display_string(cat, "Gate", "Threshold", -48.0)[0] == "-48.0 dB"


def test_inline_enum():
    cat = _cat("Mode", ["Bass", "Guitar"])
    assert display_string(cat, "X", "Mode", 1)[0] == "Guitar"


def test_band_khz_with_units_multiplier():
    ctrl = {"format": [
        {"lowerBound": 0.0, "upperBound": 1000.0, "formatUnits": "%.0f Hz"},
        {"lowerBound": 1000.0, "upperBound": 20000.1, "unitsMultiplier": 0.001,
         "formatUnits": "%.1f kHz"},
    ]}
    cat = _cat("HighCut", "eq_high_cut", ctrl)
    assert display_string(cat, "EQ", "HighCut", 500.0)[0] == "500 Hz"
    assert display_string(cat, "EQ", "HighCut", 9000.0)[0] == "9.0 kHz"


def test_domain_b_pan_center_and_literal():
    ctrl = {"minDisplayValue": -100, "maxDisplayValue": 100, "format": [
        {"lowerBound": -99999, "upperBound": -0.5, "formatUnits": "Left %.0f", "unitsMultiplier": -1},
        {"lowerBound": -0.5, "upperBound": 0.5, "formatUnits": "Center"},
        {"lowerBound": 0.5, "upperBound": 999999, "formatUnits": "Right %.0f"},
    ]}
    cat = _cat("Pan", "pan", ctrl)
    assert display_string(cat, "X", "Pan", 0.5)[0] == "Center"      # -100 + 0.5*200 = 0
    assert display_string(cat, "X", "Pan", 0.0)[0] == "Left 100"    # -100 -> *-1


def test_enum_via_control_format_list():
    # some control-types express `format` as a list of enum-label strings
    ctrl = {"format": ["Off", "Oct-", "Fifth", "Oct+", "Oct+5th", "Oct+7th", "2 Oct", "2 Oct+7th"]}
    cat = _cat("FeedbackType", "vic_feedback_type", ctrl)
    assert display_string(cat, "X", "FeedbackType", 7)[0] == "2 Oct+7th"
