from pathlib import Path
import pytest
import ezdxf
from weldbox.spec import BoxSpec
from weldbox.frame import resolve_frame
from weldbox.features import plan_features
from weldbox.vendors import get_vendor
from weldbox.panels.layout import panel_layouts
from weldbox.panels.dxf import write_panel_dxf


def raw():
    return dict(name='Inset test',material=dict(shape='square',size=['2in'],wall='.120in',family='A500'),
        exterior=dict(width=2000,depth=710,height=750),topology='top_bottom_frames',
        blocking=[dict(type='supports',between=['base','top'],at='midpoints')],consolidate=False,
        siding=dict(fit='inset',corner_radius=2,panels=[dict(faces=['front','back'],material=dict(alloy='5052',thickness=1.5))],
        inset=dict(recess=10,split_heights=[602],tab_material=dict(alloy='A36',thickness=2),fastener=dict(panel_hole=6.1,receiver_hole=6.4,grip_min=2.1,grip_max=4.4,panel_max=1.6,grommet='NY-4G-42-20',plunger='NY-4P-42-1-50'))))


def layout(data=None):
    spec=BoxSpec.model_validate(data or raw()); frame=resolve_frame(spec,get_vendor('rmfg').catalog())
    holes=plan_features(frame,spec)
    assert holes=={} # no overlay rivet holes added to the tube
    return spec,frame,panel_layouts(frame,spec,holes)


def test_openings_split_and_different_holes(tmp_path):
    spec,frame,parts=layout(); panels=[p for p in parts if p.face.startswith('inset:')];tabs=[p for p in parts if p.face.startswith('tab:')]
    assert len(panels)==8 and len(tabs)==40
    assert {round(p.width,3) for p in panels}=={919.8}
    assert {round(p.height,3) for p in panels}=={547.2,93.2}
    for p in panels:
        assert p.origin3d[2] == pytest.approx(52.8) or p.origin3d[2] == pytest.approx(604)
        for u,v,d in p.holes:
            assert min(u,p.width-u,v,p.height-v)>d/2+2
            center=tuple(p.origin3d[i]+u*p.u_dir[i]+v*p.v_dir[i] for i in range(3))
            mates=[]
            for t in tabs:
                tu,tv,td=t.holes[0];tc=tuple(t.origin3d[i]+tu*t.u_dir[i]+tv*t.v_dir[i] for i in range(3))
                if abs(tc[0]-center[0])<1e-6 and abs(tc[2]-center[2])<1e-6 and abs(abs(tc[1]-center[1])-2)<1e-6: mates.append(t)
            assert len(mates)==1 and d==6.1 and mates[0].holes[0][2]==6.4
    out=tmp_path/'panel.dxf';write_panel_dxf(panels[0],out);drawing=ezdxf.readfile(out)
    assert drawing.header['$INSUNITS']==4
    assert len(drawing.modelspace().query('CIRCLE'))==6


@pytest.mark.parametrize('change',[lambda d:d['siding']['inset']['fastener'].update(grip_max=3),lambda d:d['siding']['panels'][0]['material'].update(thickness=2),lambda d:d['siding']['panels'][0].update(faces=['top']),lambda d:d['siding']['inset'].update(split_heights=[602,602]),lambda d:d['siding']['inset'].update(tab_projection=8)])
def test_invalid_configs_rejected(change):
    data=raw();change(data)
    with pytest.raises(ValueError):BoxSpec.model_validate(data)


def test_all_vertical_faces_and_no_split():
    data=raw();data['siding']['panels'][0]['faces']=['left','right','front','back'];data['siding']['inset']['split_heights']=[]
    _,_,parts=layout(data)
    assert len([p for p in parts if p.face.startswith('inset:')])==8


@pytest.mark.slow
def test_panel_tab_seat_and_frame_clearance(tmp_path):
    from weldbox.geometry.assembly import panel_solid,build_frame_compound
    from build123d import export_step,import_step
    _,frame,parts=layout();p=next(p for p in parts if p.face=='inset:front');t=next(t for t in parts if t.face=='tab:front')
    ps,ts=panel_solid(p),panel_solid(t)
    assert ps.is_valid and ts.is_valid
    common=ps.intersect(ts)
    assert common is None or common.volume<1e-5
    assert ps.distance_to(ts)<1e-5
    base=build_frame_compound(frame)
    assert ts.distance_to(base)<1e-5
    for solid in (ps,ts):
        common=solid.intersect(base)
        assert common is None or common.volume<1e-5
    out=tmp_path/'inset.step';export_step(ps,out);rt=import_step(out)
    assert len(rt.solids())==1 and rt.volume==pytest.approx(ps.volume,rel=1e-6)


def test_tab_recess_must_clear_rounded_tube_corner():
    data=raw();data['siding']['inset']['recess']=0
    with pytest.raises(ValueError,match='flat tube wall'):layout(data)


def test_tiny_split_rejected():
    data=raw();data['siding']['inset']['split_heights']=[60]
    with pytest.raises(ValueError,match='too small'):layout(data)
