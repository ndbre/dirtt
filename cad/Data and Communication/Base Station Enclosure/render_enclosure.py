"""Render preview images of the enclosure (needs the three.js renderer render3d.js)."""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pi5_enclosure as E
from PIL import Image, ImageDraw, ImageFont

R = sys.argv[1]            # path to render3d.js
TMP = sys.argv[2]          # scratch dir
OUT = os.path.join(E.OUT, "DIRTT_pi5_enclosure_preview.png")

def mesh(shape, color, opacity=1.0, dz=0.0, edges=True):
    vs, fs = shape.val().tessellate(0.05, 0.3)
    v = []
    for p in vs: v += [p.x, p.y, p.z + dz]
    f = [i for t in fs for i in t]
    m = {"v": v, "f": f, "color": color, "opacity": opacity}
    if not edges: m["edges"] = False
    return m

base, lid = E.make_base(), E.make_lid()
B = E.make_boards()
board_colors = {"pi_pcb": "#2e8b57", "pi_parts": "#b8b8b8", "bonnet_pcb": "#1f3f8f", "bonnet_header": "#222222",
                "oled": "#111111", "oled_active": "#5ec8ff", "buttons": "#444444", "radio": "#c0c0c0",
                "sma": "#d4a017", "spacers": "#e8e8e8"}
boards = lambda dz=0.0: [mesh(s, board_colors[k], dz=dz, edges=False) for k, s in B.items()]
BASE_C, LID_C = "#f2f2ee", "#ff8c1a"

views = [
    ("Assembled", [mesh(base, BASE_C), mesh(lid, LID_C)] + boards(), [0.55, -1.0, 0.75]),
    ("Lid see-through", [mesh(base, BASE_C), mesh(lid, LID_C, 0.28)] + boards(), [0.55, -1.0, 0.9]),
    ("Exploded", [mesh(base, BASE_C), mesh(lid, LID_C, dz=38)] + boards(14), [-0.6, -1.0, 0.55]),
    ("Back / left side", [mesh(base, BASE_C), mesh(lid, LID_C)] + boards(), [-0.9, 0.8, 0.5]),
    ("Underside of lid", [mesh(lid.rotate((0,0,0),(1,0,0),180), LID_C)], [0.3, -0.6, 1.0]),
    ("Base", [mesh(base, BASE_C)], [0.4, -0.8, 1.0]),
]
tiles = []
for i, (title, meshes, d) in enumerate(views):
    sf = os.path.join(TMP, f"enc_scene{i}.json"); png = os.path.join(TMP, f"enc_view{i}.png")
    json.dump({"size": [900, 640], "meshes": meshes, "dir": d, "fit": 1.05}, open(sf, "w"))
    subprocess.run(["node", R, sf, png], check=True)
    im = Image.open(png).convert("RGB")
    ImageDraw.Draw(im).text((18, 14), title, fill=(30, 30, 30), font=ImageFont.truetype("DejaVuSans-Bold.ttf", 26))
    tiles.append(im)
W, H = 900, 640
sheet = Image.new("RGB", (W * 2, H * 3 + 60), "white")
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % 2) * W, 60 + (i // 2) * H))
ImageDraw.Draw(sheet).text((20, 14), f"D.I.R.T.T. base station enclosure: Pi 5 + LoRa Bonnet   "
                           f"{E.OUTER[1]-E.OUTER[0]:.1f} x {E.OUTER[3]-E.OUTER[2]:.1f} x {E.H:.0f} mm",
                           fill=(0, 0, 0), font=ImageFont.truetype("DejaVuSans-Bold.ttf", 30))
sheet.save(OUT); print(OUT)
