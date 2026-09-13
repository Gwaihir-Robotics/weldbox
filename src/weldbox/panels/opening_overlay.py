"""Flat, per-opening removable covers with holes in the actual tube outer wall.

Cover sides overlap the two vertical members. Upper/lower edges retain the
configured opening clearance, including split seams. Optional top-row extensions
and panel-only access holes do not move the vertical-tube fasteners. No tabs.
"""
import math
from ..features import RivetHole, global_dir_to_local_face, _FACE_LATERAL
from ..frame import LOCAL_BASIS, AXIS_INDEX
from .layout import Panel, _face_frames, hole_global_position
from .inset import opening_rectangles, _member_bounds


def opening_overlay_layouts(frame, spec, *, drill=False):
    siding=spec.siding;cfg=siding.opening_overlay;result=[]
    for pspec in siding.panels:
        grip=pspec.material.thickness+frame.profile.wall_mm
        if not cfg.fastener.grip_min <= grip <= cfg.fastener.grip_max:
            raise ValueError('Resolved tube wall is outside configured fastener grip')
        for face in pspec.faces:
            f=_face_frames(spec)[face]
            ni=next(i for i,n in enumerate(f['n']) if n)
            ui=next(i for i,n in enumerate(f['u']) if n)
            def point(u,v):return tuple(f['origin'][i]+u*f['u'][i]+v*f['v'][i] for i in range(3))
            openings=opening_rectangles(frame,f);top_edge=max(o[3] for o in openings)
            face_panels=[]
            for index,(u0,v0,u1,v1) in enumerate(openings,1):
                levels=[v0]+sorted(z for z in cfg.split_heights if v0<z<v1)+[v1]
                for segment,(za,zb) in enumerate(zip(levels,levels[1:]),1):
                    left=u0-cfg.edge_overlap;bottom=za+cfg.clearance
                    w=u1-u0+2*cfg.edge_overlap;attachment_h=zb-za-2*cfg.clearance
                    extension=cfg.top_extension if zb==top_edge else 0
                    h=attachment_h+extension
                    if bottom+h>f['h']-cfg.clearance+1e-6:
                        raise ValueError('Top extension exceeds frame height clearance')
                    if left<0 or u1+cfg.edge_overlap>f['w'] or attachment_h<=2*cfg.end_offset or siding.corner_radius>=min(w,h)/2:
                        raise ValueError('Cover overlap or split exceeds usable frame opening')
                    panel=Panel(f'cover-{face}-{index}-{segment}',f'cover:{face}',w,h,pspec.material.thickness,pspec.material.alloy,1,
                        corner_radius=siding.corner_radius,origin3d=point(left,bottom),u_dir=f['u'],v_dir=f['v'],normal=f['n'])
                    count=max(2,math.ceil((attachment_h-2*cfg.end_offset)/cfg.fastener_spacing)+1)
                    for hu in (u0-cfg.hole_offset,u1+cfg.hole_offset):
                        for j in range(count):
                            pv=cfg.end_offset+j*(attachment_h-2*cfg.end_offset)/(count-1);center=point(hu,bottom+pv)
                            candidates=[]
                            for member in frame.members:
                                if member.axis!='z':continue
                                lo,hi=_member_bounds(member)
                                if abs((hi[ni] if f['n'][ni]>0 else lo[ni])-center[ni])>1e-5:continue
                                radius=member.profile.corner_r_resolved_mm
                                if not lo[ui]+radius+cfg.fastener.receiver_hole/2+2<=center[ui]<=hi[ui]-radius-cfg.fastener.receiver_hole/2-2:continue
                                if not lo[2]+cfg.fastener.receiver_hole/2+2<=center[2]<=hi[2]-cfg.fastener.receiver_hole/2-2:continue
                                if 2*cfg.edge_overlap>=hi[ui]-lo[ui]:
                                    raise ValueError('Adjacent covers need a positive gap on shared vertical tubes')
                                candidates.append(member)
                            if len(candidates)!=1:raise ValueError('Cover hole must land on exactly one flat vertical tube face with edge clearance')
                            member=candidates[0];local_face=global_dir_to_local_face(member.axis,f['n'])
                            lx,ly=LOCAL_BASIS[member.axis];lateral=_FACE_LATERAL[local_face]
                            offset=lateral[0]*(center[AXIS_INDEX[lx]]-member.origin[AXIS_INDEX[lx]])+lateral[1]*(center[AXIS_INDEX[ly]]-member.origin[AXIS_INDEX[ly]])
                            hole=RivetHole(local_face,center[2]-member.origin[2],offset,cfg.fastener.receiver_hole)
                            actual=hole_global_position(member,hole)
                            assert max(abs(a-b) for a,b in zip(actual,center))<1e-5
                            if drill and hole not in member.features:member.features.append(hole)
                            panel.holes.append((hu-left,pv,cfg.fastener.panel_hole))
                    result.append(panel);face_panels.append((panel,left,bottom))
            for hole in (h for h in cfg.access_holes if h.face==face):
                owners=[(p,hole.u-left,hole.v-bottom) for p,left,bottom in face_panels
                        if left<hole.u<left+p.width and bottom<hole.v<bottom+p.height]
                if len(owners)!=1:raise ValueError('Access hole must lie in exactly one cover')
                panel,u,v=owners[0];r=hole.diameter/2
                if min(u,panel.width-u,v,panel.height-v)<r+2:
                    raise ValueError('Access hole needs at least 2 mm sheet edge ligament')
                if any(math.hypot(u-x,v-y)<r+d/2+2 for x,y,d in panel.holes):
                    raise ValueError('Access hole overlaps another hole or its ligament')
                panel.holes.append((u,v,hole.diameter))
    return result
