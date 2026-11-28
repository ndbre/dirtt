"""
link.py - the D.I.R.T.T. demo radio link, shared by rover.py and base.py. Copy it to both Pis.

Message types 1-4 and the first five STATUS bytes are the same as the team's original
bot.py / rover.py, so an older base still reads the heartbeat reply.

Who talks when: the base is in charge of the channel. The rover only transmits right after a
base heartbeat (its STATUS, then up to two soil lines). While the operator is driving, the base
stops sending heartbeats and sends DRIVE packets five times a second instead, so the rover never
transmits over them. LoRa is half duplex: two radios talking at once both lose.

--sim: UdpRadio stands in for the LoRa Bonnet over UDP on this computer, with the same
send / send_with_ack / receive behaviour as adafruit_rfm9x (including dropping other packets
while waiting for an ACK), so both programs can be tested without radios.
"""
import random
import select
import socket
import struct
import time

RADIO_FREQ_MHZ = 915.0
BASE_NODE = 1
ROVER_NODE = 2
BROADCAST = 0xFF
TX_POWER = 23
ACK_DELAY = 0.1        # pause before sending an ACK, so the sender has switched to receive

# ---- message types (first byte of every packet) ----
MSG_HEARTBEAT = 1   # base -> rover   <BB   type, seq                       (with ACK)
MSG_CMD       = 2   # base -> rover   <BBB  type, seq, command, + arguments (with ACK)
MSG_STATUS    = 3   # rover -> base   STATUS_FMT                            (with ACK)
MSG_DATA      = 4   # rover -> base   <BI   type, line number, + one CSV line (with ACK)
MSG_DRIVE     = 5   # base -> rover   <Bbb  type, throttle %, steering %    (broadcast, no ACK)

# ---- commands (third byte of MSG_CMD) ----
CMD_STOP        = 0   # stop everything now (motors and actuator)
CMD_RETURN_HOME = 1   # from the original code; the demo rover treats it as STOP
CMD_MODE        = 2   # + <B mode
CMD_PROBE       = 3   # + <Hhh probe id, grid x, grid y
CMD_ACT         = 4   # + <bB  direction (+1 extend / -1 retract), run time in tenths of a second

MODE_DRIVE = 0      # drive motors on the MDDRC10
MODE_PROBE = 1      # linear actuator on the MDDRC10 instead of the motors
MODE_NAMES = {MODE_DRIVE: "DRIVE", MODE_PROBE: "PROBE"}

STATE_IDLE      = 0
STATE_PROBING   = 1
STATE_RETURNING = 2   # original code's value, kept so the numbers don't clash
STATE_JOGGING   = 3
STATE_NAMES = {0: "idle", 1: "probing", 2: "returning", 3: "moving actuator"}

PHASE_NONE, PHASE_EXTENDING, PHASE_READING, PHASE_RETRACTING = 0, 1, 2, 3
PHASE_NAMES = {0: "", 1: "probe going down", 2: "reading soil", 3: "probe coming up"}

# events the rover reports back in STATUS (the last thing that happened)
EV_NONE, EV_PROBE_STARTED, EV_PROBE_SAVED, EV_PROBE_FAILED = 0, 1, 2, 3
EV_WRONG_MODE, EV_BUSY, EV_STOPPED, EV_MODE_CHANGED, EV_LINK_LOST, EV_JOG = 4, 5, 6, 7, 8, 9
EV_PROBE_BLOCKED, EV_NO_TILT = 10, 11
EVENT_NAMES = {
    0: "", 1: "probe started", 2: "probe saved", 3: "probe failed: no good sensor readings",
    4: "refused: wrong mode", 5: "refused: busy", 6: "stopped", 7: "mode changed",
    8: "link was lost", 9: "actuator moved",
    10: "probe stopped: rover started to tip (hit something hard); probe raised",
    11: "refused: tilt sensor not working",
}

# type, seq, battery % (255 = unknown), state, rssi | mode, phase, event, event probe id, lines waiting
STATUS_FMT = "<BBBBbBBBHH"
BATTERY_UNKNOWN = 255


def pack_heartbeat(seq):
    return struct.pack("<BB", MSG_HEARTBEAT, seq & 0xFF)


def pack_cmd(seq, cmd, args=b""):
    return struct.pack("<BBB", MSG_CMD, seq & 0xFF, cmd) + args


def pack_drive(throttle, steering):
    return struct.pack("<Bbb", MSG_DRIVE, clamp(throttle, -100, 100), clamp(steering, -100, 100))


def pack_status(seq, battery, state, rssi, mode, phase, event, event_id, pending):
    return struct.pack(STATUS_FMT, MSG_STATUS, seq & 0xFF, battery, state, clamp_rssi(rssi),
                       mode, phase, event, event_id & 0xFFFF, min(pending, 0xFFFF))


def unpack_status(p):
    if len(p) < struct.calcsize(STATUS_FMT):
        return None
    f = struct.unpack(STATUS_FMT, p[:struct.calcsize(STATUS_FMT)])
    keys = ("type", "seq", "battery", "state", "rssi", "mode", "phase", "event", "event_id", "pending")
    return dict(zip(keys, f))


def pack_data(index, line):
    return struct.pack("<BI", MSG_DATA, index) + line.encode("utf-8")


def unpack_data(p):
    if len(p) < 5:
        return None
    (index,) = struct.unpack("<I", p[1:5])
    return index, p[5:].decode("utf-8", errors="replace")


def clamp(v, lo, hi):
    return int(max(lo, min(hi, round(v))))


def clamp_rssi(r):
    return -128 if r is None else clamp(r, -128, 127)


# ---------------------------------------------------------------------------------------------
# Reliable send that keeps listening
# ---------------------------------------------------------------------------------------------
FLAG_ACK, FLAG_RETRY = 0x80, 0x40


def reliable_send(radio, data, on_packet, retries=5, ack_wait=0.5):
    """Send with ACK and retries, like radio.send_with_ack(), but while it waits for the ACK it
    still ACKs and hands over anything the other side sends (on_packet(payload)).

    adafruit_rfm9x's send_with_ack() throws away every other packet while it waits. If the base
    sends a command just as the rover answers a heartbeat, each side then ignores the other and
    both give up after ~4 s. That's how a STOP went missing in testing. on_packet must not send.
    """
    radio.identifier = (radio.identifier + 1) & 0xFF
    ident = radio.identifier
    flags = 0
    for _ in range(retries):
        radio.send(data, keep_listening=True, identifier=ident, flags=flags)
        end = time.monotonic() + ack_wait
        while True:
            left = end - time.monotonic()
            if left <= 0:
                break
            p = radio.receive(with_header=True, with_ack=True, timeout=left)
            if p is None or len(p) < 4:
                continue
            if p[3] & FLAG_ACK:
                if p[2] == ident:
                    return True
                continue
            on_packet(p[4:])
        flags |= FLAG_RETRY
        time.sleep(ack_wait * random.random())   # random back-off, so two radios don't re-collide
    return False


# ---------------------------------------------------------------------------------------------
# Radio setup
# ---------------------------------------------------------------------------------------------
def make_radio(node, sim=False, sim_loss=0.0):
    """Return (radio, display). display is the Bonnet's OLED, or None."""
    if sim:
        r = UdpRadio(node, loss=sim_loss)
    else:
        import board
        import busio
        import digitalio
        import adafruit_rfm9x
        cs = digitalio.DigitalInOut(board.CE1)
        reset = digitalio.DigitalInOut(board.D25)
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        r = adafruit_rfm9x.RFM9x(spi, cs, reset, RADIO_FREQ_MHZ)
        r.tx_power = TX_POWER
        # r.spreading_factor = 9   # if you change it, change it on both Pis
    r.node = node
    r.destination = ROVER_NODE if node == BASE_NODE else BASE_NODE
    r.ack_delay = ACK_DELAY
    display = None if sim else make_display()
    return r, display


def make_display():
    try:
        import board
        import busio
        import digitalio
        import adafruit_ssd1306
        i2c = busio.I2C(board.SCL, board.SDA)
        return adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, reset=digitalio.DigitalInOut(board.D4))
    except Exception as e:
        print("OLED not available:", e)
        return None


def show(display, font, *lines):
    """Up to three lines on the Bonnet's OLED. Never lets a display error stop the program."""
    if display is None:
        return
    try:
        display.fill(0)
        for i, text in enumerate(lines[:3]):
            display.text(str(text)[:21], 0, 11 * i, 1, font_name=font)
        display.show()
    except Exception:
        pass


# ---------------------------------------------------------------------------------------------
# Simulated radio for testing on one computer (--sim)
# ---------------------------------------------------------------------------------------------
class UdpRadio:
    """Behaves like adafruit_rfm9x.RFM9x's reliable-datagram calls, over UDP on localhost."""
    PORT0 = 47100

    def __init__(self, node, loss=0.0):
        self.node = node
        self.destination = BROADCAST
        self.loss = loss
        self.identifier = 0
        self.ack_wait = 0.5
        self.ack_retries = 5
        self.ack_delay = None
        self.last_rssi = None
        self.seen_ids = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", self.PORT0 + node))

    def _tx(self, dest, ident, flags, payload):
        time.sleep(0.03 + 0.002 * len(payload))         # roughly LoRa SF7 airtime
        if random.random() < self.loss:
            return
        pkt = bytes([dest, self.node, ident & 0xFF, flags & 0xFF]) + bytes(payload)
        for n in ((BASE_NODE, ROVER_NODE) if dest == BROADCAST else (dest,)):
            if n != self.node:
                self.sock.sendto(pkt, ("127.0.0.1", self.PORT0 + n))

    def send(self, data, *, keep_listening=True, destination=None, node=None, identifier=None,
             flags=None):
        self._tx(self.destination if destination is None else destination,
                 self.identifier if identifier is None else identifier,
                 0 if flags is None else flags, data)
        return True

    def receive(self, *, keep_listening=True, with_header=False, with_ack=False, timeout=None):
        timeout = 0.5 if timeout is None else timeout
        ready, _, _ = select.select([self.sock], [], [], max(0.0, timeout))
        if not ready:
            return None
        pkt, _ = self.sock.recvfrom(512)
        if len(pkt) < 5:
            return None
        self.last_rssi = -62 + random.randint(-4, 4)
        dest, src, ident, flags = pkt[:4]
        if dest not in (self.node, BROADCAST):
            return None
        if with_ack and not flags & FLAG_ACK and dest != BROADCAST:
            if self.ack_delay:
                time.sleep(self.ack_delay)
            self._tx(src, ident, flags | FLAG_ACK, b"!")
            if self.seen_ids.get(src) == ident and flags & FLAG_RETRY:
                return None                       # a retry we already have
            self.seen_ids[src] = ident
        return pkt if with_header else pkt[4:]

    def send_with_ack(self, data):
        self.identifier = (self.identifier + 1) & 0xFF
        flags = 0
        for _ in range(self.ack_retries):
            self.send(data, flags=flags)
            end = time.monotonic() + self.ack_wait
            while time.monotonic() < end:
                p = self.receive(timeout=end - time.monotonic(), with_header=True)
                if p and p[3] & FLAG_ACK and p[2] == self.identifier:
                    return True
            flags |= FLAG_RETRY
            time.sleep(self.ack_wait * random.random())
        return False
