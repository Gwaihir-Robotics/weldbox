"""Wizard: drive the questionary prompts with scripted answers and assert
the YAML it writes round-trips into a valid BoxSpec with plates and feet."""

from pathlib import Path

import pytest

from weldbox import wizard
from weldbox.spec import load_spec


class FakePrompt:
    """Stands in for a questionary prompt object: .unsafe_ask() pops the
    next scripted answer, matched by the prompt kind for a clearer failure
    when the script and the wizard drift apart."""

    def __init__(self, script, kind):
        self.script = script
        self.kind = kind

    def unsafe_ask(self):
        assert self.script, f"ran out of scripted answers at a {self.kind} prompt"
        want_kind, value = self.script.pop(0)
        assert want_kind == self.kind, (
            f"wizard asked a {self.kind} prompt; script expected {want_kind} "
            f"(value {value!r})"
        )
        return value


@pytest.fixture
def drive(monkeypatch):
    def _drive(script):
        script = list(script)
        for kind in ("text", "select", "confirm", "checkbox"):
            monkeypatch.setattr(
                wizard.questionary,
                kind,
                lambda *a, _k=kind, **kw: FakePrompt(script, _k),
            )
        return script

    return _drive


def test_wizard_writes_plates_and_feet(drive, tmp_path):
    out = tmp_path / "box.yaml"
    script = [
        ("text", "Cart"),                    # project name
        ("select", "rmfg"),                  # vendor
        ("select", _first_square_profile()), # tube profile
        ("text", "800mm"),                   # height
        ("text", "1600mm"),                  # width
        ("text", "700mm"),                   # depth
        ("select", "full_height_posts"),     # topology
        ("confirm", False),                  # add blocking? no
        ("confirm", False),                  # add siding? no
        # --- deck plates ---
        ("confirm", True),                   # add a deck plate? yes
        ("select", "base"),                  # on which layer
        ("text", "0.075in"),                 # thickness
        ("text", "304"),                     # alloy
        ("text", "1mm"),                     # post clearance
        ("confirm", False),                  # add another plate? no
        # --- feet ---
        ("confirm", True),                   # add feet? yes
        ("text", "0.25in"),                  # thickness
        ("text", "A36"),                     # alloy
        ("text", "4in"),                     # size
        ("select", "square"),                # pattern kind
        ("text", "3in"),                     # bolt spacing
        ("text", "0.41in"),                  # bolt hole
        ("confirm", True),                   # centered stem hole? yes
        ("text", "0.5in"),                   # center hole dia
        ("confirm", True),                   # one per corner? yes
        ("confirm", True),                   # mid-span pairs? yes
        ("text", "1"),                       # how many
        ("select", "width"),                 # axis
        # ---
        ("text", "5"),                       # quantity
    ]
    drive(script)

    wizard.run_wizard(out)

    spec = load_spec(out)
    assert len(spec.plates) == 1
    assert spec.plates[0].layer == "base"
    assert spec.plates[0].material.alloy == "304"
    assert spec.plates[0].post_clearance == pytest.approx(1.0)

    assert spec.feet is not None
    assert spec.feet.corners is True
    assert spec.feet.mid.count == 1 and spec.feet.mid.axis == "width"
    assert spec.feet.pattern.type == "square"
    assert spec.feet.pattern.spacing == pytest.approx(76.2)
    assert spec.feet.pattern.center_hole == pytest.approx(12.7)
    assert spec.quantity == 5


def test_wizard_single_pattern_no_center_hole(drive, tmp_path):
    out = tmp_path / "box.yaml"
    script = [
        ("text", "Leveled"),
        ("select", "rmfg"),
        ("select", _first_square_profile()),
        ("text", "800mm"), ("text", "900mm"), ("text", "700mm"),
        ("select", "full_height_posts"),
        ("confirm", False),                  # blocking
        ("confirm", False),                  # siding
        ("confirm", False),                  # deck plate? no
        ("confirm", True),                   # feet? yes
        ("text", "0.25in"), ("text", "A36"), ("text", "4in"),
        ("select", "single"),                # single stem pattern
        ("text", "0.5in"),                   # stem hole
        ("confirm", True),                   # one per corner
        ("confirm", False),                  # no mid pairs
        ("text", "1"),                       # quantity
    ]
    drive(script)

    wizard.run_wizard(out)

    spec = load_spec(out)
    assert spec.plates == []
    assert spec.feet.pattern.type == "single"
    assert spec.feet.pattern.hole == pytest.approx(12.7)
    assert spec.feet.mid is None


def _first_square_profile():
    from weldbox.vendors import get_vendor

    return next(p for p in get_vendor("rmfg").catalog().profiles if p.shape == "square")
