"""Group physically identical members into unique parts.

Two members are the same stock part when one can be mapped onto the other
by a symmetry of the square tube: rotation about the member axis in 90
degree steps (4) x end-for-end flip (2) = 8 transforms. The signature is
the minimum over all 8 transforms of the transformed feature set — so a
part and its end-swapped or rotated twin collapse together.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .features import feature_key, transform_feature
from .frame import FrameGraph, Member

_ROUND = 2  # mm decimals in signatures

ALL_TRANSFORMS: list[tuple[int, bool]] = [
    (q, flipped) for flipped in (False, True) for q in (0, 1, 2, 3)
]


def transformed_keys(member: Member, quarter_turns: int, flipped: bool) -> tuple:
    return tuple(
        sorted(
            feature_key(transform_feature(f, member.length, quarter_turns, flipped))
            for f in member.features
        )
    )


def part_signature(member: Member) -> tuple:
    variants = [transformed_keys(member, q, flipped) for q, flipped in ALL_TRANSFORMS]
    return (member.profile.id, round(member.length, _ROUND), min(variants))


@dataclass
class UniquePart:
    signature: tuple
    exemplar: Member
    member_ids: list[str] = field(default_factory=list)
    name: str = ""

    @property
    def qty(self) -> int:
        return len(self.member_ids)


def group_parts(frame: FrameGraph) -> list[UniquePart]:
    groups: dict[tuple, UniquePart] = {}
    for m in frame.members:
        sig = part_signature(m)
        part = groups.get(sig)
        if part is None:
            part = groups[sig] = UniquePart(signature=sig, exemplar=m)
        part.member_ids.append(m.id)

    parts = sorted(groups.values(), key=lambda p: (-p.exemplar.length, p.exemplar.id))
    # name each part by its member role (or "member-<length>" when a part is
    # used across several roles); number repeats (rail vs rail-2)
    base_names: list[str] = []
    for part in parts:
        roles = {frame.member(mid).role for mid in part.member_ids}
        if len(roles) == 1:
            base_names.append(next(iter(roles)))
        else:
            base_names.append(f"member-{part.exemplar.length:.0f}mm")
    seen: dict[str, int] = {}
    for part, base in zip(parts, base_names):
        seen[base] = seen.get(base, 0) + 1
        part.name = base if base_names.count(base) == 1 else f"{base}-{seen[base]}"
    return parts
