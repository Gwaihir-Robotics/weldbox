"""Removable inset siding from clear rectangular openings in vertical faces.

Projects only members touching the exterior face, merges free grid cells into
rectangles, then mounts each cover on separate, edge-welded receiver tabs.
No tube holes are inferred from panel holes: these two fastener holes differ.
"""
from __future__ import annotations

import math
from ..frame import AXIS_INDEX, LOCAL_BASIS
from .layout import Panel, _face_frames


def _member_bounds(member):
    lo, hi = list(member.origin), list(member.end)
    for axis, size in zip(LOCAL_BASIS[member.axis], [member.profile.outer_w_mm, member.profile.outer_h_mm]):
        k = AXIS_INDEX[axis]
        lo[k] -= size / 2
        hi[k] += size / 2
    return lo, hi


def opening_rectangles(frame, face_frame):
    """Clear rectangles (u0,v0,u1,v1), bounded by actual skin members."""
    f = face_frame
    ni = next(i for i, n in enumerate(f['n']) if n)
    ui = next(i for i, n in enumerate(f['u']) if n)
    vi = next(i for i, n in enumerate(f['v']) if n)
    rects = []
    for member in frame.members:
        lo, hi = _member_bounds(member)
        if abs((hi[ni] if f['n'][ni] > 0 else lo[ni]) - f['origin'][ni]) > 1e-5:
            continue
        rect = (max(0,lo[ui]),max(0,lo[vi]),min(f['w'],hi[ui]),min(f['h'],hi[vi]))
        rect = tuple(round(value,7) for value in rect)
        if rect[2] > rect[0] and rect[3] > rect[1]:
            rects.append(rect)
    us = sorted({0., f['w']} | {r[i] for r in rects for i in (0,2)})
    vs = sorted({0., f['h']} | {r[i] for r in rects for i in (1,3)})
    result, active = [], {}
    for va, vb in zip(vs,vs[1:]):
        spans, start = [], None
        for ua, ub in zip(us,us[1:]):
            free = not any(r[0] < (ua+ub)/2 < r[2] and r[1] < (va+vb)/2 < r[3] for r in rects)
            if free and start is None: start = ua
            if not free and start is not None:
                spans.append((start,ua)); start = None
        if start is not None: spans.append((start,us[-1]))
        next_active = {}
        for span in spans:
            old = active.pop(span,None)
            next_active[span] = (span[0], old[1] if old else va, span[1], vb)
        result.extend(active.values()); active = next_active
    result.extend(active.values())
    for u0,v0,u1,v1 in result:
        # Every receiver tab needs a continuous vertical member to weld to.
        for u in (u0-1e-4,u1+1e-4):
            intervals = sorted((max(v0,r[1]),min(v1,r[3])) for r in rects if r[0] <= u <= r[2] and r[3]>v0 and r[1]<v1)
            end = v0
            for a,b in intervals:
                if a > end+1e-5: break
                end = max(end,b)
            if end < v1-1e-5:
                raise ValueError('Inset opening requires continuous vertical receiving members; unsupported irregular opening')
    return sorted(result)


def inset_layouts(frame, spec):
    siding = spec.siding; cfg = siding.inset; result = []
    frames = _face_frames(spec)
    for pspec in siding.panels:
        depth = cfg.recess + pspec.material.thickness
        radius = frame.profile.corner_r_resolved_mm
        if depth < radius or depth + cfg.tab_material.thickness > min(frame.profile.outer_w_mm, frame.profile.outer_h_mm) - radius:
            raise ValueError('Inset receiver tabs must land on the flat tube wall beyond its corner radius')
        for face in pspec.faces:
            f = frames[face]
            def point(u,v,depth):
                return tuple(f['origin'][i]+u*f['u'][i]+v*f['v'][i]-depth*f['n'][i] for i in range(3))
            for index,(u0,v0,u1,v1) in enumerate(opening_rectangles(frame,f),1):
                levels = [v0]+sorted(z for z in cfg.split_heights if v0<z<v1)+[v1]
                for segment,(za,zb) in enumerate(zip(levels,levels[1:]),1):
                    gap = cfg.clearance; w=u1-u0-2*gap; h=zb-za-2*gap
                    if w <= 2*cfg.tab_projection or h <= 2*cfg.end_offset or siding.corner_radius >= min(w,h)/2:
                        raise ValueError('Inset opening/split too small for configured tabs and corner radius')
                    name=f'inset-{face}-{index}-{segment}'
                    panel=Panel(name,f'inset:{face}',w,h,pspec.material.thickness,pspec.material.alloy,1,
                        corner_radius=siding.corner_radius,origin3d=point(u0+gap,za+gap,cfg.recess+pspec.material.thickness),u_dir=f['u'],v_dir=f['v'],normal=f['n'])
                    count=max(2,math.ceil((h-2*cfg.end_offset)/cfg.fastener_spacing)+1)
                    for side in (0,1):
                        tu=u0 if side==0 else u1-cfg.tab_projection
                        for j in range(count):
                            pv=cfg.end_offset+j*(h-2*cfg.end_offset)/(count-1)
                            hu=tu+cfg.tab_projection/2; hv=za+gap+pv
                            panel.holes.append((hu-u0-gap,pv,cfg.fastener.panel_hole))
                            tab=Panel(f'receiver-tab-{sum(p.face.startswith("tab:") for p in result)+1}',f'tab:{face}',cfg.tab_projection,cfg.tab_width,cfg.tab_material.thickness,cfg.tab_material.alloy,1,
                                holes=[(cfg.tab_projection/2,cfg.tab_width/2,cfg.fastener.receiver_hole)],
                                origin3d=point(tu,hv-cfg.tab_width/2,cfg.recess+panel.thickness+cfg.tab_material.thickness),u_dir=f['u'],v_dir=f['v'],normal=f['n'])
                            result.append(tab)
                    result.append(panel)
    return result
