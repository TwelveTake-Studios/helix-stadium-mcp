"""Catalog tests against a REAL installed Helix Stadium.

Install-gated: run with `pytest --run-install`. It reads the user's own install
and asserts the model/param counts + the stereo-alias trap.
"""
import pytest

pytestmark = pytest.mark.install


@pytest.fixture(scope="module")
def catalog():
    from helix_stadium_mcp.catalog import Catalog
    try:
        return Catalog()
    except FileNotFoundError as e:
        pytest.skip(f"no Helix Stadium install found: {e}")


COUNTS = {
    (1, 3, 0, 0): {"populated_categories": 18, "models": 627, "uidefs_entries": 641,
                   "params": 5344, "stereo_aliases": 145},
    (1, 4, 0, 0): {"populated_categories": 18, "models": 636, "uidefs_entries": 648,
                   "params": 5406, "stereo_aliases": 151},
}


def _install_version(catalog):
    from helix_stadium_mcp import modeldefs as M
    binf = M._latest_bin(catalog.res)
    return M._ver_key(str(binf)) if binf else None


def test_counts_match_spec(catalog):
    expected = COUNTS.get(_install_version(catalog))
    if expected is None:
        pytest.skip(f"no pinned counts for install version {_install_version(catalog)}")
    c = catalog.counts()
    assert {k: c[k] for k in expected} == expected


def _described(catalog, model_id):
    from helix_stadium_mcp.tools.models import _enrich_ranges
    desc = catalog.describe(model_id)
    _enrich_ranges(catalog, model_id, desc)
    return {p["id"]: p for p in desc["params"]}


def test_agoura_sag_ripple_signed_range(catalog):
    from helix_stadium_mcp.encoding import display_string, stored_value
    assert catalog.stored_range("Agoura_AmpCali2CPlus", "Sag") == (-1, 1)
    params = _described(catalog, "Agoura_AmpCali2CPlus")
    for pid in ("Sag", "Ripple"):
        assert params[pid]["default"] == "Stock"
        assert params[pid]["range"] == ["-10.0", "+10.0"]
    assert display_string(catalog, "Agoura_AmpCali2CPlus", "Sag", -1.0)[0] == "-10.0"
    assert stored_value(catalog, "Agoura_AmpCali2CPlus", "Sag", 0) == 0.0


def test_prosecutor_sag_unit_range_still_centers_on_stock(catalog):
    if "Agoura_AmpLine6Prosecutor" not in catalog.uidefs:
        pytest.skip("install predates the Line 6 Prosecutor (1.4)")
    assert catalog.stored_range("Agoura_AmpLine6Prosecutor", "Sag") == (0, 1)
    params = _described(catalog, "Agoura_AmpLine6Prosecutor")
    for pid in ("Sag", "Ripple"):
        assert params[pid]["default"] == "Stock"
        assert params[pid]["range"] == ["-10.0", "+10.0"]


def test_stereo_alias_resolution(catalog):
    # These preset ids are NOT primary keys — resolve via base .stereo_model.
    for mid in ("HD2_VolPanGainStereo", "HX2_EQParametricStereo"):
        assert mid not in catalog.uidefs
        assert catalog.resolve(mid) is not None


def test_encoding_on_real_amp(catalog):
    from helix_stadium_mcp.encoding import display_string
    text, tag = display_string(catalog, "Agoura_AmpEVPanamaRed", "Drive", 0.6)
    assert tag == "generic_knob"
    assert text == "6.0"


def test_find_model_id(catalog):
    assert catalog.find_model_id("Agoura_AmpEVPanamaRed") == "Agoura_AmpEVPanamaRed"
    assert catalog.find_model_id("EV Panama Red") == "Agoura_AmpEVPanamaRed"   # friendly name
    assert catalog.find_model_id("no such model") is None
