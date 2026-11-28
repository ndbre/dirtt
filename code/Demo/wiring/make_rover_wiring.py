"""Draws rover_wiring.svg: the whole D.I.R.T.T. rover, December demo configuration.

python3 make_rover_wiring.py            (writes rover_wiring.svg next to this file)

Sources: the FDR drivetrain wiring (rev A) for the power path, fuses, relay and E-stop; the demo
code (code/Demo/rover.py) for the Pi pins; DFRobot's SEN0604 page for the sensor's wires.
Dashed = planned, not needed for the demo.
"""
import os

W, H = 2400, 1700
RED, BLK, MOT, SIG, I2C, EST, USB, RS4, GRY = ("#d62828", "#222222", "#1f6fd1", "#e08a00", "#2a9d8f",
                                              "#8e44ad", "#555555", "#c0392b", "#9aa0a6")
FONT = "Segoe UI, Roboto, Helvetica, Arial, sans-serif"
out = []


def add(s):
    out.append(s)


def text(x, y, s, size=15, weight="normal", anchor="start", fill="#1f2328", italic=False):
    st = ' font-style="italic"' if italic else ""
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{fill}"{st}>{s}</text>')


def box(x, y, w, h, fill="#ffffff", stroke="#1f2328", sw=2, rx=8, dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{sw}"{da}/>')


def wire(points, color, width=4, dash=None):
    d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(points))
    da = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" '
        f'stroke-linecap="round"{da}/>')


def node(x, y, color="#1f2328", r=6):
    add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')


def term(x, y, label="", side="right", color="#1f2328", size=14):
    add(f'<circle cx="{x}" cy="{y}" r="7" fill="#ffffff" stroke="{color}" stroke-width="2.5"/>')
    if label:
        if side == "right":
            text(x + 13, y + 5, label, size, "bold")
        elif side == "left":
            text(x - 13, y + 5, label, size, "bold", "end")
        elif side == "above":
            text(x, y - 13, label, size, "bold", "middle")
        else:
            text(x, y + 24, label, size, "bold", "middle")


def gnd(x, y, label="to − bus", awg="", left=False):
    """Ground symbol: its own wire back to the fuse block's − bus."""
    wire([(x, y), (x, y + 14)], BLK, 3)
    for i, w in enumerate((22, 14, 6)):
        wire([(x - w / 2, y + 14 + i * 6), (x + w / 2, y + 14 + i * 6)], BLK, 2.5)
    t = label + (f", {awg}" if awg else "")
    if left:
        text(x - 16, y + 26, t, 12, "normal", "end", "#444")
    else:
        text(x + 16, y + 26, t, 12, "normal", "start", "#444")


def tag(x, y, s, color, anchor="middle"):
    text(x, y, s, 13, "bold", anchor, color)


add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    f'font-family="{FONT}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(50, 56, "D.I.R.T.T. rover wiring: December demo", 30, "bold")
text(50, 88, "Rover Pi 3 B drives the Cytron MDDRC10 directly (no flight controller yet). Dashed parts are "
             "planned and not needed for the demo.", 17, fill="#555")

# ============================================================================== POWER PATH
# battery
box(50, 160, 230, 190)
text(165, 198, "Battery", 22, "bold", "middle")
text(165, 224, "LiFePO4 12.8 V 20 Ah", 15, "normal", "middle", "#555")
text(165, 246, "(built-in BMS)", 14, "normal", "middle", "#777")
term(280, 290, "+", "left", RED)
term(280, 330, "−", "left", BLK)
# XT60
box(330, 250, 56, 110, "#f3f3f3")
text(358, 238, "XT60", 15, "bold", "middle")
text(358, 385, "unplug", 13, "normal", "middle", "#666")
text(358, 401, "to charge", 13, "normal", "middle", "#666")
# 20 A fuse + switch
wire([(287, 290), (440, 290)], RED, 7)
box(440, 266, 120, 48, "#fff6d6")
text(500, 297, "20 A fuse", 16, "bold", "middle")
text(500, 336, "≤ 6 in from battery", 13, "normal", "middle", "#666", True)
wire([(560, 290), (630, 290)], RED, 7)
add('<circle cx="680" cy="290" r="48" fill="#ffffff" stroke="#1f2328" stroke-width="2.5"/>')
wire([(652, 312), (708, 268)], BLK, 4)
text(680, 228, "Main switch", 16, "bold", "middle")
text(680, 362, "rotary disconnect", 13, "normal", "middle", "#666")
wire([(728, 290), (830, 290)], RED, 7)
tag(780, 280, "14 AWG", RED)
tag(416, 280, "14 AWG", RED)

# fuse block
FBX, FBY, FBW, FBH = 830, 150, 330, 640
box(FBX, FBY, FBW, FBH, "#fafafa")
text(FBX + FBW / 2, FBY - 14, "6-way fuse block (with − bus)", 17, "bold", "middle")
box(FBX + 18, FBY + 50, 26, 480, "#f6d2d2", RED, 1.5, 3)
text(FBX + 31, FBY + 40, "+ bus", 13, "normal", "middle", RED)
fuses = [("F1 15 A", "motors, via relay", True), ("F2 2 A", "E-stop loop", True),
         ("F3 5 A", "5 V → Pi", True), ("F4 2 A", "soil sensor", True),
         ("F5 —", "spare", False), ("F6 —", "spare", False)]
FY = {}
for i, (name, what, used) in enumerate(fuses):
    y = FBY + 80 + i * 78
    FY[i + 1] = y
    wire([(FBX + 44, y), (FBX + 80, y)], RED if used else GRY, 3)
    box(FBX + 80, y - 22, 120, 44, "#ffffff", "#1f2328" if used else GRY, 2, 4)
    text(FBX + 140, y + 6, name, 15, "bold", "middle", "#1f2328" if used else GRY)
    text(FBX + 210, y + 26, what, 12, "normal", "start", "#555" if used else GRY)
    wire([(FBX + 200, y), (FBX + FBW, y)], "#1f2328" if used else GRY, 2)
box(FBX + 18, FBY + FBH - 62, FBW - 36, 40, "#dddddd")
text(FBX + FBW / 2, FBY + FBH - 36, "− bus (ground)", 15, "bold", "middle")
GND_Y = FBY + FBH - 42
# battery − to − bus
wire([(287, 330), (300, 330), (300, 470), (760, 470), (760, GND_Y), (FBX + 18, GND_Y)], BLK, 7)
tag(600, 460, "14 AWG", BLK)

# relay
RX, RY = 1260, 150
box(RX, RY, 230, 170)
text(RX + 115, RY + 34, "Relay", 19, "bold", "middle")
text(RX + 115, RY + 58, "12 V 40 A SPST", 14, "normal", "middle", "#555")
term(RX, FY[1], "30", "right")
term(RX + 230, FY[1], "87", "left")
term(RX + 60, RY + 170, "86", "above")
term(RX + 170, RY + 170, "85", "above")
text(RX + 115, RY + 140, "coil", 13, "normal", "middle", "#777", True)
wire([(FBX + FBW, FY[1]), (RX - 7, FY[1])], RED, 6)
tag((FBX + FBW + RX) / 2, FY[1] - 10, "14 AWG", RED)

# E-stop
EX, EY = 1250, 400
box(EX, EY, 250, 120, "#fdecec", RED, 2.5)
text(EX + 125, EY + 32, "E-STOP", 20, "bold", "middle", RED)
text(EX + 125, EY + 55, "NC contact (pressed = open)", 13, "normal", "middle", "#555")
wire([(FBX + FBW, FY[2]), (EX - 40, FY[2]), (EX - 40, EY + 85), (EX + 30, EY + 85)], EST, 3.5)
wire([(EX + 30, EY + 85), (EX + 70, EY + 85)], EST, 3.5)
wire([(EX + 75, EY + 92), (EX + 165, EY + 74)], BLK, 3)
wire([(EX + 175, EY + 85), (EX + 210, EY + 85), (EX + 210, EY - 30), (RX + 60, EY - 30), (RX + 60, RY + 177)],
     EST, 3.5)
tag(EX - 40, FY[2] - 10, "18 AWG", EST)
wire([(RX + 170, RY + 177), (RX + 170, RY + 195), (RX + 240, RY + 195), (RX + 240, RY + 205)], BLK, 2.5)
gnd(RX + 240, RY + 205, "− bus")
text(EX + 125, EY + 145, "NO contact → Pi GPIO27 + GND (later)", 13, "normal", "middle", GRY)

# ============================================================================== MDDRC10 + MOTORS
MX, MY, MW, MH = 1640, 150, 330, 560
box(MX, MY, MW, MH, "#1d2125", "#000", 2, 14)
text(MX + MW / 2, MY + 40, "Cytron MDDRC10", 22, "bold", "middle", "#ffffff")
text(MX + MW / 2, MY + 64, "switch on MIX", 15, "bold", "middle", "#f2c94c")
text(MX + MW / 2, MY + 86, "RC1 = throttle, RC2 = steering", 13, "normal", "middle", "#c9ced3")
VBP, VBN = MY + 140, MY + 190
for lbl, y in (("VB+", VBP), ("VB−", VBN)):
    add(f'<circle cx="{MX}" cy="{y}" r="8" fill="#9be59b" stroke="#2c6b2c" stroke-width="2"/>')
    text(MX + 16, y + 5, lbl, 15, "bold", "start", "#ffffff")
wire([(RX + 237, FY[1]), (1580, FY[1]), (1580, VBP), (MX - 8, VBP)], RED, 6)
tag(1560, FY[1] - 10, "14 AWG", RED)
wire([(MX - 8, VBN), (1590, VBN), (1590, VBN + 70)], BLK, 6)
gnd(1590, VBN + 70, "− bus", left=True)
OUTS = {"MLA": MY + 270, "MLB": MY + 315, "MRA": MY + 410, "MRB": MY + 455}
for lbl, y in OUTS.items():
    add(f'<circle cx="{MX + MW}" cy="{y}" r="8" fill="#9be59b" stroke="#2c6b2c" stroke-width="2"/>')
    text(MX + MW - 16, y + 5, lbl, 15, "bold", "end", "#ffffff")
text(MX + MW - 16, MY + 245, "LEFT", 13, "bold", "end", "#c9ced3")
text(MX + MW - 16, MY + 385, "RIGHT", 13, "bold", "end", "#c9ced3")
RC = {"RC1": MX + 70, "RC2": MX + 160, "GND": MX + 250}
for lbl, x in RC.items():
    add(f'<rect x="{x - 7}" y="{MY + MH - 7}" width="14" height="14" fill="#f2c94c" stroke="#7a5d00"/>')
    text(x, MY + MH - 18, lbl, 14, "bold", "middle", "#ffffff")
text(MX + MW / 2, MY + MH - 60, "RC +5V pin: not connected", 13, "normal", "middle", "#aaa", True)


def motor(x, y, name):
    box(x, y, 150, 76, "#eef4fb", "#1f2328", 2)
    add(f'<circle cx="{x + 118}" cy="{y + 38}" r="24" fill="#ffffff" stroke="#1f2328" stroke-width="2.5"/>')
    text(x + 118, y + 46, "M", 20, "bold", "middle")
    text(x + 50, y + 32, "FIT0185", 13, "bold", "middle")
    text(x + 50, y + 52, name, 13, "normal", "middle", "#555")
    return (x, y + 22), (x, y + 56)


MOT_Y = {"LF": 150, "LR": 290, "RF": 500, "RR": 640}
NAMES = {"LF": "left front", "LR": "left rear", "RF": "right front", "RR": "right rear"}
mot = {k: motor(2190, y, NAMES[k]) for k, y in MOT_Y.items()}
for (a, b, ka, kb, xp, xn) in (("MLA", "MLB", "LF", "LR", 2070, 2100), ("MRA", "MRB", "RF", "RR", 2130, 2160)):
    ya, yb = OUTS[a], OUTS[b]
    (p1, n1), (p2, n2) = mot[ka], mot[kb]
    wire([(MX + MW + 8, ya), (xp, ya)], MOT, 3.5)
    wire([(MX + MW + 8, yb), (xn, yb)], MOT, 3.5)
    ys_p = [ya, p1[1], p2[1]]
    ys_n = [yb, n1[1], n2[1]]
    wire([(xp, min(ys_p)), (xp, max(ys_p))], MOT, 3.5)
    wire([(xn, min(ys_n)), (xn, max(ys_n))], MOT, 3.5)
    for y in ys_p:
        node(xp, y, MOT, 5)
    for y in ys_n:
        node(xn, y, MOT, 5)
    for (px, py) in (p1, p2):
        wire([(xp, py), (px, py)], MOT, 3.5)
        text(px - 8, py - 6, "+", 13, "bold", "end")
    for (nx, ny) in (n1, n2):
        wire([(xn, ny), (nx, ny)], MOT, 3.5)
        text(nx - 8, ny + 16, "−", 13, "bold", "end")
tag(2240, 745, "18 AWG", MOT)
text(2060, 765, "Each side's two motors in parallel. A side", 13, "normal", "start", "#555")
text(2060, 783, "runs backward: swap its two leads at the", 13, "normal", "start", "#555")
text(2060, 801, "MDDRC10. Lines crossing without a dot", 13, "normal", "start", "#555")
text(2060, 819, "are not connected.", 13, "normal", "start", "#555")

# actuator (PROBE mode)
AX, AY = 2060, 845
box(AX, AY, 290, 120, "#fff8e6", "#b07a00", 2.5, 8, "10,6")
text(AX + 145, AY + 30, "Linear actuator, 8 in, 12 V", 15, "bold", "middle")
text(AX + 145, AY + 54, "PROBE mode: unplug the LEFT motor", 13, "normal", "middle", "#555")
text(AX + 145, AY + 72, "pair from MLA/MLB, plug this in", 13, "normal", "middle", "#555")
text(AX + 145, AY + 90, "instead. 12 V OFF while swapping.", 13, "normal", "middle", "#555")
text(AX + 145, AY + 110, "Its own limit switches stop it at each end.", 12, "normal", "middle", "#777", True)
wire([(MX + MW + 8, OUTS["MLA"] + 12), (2035, OUTS["MLA"] + 12), (2035, AY + 40), (AX, AY + 40)],
     "#b07a00", 3, "10,6")
wire([(MX + MW + 8, OUTS["MLB"] + 12), (2015, OUTS["MLB"] + 12), (2015, AY + 80), (AX, AY + 80)],
     "#b07a00", 3, "10,6")

# ============================================================================== 5 V + PI
BX, BY = 1250, 600
box(BX, BY, 250, 120, "#eef7ee")
text(BX + 125, BY + 32, "5 V buck converter", 17, "bold", "middle")
text(BX + 125, BY + 56, "set to 5.1 V BEFORE", 13, "bold", "middle", RED)
text(BX + 125, BY + 74, "connecting the Pi", 13, "bold", "middle", RED)
text(BX + 125, BY + 98, "≥ 3 A", 13, "normal", "middle", "#555")
term(BX, BY + 30, "IN+", "right", RED, 12)
term(BX, BY + 90, "IN−", "right", BLK, 12)
term(BX + 250, BY + 30, "OUT+", "left", RED, 12)
term(BX + 250, BY + 90, "OUT−", "left", BLK, 12)
wire([(FBX + FBW, FY[3]), (1200, FY[3]), (1200, BY + 30), (BX - 7, BY + 30)], RED, 3.5)
tag(BX - 60, BY + 45, "18 AWG", RED)
wire([(BX - 7, BY + 90), (1215, BY + 90), (1215, BY + 112)], BLK, 3.5)
gnd(1215, BY + 112, "− bus")

PX, PY, PW, PH = 1080, 960, 420, 470
box(PX, PY, PW, PH, "#e8f1e4", "#2e7d32", 2.5, 14)
text(PX + 30, PY + 44, "Rover Pi 3 B", 22, "bold")
text(PX + 30, PY + 70, "+ Adafruit RFM95W LoRa Bonnet (915 MHz)", 14, "normal", "start", "#555")
text(PX + 30, PY + 92, "Bonnet uses SPI, CE1, GPIO22, GPIO25,", 13, "normal", "start", "#777")
text(PX + 30, PY + 110, "OLED on I2C 0x3C; buttons on 5, 6, 12", 13, "normal", "start", "#777")
text(PX + 30, PY + 145, "Use the Bonnet's breakout holes", 13, "bold", "start", "#2e7d32")
text(PX + 30, PY + 163, "(the Pi header is covered).", 13, "normal", "start", "#555")
# antenna
wire([(PX + 60, PY), (PX + 60, PY - 50)], "#444", 3)
wire([(PX + 45, PY - 50), (PX + 75, PY - 50)], "#444", 3)
text(PX + 85, PY - 40, "antenna", 13, "normal", "start", "#555")
PINS = ["5V", "GND", "GPIO18", "GPIO19", "GND", "3V3", "GND", "SDA", "SCL", "GPIO27", "GPIO16", "GPIO20"]
PIN_Y = {}
for i, p in enumerate(PINS):
    y = PY + 40 + i * 35
    PIN_Y[(p, i)] = y
    later = p in ("GPIO27", "GPIO16", "GPIO20")
    add(f'<rect x="{PX + PW - 7}" y="{y - 7}" width="14" height="14" fill="{"#eeeeee" if later else "#f2c94c"}" '
        f'stroke="{"#aaa" if later else "#7a5d00"}"/>')
    text(PX + PW - 16, y + 5, p, 14, "bold", "end", GRY if later else "#1f2328")
py = {k[0] + str(k[1]): v for k, v in PIN_Y.items()}
P5, PG1, P18, P19, PG2, P33, PG3, PSDA, PSCL, P27, P16, P20 = (PIN_Y[(p, i)] for i, p in enumerate(PINS))
# 5 V in (to the Bonnet's 5V and GND holes)
wire([(BX + 257, BY + 30), (1540, BY + 30), (1540, P5), (PX + PW + 7, P5)], RED, 3.5)
wire([(BX + 257, BY + 90), (1525, BY + 90), (1525, PG1), (PX + PW + 7, PG1)], BLK, 3.5)
tag(1548, (BY + 30 + P5) / 2, "20 AWG, short", RED, "start")
text(PX + 30, PY + 200, "5 V in through the 5V/GND holes", 13, "normal", "start", "#555")
text(PX + 30, PY + 218, "skips the Pi's input fuse: check", 13, "normal", "start", "#555")
text(PX + 30, PY + 236, "the converter reads 5.1 V first.", 13, "normal", "start", "#555")
text(PX + 30, PY + 260, "(Or power it by USB for the demo.)", 13, "normal", "start", "#777", True)
# RC signals
wire([(PX + PW + 7, P18), (RC["RC1"], P18), (RC["RC1"], MY + MH + 7)], SIG, 3)
wire([(PX + PW + 7, P19), (RC["RC2"], P19), (RC["RC2"], MY + MH + 7)], SIG, 3)
wire([(PX + PW + 7, PG2), (RC["GND"], PG2), (RC["GND"], MY + MH + 7)], BLK, 3)
tag(RC["RC1"] - 8, 790, "22 AWG", SIG, "end")
text(1660, P18 - 8, "throttle", 13, "normal", "start", SIG)
text(1660, P19 - 8, "steering", 13, "normal", "start", SIG)
text(1700, PG2 - 8, "common ground: required", 13, "bold", "start", RED)

# MPU-6050
IX, IY = 1990, 1160
box(IX, IY, 250, 150, "#e6f6f4", I2C, 2.5)
text(IX + 125, IY + 30, "MPU-6050 (GY-521)", 16, "bold", "middle")
text(IX + 125, IY + 52, "tilt guard, I2C 0x68", 13, "normal", "middle", "#555")
text(IX + 125, IY + 72, "screw flat + tight to chassis", 13, "normal", "middle", "#555")
for j, lbl in enumerate(("VCC", "GND", "SDA", "SCL")):
    term(IX, IY + 95 + j * 0 + 0, "", "right") if False else None
IP = {"VCC": IY + 92, "GND": IY + 108, "SDA": IY + 124, "SCL": IY + 140}
for lbl, y in IP.items():
    add(f'<rect x="{IX - 6}" y="{y - 6}" width="12" height="12" fill="#f2c94c" stroke="#7a5d00"/>')
    text(IX + 12, y + 5, lbl, 12, "bold")
wire([(PX + PW + 7, P33), (1590, P33), (1590, IP["VCC"]), (IX - 6, IP["VCC"])], RED, 2.5)
wire([(PX + PW + 7, PG3), (1575, PG3), (1575, IP["GND"]), (IX - 6, IP["GND"])], BLK, 2.5)
wire([(PX + PW + 7, PSDA), (1560, PSDA), (1560, IP["SDA"]), (IX - 6, IP["SDA"])], I2C, 2.5)
wire([(PX + PW + 7, PSCL), (1545, PSCL), (1545, IP["SCL"]), (IX - 6, IP["SCL"])], I2C, 2.5)
tag(1700, IP["VCC"] - 8, "3.3 V", RED)

# planned: HX711 + load cell, E-stop sense
HX, HY = 1990, 1330
box(HX, HY, 250, 120, "#f7f7f7", GRY, 2, 8, "10,6")
text(HX + 125, HY + 28, "HX711 + load cell (planned)", 15, "bold", "middle", "#777")
text(HX + 125, HY + 50, "DT → GPIO16, SCK → GPIO20", 13, "normal", "middle", "#777")
text(HX + 125, HY + 68, "VCC → 3V3, GND → GND", 13, "normal", "middle", "#777")
text(HX + 125, HY + 90, "cell: E+ E− A+ A− on the HX711", 13, "normal", "middle", "#777")
wire([(PX + PW + 7, P16), (1610, P16), (1610, HY + 45), (HX, HY + 45)], GRY, 2.5, "8,6")
wire([(PX + PW + 7, P20), (1625, P20), (1625, HY + 65), (HX, HY + 65)], GRY, 2.5, "8,6")
wire([(PX + PW + 7, P27), (1640, P27), (1640, P27)], GRY, 2.5, "8,6")
text(1650, P27 + 5, "← E-stop NO contact (later)", 13, "normal", "start", GRY)

# ============================================================================== SOIL SENSOR
UX, UY = 560, 1040
box(UX, UY, 280, 140, "#f2f2f8", "#3d3d7a", 2)
text(UX + 140, UY + 30, "USB–RS485 adapter", 16, "bold", "middle")
text(UX + 140, UY + 52, "FTDI FT232R", 13, "normal", "middle", "#555")
for lbl, y in (("A", UY + 82), ("B", UY + 104), ("GND", UY + 126)):
    add(f'<rect x="{UX - 6}" y="{y - 6}" width="12" height="12" fill="#f2c94c" stroke="#7a5d00"/>')
    text(UX + 12, y + 5, lbl, 12, "bold")
wire([(UX + 280, UY + 70), (PX, UY + 70)], USB, 5)
text((UX + 280 + PX) / 2, UY + 60, "USB", 13, "bold", "middle", USB)

SX, SY = 80, 1000
box(SX, SY, 300, 230, "#f4ede2", "#7a5a2e", 2.5)
text(SX + 150, SY + 30, "Soil sensor SEN0604", 17, "bold", "middle")
text(SX + 150, SY + 52, "RS485 4-in-1, DC 5–30 V", 13, "normal", "middle", "#555")
text(SX + 150, SY + 70, "in probe holder v2, on the actuator", 12, "normal", "middle", "#777", True)
SW = {"brown VCC": SY + 110, "black GND": SY + 140, "yellow 485-A": SY + 170, "blue 485-B": SY + 200}
SWC = {"brown VCC": "#8b5a2b", "black GND": BLK, "yellow 485-A": "#d4b000", "blue 485-B": "#1f6fd1"}
for lbl, y in SW.items():
    add(f'<circle cx="{SX + 300}" cy="{y}" r="6" fill="{SWC[lbl]}"/>')
    text(SX + 288, y + 5, lbl, 13, "bold", "end")
wire([(SX + 306, SW["yellow 485-A"]), (470, SW["yellow 485-A"]), (470, UY + 82), (UX - 6, UY + 82)], "#d4b000", 3)
wire([(SX + 306, SW["blue 485-B"]), (490, SW["blue 485-B"]), (490, UY + 104), (UX - 6, UY + 104)], "#1f6fd1", 3)
wire([(SX + 306, SW["black GND"]), (450, SW["black GND"]), (450, UY + 126), (UX - 6, UY + 126)], BLK, 2.5)
# power from F4 and the − bus
wire([(FBX + FBW, FY[4]), (1180, FY[4]), (1180, 900), (420, 900), (420, SW["brown VCC"]), (SX + 306, SW["brown VCC"])],
     "#8b5a2b", 3)
tag(700, 890, "F4 → sensor VCC (12 V), 20 AWG", "#8b5a2b")
wire([(450, SW["black GND"]), (450, 960)], BLK, 2.5)
gnd(450, 960, "− bus")
text(SX, SY + 260, "A/B swapped = no replies (not damage): swap them and retry.", 13, "normal", "start", "#555")
text(SX, SY + 278, "Cable moves with the probe: leave a slack loop, anchor both ends.", 13, "normal", "start", "#555")

# solar (planned)
box(50, 560, 360, 170, "#f7f7f7", GRY, 2, 8, "10,6")
text(230, 592, "Solar (next semester)", 16, "bold", "middle", "#777")
text(230, 618, "30 W panel → Renogy Wanderer 10 A", 13, "normal", "middle", "#777")
text(230, 638, "PV in; BATTERY out → battery terminals", 13, "normal", "middle", "#777")
text(230, 658, "through its own fuse. Set battery type", 13, "normal", "middle", "#777")
text(230, 678, "to LI (lithium).", 13, "normal", "middle", "#777")
text(230, 708, "Spare INA219 here measures charging.", 12, "normal", "middle", "#999", True)

# ============================================================================== KEY + NOTES
KY = 1500
box(50, KY - 30, 520, 190)
text(70, KY, "Wire key", 18, "bold")
keys = [(RED, 7, "14 AWG battery + / motor power"), (BLK, 7, "14 AWG ground"), (MOT, 3.5, "18 AWG motor / actuator leads"),
        (EST, 3.5, "18 AWG E-stop loop"), (SIG, 3, "22 AWG RC signals (3.3 V)"), (I2C, 2.5, "I2C to the MPU-6050"),
        (GRY, 2.5, "planned, dashed")]
for i, (c, wdt, lbl) in enumerate(keys):
    y = KY + 24 + i * 20
    wire([(72, y), (142, y)], c, wdt, "8,6" if c == GRY else None)
    text(158, y + 5, lbl, 14)
box(600, KY - 30, 1760, 190)
text(620, KY, "Build and power-up notes", 18, "bold")
notes = [
    "1. Each ground symbol is its own wire to the fuse block's − bus; only the − bus wire goes to the battery −. Ring terminals on studs, ferrules in screw terminals.",
    "2. E-stop: pressing it opens the relay coil loop, so the MDDRC10 loses motor power. The Pi, radio and sensor stay on (F3, F4) to report the stop.",
    "3. Relay harnesses often have a coil diode: 86 = +, 85 = ground. Check the listing's diagram.",
    "4. First power-up: wheels off the ground, E-stop pressed, start rover.py (it sends 'stop' pulses), then switch on. The MDDRC10 learns 'stop' at power-up.",
    "5. MIX mode for the demo (the code mixes throttle and steering). The FDR's rev A drawing used INDEPENDENT mode with the Arduino; this one replaces it.",
    "6. Check with i2cdetect -y 1: 3c (OLED) and 68 (MPU-6050). Turn on I2C in raspi-config.",
    "7. Battery: charge LiFePO4 at 14.4 V; unplug the XT60 to charge on the bench.",
]
for i, n in enumerate(notes):
    text(620, KY + 28 + i * 21, n, 14)
text(50, H - 16, "D.I.R.T.T. rover wiring, demo configuration. Generated by code/Demo/wiring/make_rover_wiring.py. "
                 "Fuse and wire sizes from the FDR drivetrain wiring (rev A).", 13, "normal", "start", "#777", True)

add("</svg>")
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rover_wiring.svg")
open(path, "w").write("\n".join(out))
print(path)
