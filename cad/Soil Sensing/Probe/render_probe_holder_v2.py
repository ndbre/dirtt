"""Preview sheet for the v2 probe holder:
    python3 render_probe_holder_v2.py DIRTT_probe_holder_v2.stl DIRTT_probe_holder_v2_preview.png path/to/render3d.js
"""
import json, os, subprocess, sys, numpy as np, trimesh
from trimesh.creation import cylinder, box
from shapely.geometry import Point
from PIL import Image, ImageDraw, ImageFont
H = trimesh.load(sys.argv[1]); OUT = sys.argv[2]; R = sys.argv[3]  # the three.js renderer render3d.js (same one the enclosure preview uses)
S = 6.0  # skirt offset (holder was moved up by 6)
def m(t, color, opacity=1.0, edges=True):
    d = {"v": t.vertices.ravel().tolist(), "f": t.faces.ravel().tolist(), "color": color, "opacity": opacity}
    if not edges: d["edges"] = False
    return d
def ycyl(r, y0, y1, x, z):
    c = cylinder(radius=r, height=y1-y0, sections=32); c.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1,0,0])); c.apply_translation([x,(y0+y1)/2,z]); return c
def zc(r, z0, z1, x=0, y=0, sec=64):
    c = cylinder(radius=r, height=z1-z0, sections=sec); c.apply_translation([x,y,(z0+z1)/2]); return c
ob = Point(-15,0).buffer(7.6,48).union(Point(15,0).buffer(7.6,48)).convex_hull
sensor = trimesh.creation.extrude_polygon(ob, 29.8); sensor.apply_translation([0,0,S])
pins = [zc(1.6, S-60, S, x=x, sec=16) for x in (-11.25,-3.75,3.75,11.25)]
cable = zc(3.0, S+29.8, S+45)
rod = zc(10.0, S+65, S+65+60)
cap = trimesh.creation.box(extents=[36,44,14]); cap.apply_translation([0,0,S+65+24+7])
def bolt(y_head, y_tip, x, z):  # head at y_head, shank to y_tip
    sgn = 1 if y_head > y_tip else -1
    return [ycyl(2.0, min(y_head,y_tip), max(y_head,y_tip), x, z), ycyl(3.5, y_head, y_head+sgn*4, x, z) if sgn>0 else ycyl(3.5, y_head-4, y_head, x, z)]
hw = []
hw += bolt(20.5, 4.5, 0, S+79.5)                         # rod bolt M4x16
for x in (-19, 19): hw += bolt(13.0, -12.0, x, S-2.2)    # cross bolts M4x25
for x in (-10, 10): hw += bolt(19.0, 7.8, x, S+15)       # pinch bolts (snug)
nuts = [box(extents=[7,3.2,8]) for _ in range(3)]
for n,(x,y,z) in zip(nuts,[(0,13.7,S+79.5),(-10,14.0,S+15),(10,14.0,S+15)]): n.apply_translation([x,y,z])
frame = trimesh.boolean.difference([box(extents=[80,60,2]), box(extents=[62,40.2,4])], engine="manifold"); frame.apply_translation([0,5.9,-3])
HOLD, SEN, ROD, HW = "#f0efe8", "#2f7d4a", "#c8ccd2", "#3a3a3a"
views = [
 ("Assembled, from the front", [m(H,HOLD), m(sensor,SEN), m(cable,"#111111",edges=False), m(rod,ROD), m(cap,"#222222")] + [m(p,"#8a8f96",edges=False) for p in pins] + [m(h,HW,edges=False) for h in hw], [0.7,-1.0,0.35]),
 ("From the back: bolts", [m(H,HOLD), m(sensor,SEN), m(rod,ROD)] + [m(p,"#8a8f96",edges=False) for p in pins] + [m(h,HW,edges=False) for h in hw] + [m(n,"#9a9a9a",edges=False) for n in nuts], [-0.6,1.0,0.35]),
 ("Holder alone", [m(H,HOLD)], [0.8,-0.9,0.6]),
 ("See-through: sensor, cross bolts, rod bolt", [m(H,HOLD,0.3), m(sensor,SEN), m(rod,ROD)] + [m(p,"#8a8f96",edges=False) for p in pins] + [m(h,"#c0392b",edges=False) for h in hw] + [m(n,"#e67e22",edges=False) for n in nuts], [1.0,-0.5,0.25]),
 ("Top down: fits the tower's base opening (orange)", [m(frame,"#e69f00"), m(H,HOLD)], [0.0,-0.02,1.0]),
 ("Underside: pocket, cross bolts", [m(H,HOLD), m(sensor,SEN)] + [m(h,"#c0392b",edges=False) for h in hw[2:6]], [0.5,-0.7,-0.9]),
]
tiles = []
for i,(title, meshes, d) in enumerate(views):
    sf = f"/tmp/h{i}.json"; png = f"/tmp/h{i}.png"
    json.dump({"size":[800,800], "meshes":meshes, "dir":d, "fit":1.08}, open(sf,"w"))
    subprocess.run(["node", R, sf, png], check=True, capture_output=True)
    im = Image.open(png).convert("RGB"); ImageDraw.Draw(im).text((16,12), title, fill=(30,30,30), font=ImageFont.truetype("DejaVuSans-Bold.ttf", 24)); tiles.append(im)
W=800; sheet = Image.new("RGB",(W*3, W*2+60),"white")
for i,t in enumerate(tiles): sheet.paste(t,((i%3)*W, 60+(i//3)*W))
lo, hi = H.bounds
ImageDraw.Draw(sheet).text((20,14), f"D.I.R.T.T. probe holder v2: 20 mm actuator rod + SEN0604, all M4   {hi[0]-lo[0]:.1f} x {hi[1]-lo[1]:.1f} x {hi[2]-lo[2]:.1f} mm", fill=(0,0,0), font=ImageFont.truetype("DejaVuSans-Bold.ttf", 30))
sheet.save(OUT); print(OUT)
