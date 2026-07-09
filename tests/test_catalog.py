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


def test_counts_match_spec(catalog):
    c = catalog.counts()
    assert c["populated_categories"] == 18
    assert c["models"] == 627
    assert c["uidefs_entries"] == 641
    assert c["params"] == 5344
    assert c["stereo_aliases"] == 145


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
