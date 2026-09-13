import pytest
from test_inset import raw
from weldbox.spec import BoxSpec
from weldbox.frame import resolve_frame
from weldbox.features import plan_features,RivetHole
from weldbox.vendors import get_vendor
from weldbox.panels.layout import panel_layouts,hole_global_position


def config():
    data=raw();s=data['siding'];s['fit']='opening_overlay';s.pop('inset')
    s['opening_overlay']=dict(clearance=2,edge_overlap=24,hole_offset=12,split_heights=[602],fastener_spacing=300,end_offset=20,
        fastener=dict(panel_hole=6.1,receiver_hole=6.4,grip_min=3.0,grip_max=5.3,panel_max=2.5,grommet='NY-4G-43-20',plunger='NY-4P-43-1-50'))
    return data


def build(data=None):
    spec=BoxSpec.model_validate(data or config());frame=resolve_frame(spec,get_vendor('rmfg').catalog());holes=plan_features(frame,spec)
    return spec,frame,panel_layouts(frame,spec,holes)


def test_tube_receivers_are_coaxial_and_no_tabs():
    _,frame,panels=build();assert len(panels)==8 and all(p.face.startswith('cover:') for p in panels)
    assert {round(p.width,2) for p in panels}=={971.8}
    receivers=[(m,h) for m in frame.members for h in m.features if isinstance(h,RivetHole)]
    assert len(receivers)==40 and all(m.axis=='z' for m,h in receivers)
    for p in panels:
        for u,v,d in p.holes:
            point=tuple(p.origin3d[i]+u*p.u_dir[i]+v*p.v_dir[i] for i in range(3))
            matches=[h for m,h in receivers if max(abs(a-b) for a,b in zip(hole_global_position(m,h),point))<1e-5]
            assert len(matches)==1 and matches[0].dia==6.4 and d==6.1


def test_old_grip_range_rejected():
    data=config();data['siding']['opening_overlay']['fastener'].update(grip_min=2.1,grip_max=4.4)
    with pytest.raises(ValueError,match='grip'):build(data)


@pytest.mark.parametrize('patch',[dict(edge_overlap=26),dict(hole_offset=8),dict(split_heights=[60])])
def test_bad_geometry_rejected(patch):
    data=config();data['siding']['opening_overlay'].update(patch)
    with pytest.raises(ValueError):build(data)


def test_all_vertical_faces():
    data=config();data['siding']['panels'][0]['faces']=['front','back','left','right']
    _,_,panels=build(data);assert len(panels)==16


@pytest.mark.slow
def test_actual_tube_holes_single_wall_and_cover_seat(tmp_path):
    from build123d import Pos,Cylinder,export_step,import_step
    from weldbox.geometry.assembly import panel_solid,build_frame_compound
    _,frame,panels=build();base=build_frame_compound(frame);p=panels[0];sheet=panel_solid(p)
    assert sheet.is_valid and sheet.distance_to(base)<1e-5
    common=sheet.intersect(base);assert common is None or common.volume<1e-5
    u,v,d=p.holes[0];x=p.origin3d[0]+u;z=p.origin3d[2]+v
    # Front outer wall is Y=0; only that wall is drilled. Probe through both walls.
    outer=Pos(x,1.524,z)*Cylinder(3.2,5,rotation=(90,0,0))
    inner=Pos(x,49.276,z)*Cylinder(3.2,3,rotation=(90,0,0))
    cut=outer.intersect(base);assert cut is None or cut.volume<1e-5
    assert sum(q.volume for q in inner.intersect(base))>80
    path=tmp_path/'cover.step';export_step(sheet,path);rt=import_step(path)
    assert len(rt.solids())==1 and rt.volume==pytest.approx(sheet.volume,rel=1e-6)


def test_top_extension_retains_lower_covers_and_receiver_positions():
    _,before_frame,before=build()
    data=config();data['siding']['opening_overlay']['top_extension']=50.8
    _,frame,panels=build(data)
    assert {round(p.height,2) for p in panels}=={547.2,144.0}
    old_holes=[hole_global_position(m,h) for m in before_frame.members for h in m.features if isinstance(h,RivetHole)]
    new_holes=[hole_global_position(m,h) for m in frame.members for h in m.features if isinstance(h,RivetHole)]
    assert old_holes==new_holes
    for a,b in zip(before,panels):
        assert a.origin3d==b.origin3d and a.holes==b.holes
        if a.height>200:assert a==b


def test_panel_access_holes_do_not_add_tube_features():
    data=config();cfg=data['siding']['opening_overlay'];cfg['top_extension']=50.8
    cfg['access_holes']=[dict(face=f,u=x,v=724.6,diameter=6.6) for f in ['front','back'] for x in [310,390,810,890,1310,1390,1810,1890]]
    _,frame,panels=build(data)
    assert len([h for m in frame.members for h in m.features if isinstance(h,RivetHole)])==40
    holes=[(p,u,v) for p in panels for u,v,d in p.holes if d==6.6]
    assert len(holes)==16 and all(p.origin3d[2]+v==pytest.approx(724.6) for p,u,v in holes)
    assert all(p.height==pytest.approx(144) for p,u,v in holes)


@pytest.mark.parametrize('patch',[
    dict(top_extension=55),
    dict(access_holes=[dict(face='front',u=1000,v=724.6,diameter=6.6)]),
    dict(access_holes=[dict(face='front',u=500,v=600,diameter=6.6)]),
    dict(access_holes=[dict(face='left',u=100,v=724.6,diameter=6.6)]),
    dict(access_holes=[dict(face='front',u=40,v=724.6,diameter=30)]),
])
def test_invalid_extension_and_access_holes_rejected(patch):
    data=config();data['siding']['opening_overlay'].update(top_extension=50.8)
    data['siding']['opening_overlay'].update(patch)
    with pytest.raises(ValueError):build(data)


@pytest.mark.slow
def test_extended_sheet_access_hole_survives_step(tmp_path):
    from build123d import Pos,Cylinder,export_step,import_step
    from weldbox.geometry.assembly import panel_solid
    data=config();cfg=data['siding']['opening_overlay'];cfg.update(top_extension=50.8,access_holes=[dict(face='front',u=310,v=724.6,diameter=6.6)])
    _,_,panels=build(data);panel=next(p for p in panels if any(h[2]==6.6 for h in p.holes))
    sheet=panel_solid(panel);assert sheet.is_valid and len(sheet.solids())==1
    probe=Pos(310,-.75,724.6)*Cylinder(3.3,4,rotation=(90,0,0));common=sheet.intersect(probe)
    assert common is None or common.volume<1e-5
    path=tmp_path/'extended.step';export_step(sheet,path);rt=import_step(path)
    assert rt.volume==pytest.approx(sheet.volume,rel=1e-6)


def test_export_keeps_access_holes_out_of_fastener_quantity(tmp_path):
    import json
    from weldbox.generate import produce_outputs
    data=config();data['siding']['opening_overlay'].update(top_extension=50.8,access_holes=[dict(face='front',u=310,v=724.6,diameter=6.6)])
    spec=BoxSpec.model_validate(data);frame=resolve_frame(spec,get_vendor('rmfg').catalog())
    out=produce_outputs(spec,frame,tmp_path)
    counts=json.loads((out/'panel-fasteners.json').read_text())
    assert counts['quantity_per_assembly']==40 and counts['access_hole_count']==1
    instances=json.loads((out/'panel-layouts.json').read_text())
    assert sum(1 for p in instances for u,v,d in p['holes'] if d==6.6)==1
