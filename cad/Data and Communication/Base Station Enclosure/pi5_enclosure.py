"""
D.I.R.T.T. base station enclosure: Raspberry Pi 5 + Adafruit LoRa Radio Bonnet with OLED (RFM95W).

Parts (print each once unless noted):
  base    - tray the Pi screws into. Print floor-down.
  lid     - shell with port openings, OLED window, 3 flex buttons, SMA antenna hole, vents.
            Print upside down (top face on the bed).
  spacer  - 11 mm spacer between Pi and bonnet at the two GPIO-side holes. Print 2.

Hardware: 6 x M2.5 x 16 mm pan-head screws (self-tap into 2.2 mm printed holes),
          1 x uFL -> SMA female bulkhead pigtail + 915 MHz SMA antenna.

Screws, all from underneath:
  2 front Pi holes  : base -> Pi -> lid post         (holds Pi and lid front)
  2 GPIO-side holes : base -> Pi -> printed spacer   (bonnet sits on the spacers)
  2 back corners    : base -> lid corner column      (holds lid back)

Coordinates: Pi 5 board, origin at the board's lower-left corner (USB-C / HDMI edge is y=0,
GPIO edge is y=56, USB/Ethernet edge is x=85), z=0 at the bottom of the enclosure.
Dimensions from the Raspberry Pi 5 datasheet (repo: datasheets/Data and Communication) and
Adafruit's bonnet board file (github.com/adafruit/Adafruit-Radio-Bonnet-PCB).
"""
import os
import cadquery as cq

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- stack heights (z)
FLOOR = 2.0
STANDOFF_H = 3.5
PCB_BOT = FLOOR + STANDOFF_H          # 5.5
PCB_TOP = PCB_BOT + 1.4               # 6.9
SPLIT = 6.5                           # base / lid joint
BONNET_GAP = 11.0                     # Pi PCB top -> bonnet PCB bottom (2.5 header base + 8.5 socket)
BON_BOT = PCB_TOP + BONNET_GAP        # 17.9
BON_TOP = BON_BOT + 1.6               # 19.5
BUTTON_H = 2.5                        # EVQ-Q2 tact switch height above bonnet (measure yours!)
CEIL = 25.0                           # lid inside ceiling
TOP = 2.0
H = CEIL + TOP                        # 27.0 overall height

# ---------------------------------------------------------------- footprint (x, y)
CAV = (-1.0, 86.0, -1.0, 57.5)        # inside cavity
OUTER = (-4.0, 88.5, -3.5, 60.5)      # outside
R_OUT = 3.0

PI_HOLES_FRONT = [(3.5, 3.5), (61.5, 3.5)]
PI_HOLES_GPIO = [(3.5, 52.5), (61.5, 52.5)]
BACK_COLS = [(-1.3, 57.9), (86.0, 57.6)]

# Bonnet sits on the GPIO header: bonnet (bx, by) -> Pi (bx, by + 26)
BON_DY = 26.0
def bon(x, y):
    return (x, y + BON_DY)

BONNET_HOLES = [bon(3.5, 3.5), bon(61.5, 3.5), bon(3.5, 26.5), bon(61.5, 26.5)]
BUTTONS = [bon(36.449, 3.175), bon(45.085, 3.175), bon(53.848, 3.175)]
OLED_ACTIVE = (62.738 - 27.9, 62.738 - 5.516, 12.7 - 2.109 + BON_DY, 12.7 + 3.475 + BON_DY)
UFL = bon(2.2, 15.24)

SMA_XY = (6.5, 15.0)
SMA_HOLE = 6.6

PILOT = 2.2       # M2.5 self-tapping into PLA/PETG
CLEAR = 2.9
CB_D, CB_DEPTH = 5.6, 1.8


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def cyl(x, y, z0, z1, d):
    return cq.Workplane("XY").circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def rounded_box(x0, x1, y0, y1, z0, z1, r):
    return box(x0, x1, y0, y1, z0, z1).edges("|Z").fillet(r)


def slot_xz(xc, w, z0, z1, y0, y1, r=None):
    """Opening through a wall facing +/-y: width w centred on xc, from z0 to z1."""
    b = box(xc - w / 2, xc + w / 2, y0, y1, z0, z1)
    return b.edges("|Y").fillet(r) if r else b


def slot_yz(yc, w, z0, z1, x0, x1, r=None):
    b = box(x0, x1, yc - w / 2, yc + w / 2, z0, z1)
    return b.edges("|X").fillet(r) if r else b


# ---------------------------------------------------------------- port openings
# front wall (y = OUTER[2]..CAV[2]): plug overmolds need room, so these dip into the base wall
FRONT_PORTS = [  # (x centre, width, z0, z1)
    (11.2, 12.0, PCB_TOP - 2.0, PCB_TOP + 5.6),    # USB-C power
    (25.8, 12.0, PCB_TOP - 2.2, PCB_TOP + 5.8),    # micro-HDMI 0
    (39.2, 12.0, PCB_TOP - 2.2, PCB_TOP + 5.8),    # micro-HDMI 1
]
# right wall (x = CAV[1]..OUTER[1]): receptacles poke through the wall
RIGHT_PORTS = [  # (y centre, width, z1)
    (10.2, 17.0, PCB_TOP + 14.3),   # Ethernet
    (29.1, 15.4, PCB_TOP + 16.8),   # USB 3
    (47.0, 15.4, PCB_TOP + 16.8),   # USB 2
]
POWER_BTN = (12.3, 19.5, SPLIT, PCB_TOP + 4.0)   # left wall, y0, y1, z0, z1
SD_NOTCH = (20.0, 36.0, FLOOR + 0.5, SPLIT)      # left wall, base only


def make_base():
    x0, x1, y0, y1 = OUTER
    b = rounded_box(x0, x1, y0, y1, 0, SPLIT, R_OUT)
    b = b.cut(box(CAV[0], CAV[1], CAV[2], CAV[3], FLOOR, SPLIT + 1))

    # Pi standoffs (all four) and back-corner bosses
    for (x, y) in PI_HOLES_FRONT + PI_HOLES_GPIO:
        b = b.union(cyl(x, y, FLOOR - 0.01, PCB_BOT, 6.0))
    for (x, y) in BACK_COLS:
        b = b.union(cyl(x, y, FLOOR - 0.01, SPLIT, 5.0))
    b = b.intersect(rounded_box(x0, x1, y0, y1, 0, SPLIT, R_OUT))

    # screw holes + counterbores from below
    for (x, y) in PI_HOLES_FRONT + PI_HOLES_GPIO + BACK_COLS:
        b = b.cut(cyl(x, y, -1, SPLIT + 1, CLEAR))
        b = b.cut(cyl(x, y, -1, CB_DEPTH, CB_D))

    # floor vents under the SoC
    for i in range(10):
        xc = 20.0 + 4.0 * i
        b = b.cut(box(xc - 1.0, xc + 1.0, 12.0, 40.0, -1, FLOOR + 1).edges("|Z").fillet(0.99))

    # front port dips, microSD notch
    for (xc, w, z0, z1) in FRONT_PORTS:
        b = b.cut(slot_xz(xc, w, z0, SPLIT + 1, y0 - 1, CAV[2] + 0.5))
    sy0, sy1, sz0, sz1 = SD_NOTCH
    b = b.cut(box(x0 - 1, CAV[0] + 0.5, sy0, sy1, sz0, SPLIT + 1))
    return b


def make_lid():
    x0, x1, y0, y1 = OUTER
    l = rounded_box(x0, x1, y0, y1, SPLIT, H, R_OUT)
    l = l.cut(box(CAV[0], CAV[1], CAV[2], CAV[3], SPLIT - 1, CEIL))

    # front posts (clamp Pi front holes), back corner columns, bonnet hold-down pegs
    for (x, y) in PI_HOLES_FRONT:
        l = l.union(cyl(x, y, PCB_TOP, CEIL + 0.01, 5.5))
    for (x, y) in BACK_COLS:
        l = l.union(cyl(x, y, SPLIT, CEIL + 0.01, 5.0))
    for (x, y) in BONNET_HOLES:
        l = l.union(cyl(x, y, BON_TOP + 0.3, CEIL + 0.01, 4.5))
    # thicker pad under the SMA bulkhead (panel = 3.5 mm)
    l = l.union(cyl(SMA_XY[0], SMA_XY[1], CEIL - 1.5, CEIL + 0.01, 13.0))
    l = l.intersect(rounded_box(x0, x1, y0, y1, SPLIT, H, R_OUT))

    for (x, y) in PI_HOLES_FRONT:
        l = l.cut(cyl(x, y, PCB_TOP - 1, PCB_TOP + 14.0, PILOT))
    for (x, y) in BACK_COLS:
        l = l.cut(cyl(x, y, SPLIT - 1, SPLIT + 14.0, PILOT))

    # SMA antenna hole
    l = l.cut(cyl(SMA_XY[0], SMA_XY[1], CEIL - 3, H + 1, SMA_HOLE))

    # OLED window (active area + 1 mm), chamfered outward
    ax0, ax1, ay0, ay1 = OLED_ACTIVE
    m = 1.0
    l = l.cut(box(ax0 - m, ax1 + m, ay0 - m, ay1 + m, CEIL - 1, H + 1))
    c = 1.2
    chamfer = (cq.Workplane("XY").workplane(offset=H - c)
               .rect(ax1 - ax0 + 2 * m, ay1 - ay0 + 2 * m)
               .workplane(offset=c + 0.01)
               .rect(ax1 - ax0 + 2 * m + 2 * c, ay1 - ay0 + 2 * m + 2 * c)
               .loft().translate(((ax0 + ax1) / 2, (ay0 + ay1) / 2, 0)))
    l = l.cut(chamfer)

    # flex buttons: U-slot tab (hinge toward the front), thinned to 1.2 mm, nub underneath
    TAB_W, SLOT, TAB_T = 6.0, 0.8, 1.2
    nub_bot = BON_TOP + BUTTON_H + 0.6
    for (bx, by) in BUTTONS:
        ty0, ty1 = by - 8.7, by + 2.3
        u = (box(bx - TAB_W / 2 - SLOT, bx + TAB_W / 2 + SLOT, ty0, ty1 + SLOT, CEIL - 1, H + 1)
             .cut(box(bx - TAB_W / 2, bx + TAB_W / 2, ty0 - 1, ty1, CEIL - 2, H + 2)))
        l = l.cut(u)
        l = l.cut(box(bx - TAB_W / 2 - 0.01, bx + TAB_W / 2 + 0.01, ty0, ty1, CEIL - 1, H - TAB_T))
        l = l.union(cyl(bx, by, nub_bot, H - TAB_T + 0.01, 3.0))

    # top vents
    for i in range(10):
        xc = 18.0 + 4.0 * i
        l = l.cut(box(xc - 1.0, xc + 1.0, 4.0, 18.0, CEIL - 1, H + 1).edges("|Z").fillet(0.99))
    # back-wall vents (air past the GPIO header / under the bonnet)
    for i in range(13):
        xc = 10.0 + 4.0 * i
        l = l.cut(box(xc - 1.0, xc + 1.0, CAV[3] - 1, y1 + 1, 9.5, 16.5))

    # port openings
    for (xc, w, z0, z1) in FRONT_PORTS:
        l = l.cut(slot_xz(xc, w, z0, z1, y0 - 1, CAV[2] + 0.5, r=1.5))
    for (yc, w, z1) in RIGHT_PORTS:
        l = l.cut(slot_yz(yc, w, SPLIT - 2, z1, CAV[1] - 0.5, x1 + 1, r=1.0))
    py0, py1, pz0, pz1 = POWER_BTN
    l = l.cut(box(x0 - 1, CAV[0] + 0.5, py0, py1, SPLIT - 1, pz1))

    # engraved label
    try:
        txt = (cq.Workplane("XY").workplane(offset=H - 0.6)
               .text("D.I.R.T.T. BASE", 4.5, 1.0, combine=False, halign="center", valign="center")
               .translate((32.5, 50.5, 0)))
        l = l.cut(txt)
    except Exception as e:  # font missing: skip the label
        print("label skipped:", e)
    return l


def make_spacer():
    return cyl(0, 0, 0, BONNET_GAP, 5.0).cut(cyl(0, 0, -1, BONNET_GAP + 1, PILOT))


# ---------------------------------------------------------------- reference boards (for checks/renders)
def make_boards():
    parts = {}
    pcb = rounded_box(0, 85, 0, 56, PCB_BOT, PCB_TOP, 3.0)
    for (x, y) in PI_HOLES_FRONT + PI_HOLES_GPIO:
        pcb = pcb.cut(cyl(x, y, 0, 10, 2.7))
    parts["pi_pcb"] = pcb
    ports = (box(66.5, 88.0, 10.2 - 7.95, 10.2 + 7.95, PCB_TOP, PCB_TOP + 13.5)
             .union(box(70.7, 88.0, 29.1 - 7.3, 29.1 + 7.3, PCB_TOP, PCB_TOP + 16.0))
             .union(box(70.7, 88.0, 47.0 - 7.3, 47.0 + 7.3, PCB_TOP, PCB_TOP + 16.0))
             .union(box(11.2 - 4.5, 11.2 + 4.5, -0.5, 7.0, PCB_TOP, PCB_TOP + 3.2))
             .union(box(25.8 - 3.75, 25.8 + 3.75, -0.5, 7.0, PCB_TOP, PCB_TOP + 3.4))
             .union(box(39.2 - 3.75, 39.2 + 3.75, -0.5, 7.0, PCB_TOP, PCB_TOP + 3.4))
             .union(box(-0.5, 2.5, 13.3, 18.4, PCB_TOP, PCB_TOP + 2.5))          # power button
             .union(box(-2.0, 12.0, 22.5, 33.5, PCB_BOT - 1.4, PCB_BOT))          # microSD card
             .union(box(7.1, 57.9, 50.0, 55.0, PCB_TOP, PCB_TOP + 2.5))           # GPIO header base
             .union(box(20.0, 45.0, 14.0, 34.0, PCB_TOP, PCB_TOP + 2.5)))         # SoC / RAM
    parts["pi_parts"] = ports
    bon_pcb = rounded_box(0, 65, BON_DY, BON_DY + 30.66, BON_BOT, BON_TOP, 3.0)
    for (x, y) in BONNET_HOLES:
        bon_pcb = bon_pcb.cut(cyl(x, y, 0, 30, 2.8))
    parts["bonnet_pcb"] = bon_pcb
    parts["bonnet_header"] = box(7.1, 57.9, 50.0, 55.0, PCB_TOP + 2.5, BON_BOT)
    oled = box(32.738, 62.738, 12.7 - 5.75 + BON_DY, 12.7 + 5.575 + BON_DY, BON_TOP, BON_TOP + 1.45)
    parts["oled"] = oled
    ax0, ax1, ay0, ay1 = OLED_ACTIVE
    parts["oled_active"] = box(ax0, ax1, ay0, ay1, BON_TOP + 1.45, BON_TOP + 1.5)
    btns = None
    for (x, y) in BUTTONS:
        s = box(x - 3.3, x + 3.3, y - 3.0, y + 3.0, BON_TOP, BON_TOP + BUTTON_H - 0.6).union(
            cyl(x, y, BON_TOP, BON_TOP + BUTTON_H, 3.0))
        btns = s if btns is None else btns.union(s)
    parts["buttons"] = btns
    parts["radio"] = box(17.78 - 8, 17.78 + 8, bon(0, 8.382)[1] - 8, bon(0, 8.382)[1] + 8, BON_TOP, BON_TOP + 2.0)
    sma = (cyl(SMA_XY[0], SMA_XY[1], CEIL - 1.5 - 6.0, CEIL - 1.5, 9.2)                 # body + nut inside
           .union(cyl(SMA_XY[0], SMA_XY[1], CEIL - 1.5, H + 4.0, 6.3)))                 # thread
    parts["sma"] = sma
    parts["spacers"] = cyl(*PI_HOLES_GPIO[0], PCB_TOP, BON_BOT, 5.0).union(cyl(*PI_HOLES_GPIO[1], PCB_TOP, BON_BOT, 5.0))
    return parts


if __name__ == "__main__":
    base, lid, spacer = make_base(), make_lid(), make_spacer()
    for name, shape in [("base", base), ("lid", lid), ("spacer", spacer)]:
        cq.exporters.export(shape, os.path.join(OUT, f"DIRTT_pi5_enclosure_{name}.step"))
        cq.exporters.export(shape, os.path.join(OUT, f"DIRTT_pi5_enclosure_{name}.stl"), tolerance=0.02, angularTolerance=0.1)
    # lid STL flipped for printing (top face on the bed)
    flipped = lid.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, H))
    cq.exporters.export(flipped, os.path.join(OUT, "DIRTT_pi5_enclosure_lid_print_orientation.stl"), tolerance=0.02, angularTolerance=0.1)
    print("outer size", OUTER[1] - OUTER[0], "x", OUTER[3] - OUTER[2], "x", H, "mm")
