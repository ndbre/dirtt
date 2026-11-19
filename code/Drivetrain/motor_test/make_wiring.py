"""Draws wiring.svg for the drivetrain motor test (Arduino -> Cytron MDDRC10 -> 4x FIT0185).
python3 make_wiring.py   (writes wiring.svg next to this file)"""
import os

W, H = 1500, 980
RED, BLK, SIG1, SIG2, GRY = "#d62828", "#222222", "#e07a00", "#1f6fd1", "#8a8f94"
out = []


def add(s):
    out.append(s)


def text(x, y, s, size=15, weight="normal", anchor="start", fill="#1f2328", italic=False):
    st = ' font-style="italic"' if italic else ""
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{st}>{s}</text>')


def box(x, y, w, h, fill="#ffffff", stroke="#1f2328", sw=2, rx=6):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def wire(points, color, width=4, dash=None):
    d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(points))
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{da}/>')


def dot(x, y, color):
    add(f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>')


def terminal(x, y, label, side="left"):
    add(f'<circle cx="{x}" cy="{y}" r="9" fill="#9be59b" stroke="#2c6b2c" stroke-width="2"/>')
    add(f'<line x1="{x-5}" y1="{y-5}" x2="{x+5}" y2="{y+5}" stroke="#2c6b2c" stroke-width="2"/>')
    if side == "left":
        text(x + 18, y + 5, label, 14, "bold")
    else:
        text(x - 18, y + 5, label, 14, "bold", "end")


def pin(x, y, label, side="right", fill="#1f2328"):
    add(f'<rect x="{x-6}" y="{y-6}" width="12" height="12" fill="#f2c94c" stroke="#7a5d00" stroke-width="1.5"/>')
    if side == "right":
        text(x - 14, y + 5, label, 13, "bold", "end", fill)
    else:
        text(x + 14, y + 5, label, 13, "bold", "start", fill)


def motor(x, y, name, flip=False):
    # can on the left, gearbox, shaft; leads come out at the right (x+190)
    box(x, y, 120, 64, "#c9ced3", "#4a4f55", 2, 8)
    box(x + 120, y + 8, 50, 48, "#a6adb4", "#4a4f55", 2, 4)
    add(f'<rect x="{x-22}" y="{y+27}" width="22" height="10" fill="#6c737a"/>')
    text(x + 60, y + 30, "FIT0185", 13, "bold", "middle")
    text(x + 60, y + 49, name, 13, "normal", "middle")
    return (x + 170, y + 22), (x + 170, y + 42)          # red lead, black lead start


def lead(start, end_x, y, color):
    wire([start, (start[0] + 25, start[1]), (start[0] + 25, y), (end_x, y)], color, 3.5)


add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'font-family="Segoe UI, Roboto, Helvetica, Arial, sans-serif">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(40, 48, "D.I.R.T.T. drivetrain motor test: wiring", 26, "bold", fill="#5D1725")
text(40, 76, "Arduino sends R/C pulses on D9/D10 → Cytron MDDRC10 (mode switch on MIX) → 2 motors per side in parallel", 15, fill="#555")

# ---------------------------------------------------------------- MDDRC10
DX, DY, DW, DH = 600, 170, 330, 560
box(DX, DY, DW, DH, "#1d2125", "#000", 2, 14)
text(DX + DW / 2, DY + 44, "Cytron MDDRC10", 22, "bold", "middle", "#ffffff")
text(DX + DW / 2, DY + 68, "7–30 V, 10 A per side", 14, "normal", "middle", "#c9ced3")
# terminal block (left edge, top to bottom as on the board)
TX = DX + 26
T = {"MRA": DY + 130, "MRB": DY + 175, "VB+": DY + 260, "VB-": DY + 305, "MLA": DY + 390, "MLB": DY + 435}
box(DX + 10, DY + 108, 120, 92, "#2e7d32", "#9be59b", 1.5, 4)
box(DX + 10, DY + 238, 120, 92, "#2e7d32", "#9be59b", 1.5, 4)
box(DX + 10, DY + 368, 120, 92, "#2e7d32", "#9be59b", 1.5, 4)
for k, y in T.items():
    terminal(TX, y, k.replace("-", "−"))
text(DX + 140, DY + 157, "RIGHT motors", 13, "normal", "start", "#c9ced3")
text(DX + 140, DY + 287, "POWER", 13, "normal", "start", "#c9ced3")
text(DX + 140, DY + 417, "LEFT motors", 13, "normal", "start", "#c9ced3")
# RC header (right edge): RC2 row above RC1 row, as on the board
RX = DX + DW - 30
RC = {"RC2": DY + 150, "+5V ": DY + 178, "GND ": DY + 206, "RC1": DY + 262, "+5V": DY + 290, "GND": DY + 318}
box(RX - 14, DY + 134, 28, 198, "#30353a", "#f2c94c", 1.5, 4)
for k, y in RC.items():
    pin(RX, y, k.strip(), "right", "#ffffff")
text(RX, DY + 120, "RC input", 13, "bold", "end", "#c9ced3")
# mode switch
box(DX + DW - 110, DY + 420, 92, 88, "#30353a", "#ffffff", 1.5, 4)
text(DX + DW - 64, DY + 442, "MIX", 14, "bold", "middle", "#9be59b")
add(f'<rect x="{DX + DW - 76}" y="{DY + 450}" width="24" height="34" rx="3" fill="#ffffff"/>')
add(f'<rect x="{DX + DW - 73}" y="{DY + 453}" width="18" height="14" rx="2" fill="#2e7d32"/>')
text(DX + DW - 64, DY + 500, "IND", 13, "normal", "middle", "#c9ced3")
text(DX + DW - 120, DY + 472, "Set to MIX →", 14, "bold", "end", "#ffd166")
text(DX + 24, DY + 520, "ERR LED: 2 blinks = no pulses", 12, "normal", "start", "#c9ced3")
text(DX + 24, DY + 538, "3 = low battery, 4 = over-voltage", 12, "normal", "start", "#c9ced3")

# ---------------------------------------------------------------- motors (2 per side, parallel)
BUS_X = 420                       # vertical bus where each side's pair joins
fr_r, fr_b = motor(150, 130, "Front-right")
rr_r, rr_b = motor(150, 250, "Rear-right")
fl_r, fl_b = motor(150, 560, "Front-left")
rl_r, rl_b = motor(150, 680, "Rear-left")

# right side: reds -> MRA, blacks -> MRB
for r, b in ((fr_r, fr_b), (rr_r, rr_b)):
    wire([r, (BUS_X, r[1])], RED, 3.5)
    wire([b, (BUS_X + 30, b[1])], BLK, 3.5)
wire([(BUS_X, fr_r[1]), (BUS_X, rr_r[1])], RED, 3.5)
wire([(BUS_X + 30, fr_b[1]), (BUS_X + 30, rr_b[1])], BLK, 3.5)
wire([(BUS_X, (fr_r[1] + rr_r[1]) / 2), (BUS_X + 70, (fr_r[1] + rr_r[1]) / 2), (BUS_X + 70, T["MRA"]), (TX - 10, T["MRA"])], RED, 4)
wire([(BUS_X + 30, (fr_b[1] + rr_b[1]) / 2 + 30), (BUS_X + 100, (fr_b[1] + rr_b[1]) / 2 + 30), (BUS_X + 100, T["MRB"]), (TX - 10, T["MRB"])], BLK, 4)
for p in ((BUS_X, (fr_r[1] + rr_r[1]) / 2), (BUS_X + 30, (fr_b[1] + rr_b[1]) / 2 + 30)):
    dot(*p, RED if p[0] == BUS_X else BLK)

# left side: reds -> MLA, blacks -> MLB
for r, b in ((fl_r, fl_b), (rl_r, rl_b)):
    wire([r, (BUS_X, r[1])], RED, 3.5)
    wire([b, (BUS_X + 30, b[1])], BLK, 3.5)
wire([(BUS_X, fl_r[1]), (BUS_X, rl_r[1])], RED, 3.5)
wire([(BUS_X + 30, fl_b[1]), (BUS_X + 30, rl_b[1])], BLK, 3.5)
ymid_r = (fl_r[1] + rl_r[1]) / 2
ymid_b = (fl_b[1] + rl_b[1]) / 2 + 30
wire([(BUS_X, ymid_r), (BUS_X + 70, ymid_r), (BUS_X + 70, T["MLA"]), (TX - 10, T["MLA"])], RED, 4)
wire([(BUS_X + 30, ymid_b), (BUS_X + 100, ymid_b), (BUS_X + 100, T["MLB"]), (TX - 10, T["MLB"])], BLK, 4)
dot(BUS_X, ymid_r, RED)
dot(BUS_X + 30, ymid_b, BLK)

text(150, 118, "RIGHT SIDE", 14, "bold", fill="#5D1725")
text(150, 548, "LEFT SIDE", 14, "bold", fill="#5D1725")
text(150, 770, "Motor leads: the 2 thick wires (usually red +, black −). Both motors on a side are wired the same.", 12.5, fill="#555")
text(150, 788, "Encoder wires (the 4 thin ones) aren't used for this test: tape them off. Side runs backwards? Swap its pair at the driver.", 12.5, fill="#555")

# ---------------------------------------------------------------- battery, fuse, switch
BX, BY = 170, 410
box(BX, BY, 170, 96, "#30353a", "#000", 2, 8)
add(f'<rect x="{BX+22}" y="{BY-12}" width="26" height="12" fill="{RED}"/>')
add(f'<rect x="{BX+170}" y="{T["VB-"] - 13}" width="12" height="26" fill="{BLK}"/>')
text(BX + 85, BY + 42, "12 V battery", 16, "bold", "middle", "#ffffff")
text(BX + 85, BY + 64, "8 Ah AGM (demo)", 13, "normal", "middle", "#c9ced3")
text(BX + 35, BY + 86, "+", 18, "bold", "middle", "#ff8a8a")
text(BX + 155, T["VB-"] + 6, "−", 18, "bold", "middle", "#ffffff")
# + : battery -> fuse -> switch -> VB+   (runs along y=375, between the right and left motor wiring)
PY = 375
FX, SX, JX = 300, 470, 560
wire([(BX + 35, BY - 12), (BX + 35, PY), (FX - 22, PY)], RED, 4)
box(FX - 22, PY - 13, 44, 26, "#fff3c4", "#7a5d00", 2, 4)
text(FX, PY + 5, "15 A", 12, "bold", "middle")
text(FX, PY - 20, "fuse", 12, "normal", "middle", "#555")
wire([(FX + 22, PY), (SX - 18, PY)], RED, 4)
add(f'<circle cx="{SX-14}" cy="{PY}" r="4" fill="#1f2328"/><circle cx="{SX+14}" cy="{PY}" r="4" fill="#1f2328"/>')
add(f'<line x1="{SX-14}" y1="{PY}" x2="{SX+12}" y2="{PY-16}" stroke="#1f2328" stroke-width="3"/>')
text(SX, PY + 26, "power switch / E-stop", 12, "normal", "middle", "#555")
wire([(SX + 18, PY), (JX, PY), (JX, T["VB+"]), (TX - 10, T["VB+"])], RED, 4)
# − : battery side terminal -> VB−
wire([(BX + 182, T["VB-"]), (TX - 10, T["VB-"])], BLK, 4)

# ---------------------------------------------------------------- Arduino
AX, AY, AW, AH = 1140, 300, 290, 330
box(AX, AY, AW, AH, "#0b6e8c", "#06485c", 2, 14)
text(AX + AW / 2, AY + 40, "Arduino Uno / Nano", 20, "bold", "middle", "#ffffff")
text(AX + AW / 2, AY + 62, "motor_test.ino", 14, "normal", "middle", "#cfe9f2")
A = {"D9": AY + 120, "D10": AY + 175, "GND": AY + 230}
for k, y in A.items():
    pin(AX + 20, y, k, "left")
add(f'<rect x="{AX + AW - 8}" y="{AY + AH - 90}" width="28" height="40" rx="3" fill="#c9ced3" stroke="#4a4f55"/>')
text(AX + AW - 20, AY + AH - 100, "USB", 13, "bold", "end", "#ffffff")
# USB to laptop
wire([(AX + AW + 20, AY + AH - 70), (AX + AW + 40, AY + AH - 70), (AX + AW + 40, AY + AH + 70), (AX + AW - 60, AY + AH + 70)], GRY, 6)
box(AX + 20, AY + AH + 40, 190, 70, "#eef0f1", "#8a8f94", 2, 8)
text(AX + 115, AY + AH + 70, "Laptop", 15, "bold", "middle")
text(AX + 115, AY + AH + 92, "power + Serial Monitor 115200", 12, "normal", "middle", "#555")

# signal wires: D9 -> RC1, D10 -> RC2, GND -> RC GND
wire([(AX + 20, A["D9"]), (AX - 70, A["D9"]), (AX - 70, RC["RC1"]), (RX, RC["RC1"])], SIG1, 4)
wire([(AX + 20, A["D10"]), (AX - 110, A["D10"]), (AX - 110, RC["RC2"]), (RX, RC["RC2"])], SIG2, 4)
wire([(AX + 20, A["GND"]), (AX - 150, A["GND"]), (AX - 150, RC["GND"]), (RX, RC["GND"])], BLK, 4)
KX, KY = 990, 170
text(KX, KY, "Signal wires (any jumper wire)", 14, "bold")
for i, (c, s_) in enumerate(((SIG1, "D9 → RC1: forward / back (throttle)"), (SIG2, "D10 → RC2: turn left / right"), (BLK, "GND → RC GND (shared ground)"))):
    wire([(KX, KY + 22 + i * 22), (KX + 34, KY + 22 + i * 22)], c, 4)
    text(KX + 44, KY + 27 + i * 22, s_, 13)
# +5V not connected
for y in (RC["+5V"], RC["+5V "]):
    add(f'<line x1="{RX+10}" y1="{y}" x2="{RX+40}" y2="{y}" stroke="{GRY}" stroke-width="2" stroke-dasharray="4 4"/>')
    add(f'<text x="{RX+44}" y="{y+5}" font-size="16" font-weight="bold" fill="{RED}">×</text>')
text(950, 585, "+5V pins: not connected", 12.5, "bold", "start", RED)
text(950, 602, "(Arduino runs off USB)", 12.5, "normal", "start", "#555")

# ---------------------------------------------------------------- steps
NY = 820
box(40, NY, W - 80, 140, "#f7f7f5", "#C1C6C8", 1.5, 6)
text(60, NY + 30, "Power-up order", 16, "bold", fill="#5D1725")
steps = [
    "1. Rover on blocks, wheels off the ground. Driver switch on MIX. Power switch OFF.",
    "2. Plug the Arduino into the laptop, upload motor_test.ino, open Serial Monitor (115200, \"Newline\").",
    "3. Switch on the 12 V. The driver takes the Arduino's 1500 µs \"stop\" pulse as its neutral point at power-up,",
    "    so the Arduino must already be running. Then type  test  (or w / s / a / d, x to stop).",
]
for i, s in enumerate(steps):
    text(60, NY + 58 + i * 22, s, 14)
text(W - 60, NY + 128, "Wire gauge: 16 AWG for battery and motor leads, any jumper wire for signals.", 12.5, "normal", "end", "#555")

add("</svg>")
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wiring.svg")
open(path, "w").write("\n".join(o for o in out if o))
print(path)
