import pytest

from weldbox.vendors import get_vendor


@pytest.fixture(scope="module")
def rfmg():
    return get_vendor("rfmg").catalog()


def test_rfmg_catalog_size(rfmg):
    # 34 steel + 6 stainless + 16 aluminum per material_list.md
    assert len(rfmg.profiles) == 56


def test_find_acceptance_profile(rfmg):
    p = rfmg.find("square", 38.1, 38.1, 3.048)
    assert p.id == "rfmg-a500-s15x120"
    assert p.corner_r_resolved_mm == pytest.approx(0.24 * 25.4)


def test_corner_r_fallback_missing(rfmg):
    # 1 x 1 x 1/16 A500 row has no published corner radius -> 2 x wall
    p = rfmg.find("square", 25.4, 25.4, 0.063 * 25.4, material_family="A500")
    assert p.corner_r_mm is None
    assert p.corner_r_resolved_mm == pytest.approx(2 * 0.063 * 25.4)


def test_ambiguous_requires_family(rfmg):
    # 1 x 1 x .065 exists in A500, 304, and 6061
    with pytest.raises(LookupError, match="ambiguous"):
        rfmg.find("square", 25.4, 25.4, 0.065 * 25.4)
    p = rfmg.find("square", 25.4, 25.4, 0.065 * 25.4, material_family="304")
    assert p.id == "rfmg-304-s1x065"


def test_rect_orientation_agnostic(rfmg):
    a = rfmg.find("rect", 4 * 25.4, 2 * 25.4, 0.120 * 25.4)
    b = rfmg.find("rect", 2 * 25.4, 4 * 25.4, 0.120 * 25.4)
    assert a.id == b.id == "rfmg-a500-re4x2x120"


def test_missing_profile_raises(rfmg):
    with pytest.raises(LookupError, match="no square profile"):
        rfmg.find("square", 127.0, 127.0, 3.0)


def test_stub_vendors_empty():
    assert get_vendor("oshcut").catalog().profiles == []
    assert get_vendor("fabtech").catalog().profiles == []


def test_unknown_vendor():
    with pytest.raises(LookupError, match="unknown vendor"):
        get_vendor("nope")
