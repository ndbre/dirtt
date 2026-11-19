/*
  D.I.R.T.T. drivetrain motor test
  Arduino (Uno / Nano / Mega) -> Cytron MDDRC10 RC inputs -> 4x FIT0185 gearmotors

  The MDDRC10 expects R/C servo pulses (like an RC receiver), so the Arduino sends them with
  the Servo library: 1500 us = stop, up to +/-435 us either side = full speed (datasheet).

  Wiring (see wiring.png):
    Arduino D9  -> MDDRC10 RC1 signal   (mixed mode: forward/back,  independent: LEFT motors)
    Arduino D10 -> MDDRC10 RC2 signal   (mixed mode: turn left/right, independent: RIGHT motors)
    Arduino GND -> MDDRC10 RC GND
    MDDRC10 RC +5V: leave unconnected (the Arduino is powered by USB)

  Power-up order (the driver captures its "stop" point from the first pulses it sees):
    1. Wheels off the ground.  2. Plug in the Arduino (USB).  3. Open Serial Monitor at 115200,
       line ending "Newline".  4. THEN switch on the 12 V to the driver.

  Commands (type, then Enter):
    w / s       forward / reverse          a / d    pivot left / right
    x  (or q)   stop now                   test     run the automatic test sequence
    speed N     set speed for w/s/a/d, 0-100 %          (default 30)
    time N      seconds a move lasts before it stops itself, 0 = until x  (default 2)
    t T S       raw mixed: throttle T and steering S, -100..100 %
    l N / r N   independent mode only: left / right motors at N %, -100..100
    mode mix    driver switch on MIX (default)   mode ind   driver switch on IND
    ?           status        h   help
*/

#include <Servo.h>

// ---- settings -----------------------------------------------------------------------------
const uint8_t PIN_RC1 = 9;         // MDDRC10 RC1
const uint8_t PIN_RC2 = 10;        // MDDRC10 RC2
const int NEUTRAL_US = 1500;       // stop
const int FULLSCALE_US = 435;      // datasheet: full speed at neutral +/- 435 us
const int RAMP_US_PER_STEP = 8;    // speed changes this much per 20 ms (about 0.5 s to full speed)
const int MAX_PCT = 100;           // lower this to cap the speed while testing

Servo rc1, rc2;
bool mixed = true;                 // must match the MIX/IND switch on the driver
int speedPct = 30;                 // used by w/s/a/d and the test sequence
float moveSeconds = 2.0;           // auto-stop after this long (0 = never)

int target1 = NEUTRAL_US, target2 = NEUTRAL_US;   // where we're heading
int out1 = NEUTRAL_US, out2 = NEUTRAL_US;         // what we're sending (ramped)
unsigned long stopAt = 0;          // millis() at which the current move ends (0 = none)
unsigned long lastRamp = 0;
String line;

// percent (-100..100) -> pulse width
int pctToUs(int pct) {
  pct = constrain(pct, -MAX_PCT, MAX_PCT);
  return NEUTRAL_US + (long)pct * FULLSCALE_US / 100;
}

int usToPct(int us) { return (long)(us - NEUTRAL_US) * 100 / FULLSCALE_US; }

void setTargets(int pct1, int pct2, bool timed) {
  target1 = pctToUs(pct1);
  target2 = pctToUs(pct2);
  stopAt = (timed && moveSeconds > 0 && (pct1 != 0 || pct2 != 0))
             ? millis() + (unsigned long)(moveSeconds * 1000) : 0;
}

void stopNow() {                   // no ramp: straight to neutral
  target1 = target2 = out1 = out2 = NEUTRAL_US;
  rc1.writeMicroseconds(out1);
  rc2.writeMicroseconds(out2);
  stopAt = 0;
}

// move `from` toward `to` by at most `step`
int approach(int from, int to, int step) {
  if (from < to) return min(from + step, to);
  if (from > to) return max(from - step, to);
  return from;
}

void updateOutputs() {
  if (stopAt && (long)(millis() - stopAt) >= 0) {
    target1 = target2 = NEUTRAL_US;
    stopAt = 0;
    Serial.println(F("(time's up: stopping)"));
  }
  if (millis() - lastRamp >= 20) {
    lastRamp = millis();
    out1 = approach(out1, target1, RAMP_US_PER_STEP);
    out2 = approach(out2, target2, RAMP_US_PER_STEP);
    rc1.writeMicroseconds(out1);
    rc2.writeMicroseconds(out2);
  }
}

// wait `ms` while still ramping and listening for a stop
bool waitWatching(unsigned long ms) {
  unsigned long t0 = millis();
  while (millis() - t0 < ms) {
    updateOutputs();
    if (Serial.available()) {      // any key aborts the test
      while (Serial.available()) Serial.read();
      stopNow();
      Serial.println(F("Test aborted. Stopped."));
      return false;
    }
  }
  return true;
}

void printStatus() {
  Serial.print(F("Mode: ")); Serial.print(mixed ? F("MIXED") : F("INDEPENDENT"));
  Serial.print(F(" | speed ")); Serial.print(speedPct); Serial.print(F("%"));
  Serial.print(F(" | move time ")); Serial.print(moveSeconds); Serial.println(F(" s"));
  Serial.print(F("RC1 (D9): ")); Serial.print(out1); Serial.print(F(" us = ")); Serial.print(usToPct(out1));
  Serial.print(F("%   RC2 (D10): ")); Serial.print(out2); Serial.print(F(" us = ")); Serial.print(usToPct(out2));
  Serial.println(F("%"));
}

void printHelp() {
  Serial.println(F("w/s forward/reverse   a/d pivot left/right   x stop   test = automatic sequence"));
  Serial.println(F("speed N (0-100)   time N (s, 0 = until x)   t T S (mixed, -100..100)"));
  Serial.println(F("l N / r N (independent mode)   mode mix | mode ind   ? status   h help"));
}

// one step of the automatic test: describe it, run it, stop, pause
bool step(const __FlashStringHelper *what, int pct1, int pct2, unsigned long ms) {
  Serial.print(F("  ")); Serial.println(what);
  target1 = pctToUs(pct1); target2 = pctToUs(pct2); stopAt = 0;
  if (!waitWatching(ms)) return false;
  target1 = target2 = NEUTRAL_US;
  return waitWatching(1200);       // ramp down + a pause between steps
}

void runTest() {
  int v = speedPct;
  Serial.println(F("Automatic test (press any key + Enter to abort). Watch every wheel:"));
  if (mixed) {
    if (!step(F("1. FORWARD: all 4 wheels should roll forward"), v, 0, 2500)) return;
    if (!step(F("2. REVERSE: all 4 wheels backward"), -v, 0, 2500)) return;
    if (!step(F("3. PIVOT LEFT: left wheels back, right wheels forward"), 0, -v, 2500)) return;
    if (!step(F("4. PIVOT RIGHT: left wheels forward, right wheels back"), 0, v, 2500)) return;
    if (!step(F("5. ARC: forward while turning right"), v, v / 2, 2500)) return;
  } else {
    if (!step(F("1. LEFT motors forward only"), v, 0, 2500)) return;
    if (!step(F("2. LEFT motors reverse only"), -v, 0, 2500)) return;
    if (!step(F("3. RIGHT motors forward only"), 0, v, 2500)) return;
    if (!step(F("4. RIGHT motors reverse only"), 0, -v, 2500)) return;
  }
  Serial.println(F("  6. RAMP: forward 0 -> 100% -> 0 (listen for rough or noisy gearboxes)"));
  for (int p = 0; p <= 100; p += 5) {
    if (mixed) setTargets(p, 0, false); else setTargets(p, p, false);
    if (!waitWatching(150)) return;
  }
  for (int p = 100; p >= 0; p -= 5) {
    if (mixed) setTargets(p, 0, false); else setTargets(p, p, false);
    if (!waitWatching(150)) return;
  }
  stopNow();
  Serial.println(F("Done. If a whole side ran backwards, swap that side's two wires at the driver"));
  Serial.println(F("(MLA<->MLB or MRA<->MRB). If only ONE wheel of a side is wrong, swap that motor's wires."));
}

void handle(String cmd) {
  cmd.trim();
  cmd.toLowerCase();
  if (cmd.length() == 0) return;
  int sp = cmd.indexOf(' ');
  String word = sp < 0 ? cmd : cmd.substring(0, sp);
  String rest = sp < 0 ? "" : cmd.substring(sp + 1);
  rest.trim();

  if (word == "x" || word == "q" || word == "stop") { stopNow(); Serial.println(F("STOP")); return; }
  if (word == "h" || word == "help") { printHelp(); return; }
  if (word == "?") { printStatus(); return; }
  if (word == "test") { runTest(); return; }
  if (word == "speed") { speedPct = constrain(rest.toInt(), 0, MAX_PCT); printStatus(); return; }
  if (word == "time") { moveSeconds = max(0.0, rest.toFloat()); printStatus(); return; }
  if (word == "mode") {
    stopNow();
    mixed = !rest.startsWith("ind");
    Serial.println(mixed ? F("MIXED: set the driver's switch to MIX") : F("INDEPENDENT: set the driver's switch to IND"));
    Serial.println(F("(Flip the switch with the 12 V OFF, then power the driver back on.)"));
    return;
  }

  int v = speedPct;
  if (mixed) {
    if (word == "w") setTargets(v, 0, true);
    else if (word == "s") setTargets(-v, 0, true);
    else if (word == "a") setTargets(0, -v, true);
    else if (word == "d") setTargets(0, v, true);
    else if (word == "t") {
      int sp2 = rest.indexOf(' ');
      int th = rest.toInt(), st = sp2 < 0 ? 0 : rest.substring(sp2 + 1).toInt();
      setTargets(th, st, true);
    }
    else if (word == "l" || word == "r") { Serial.println(F("l/r need independent mode (mode ind)")); return; }
    else { Serial.println(F("? Unknown command. h for help.")); return; }
  } else {
    if (word == "w") setTargets(v, v, true);
    else if (word == "s") setTargets(-v, -v, true);
    else if (word == "a") setTargets(-v, v, true);
    else if (word == "d") setTargets(v, -v, true);
    else if (word == "l") setTargets(rest.toInt(), usToPct(target2), true);
    else if (word == "r") setTargets(usToPct(target1), rest.toInt(), true);
    else if (word == "t") { Serial.println(F("t needs mixed mode (mode mix)")); return; }
    else { Serial.println(F("? Unknown command. h for help.")); return; }
  }
  Serial.print(F("-> RC1 ")); Serial.print(usToPct(target1)); Serial.print(F("%  RC2 "));
  Serial.print(usToPct(target2)); Serial.println(F("%"));
}

void setup() {
  // Start at neutral BEFORE anything else, so the driver captures 1500 us as "stop".
  rc1.attach(PIN_RC1);
  rc2.attach(PIN_RC2);
  rc1.writeMicroseconds(NEUTRAL_US);
  rc2.writeMicroseconds(NEUTRAL_US);

  Serial.begin(115200);
  Serial.println();
  Serial.println(F("D.I.R.T.T. motor test - sending STOP (1500 us) on D9/D10."));
  Serial.println(F("Wheels off the ground? Now switch on the 12 V to the MDDRC10."));
  Serial.println(F("Its ERR LED blinking twice = it isn't getting pulses (check D9/D10/GND)."));
  printHelp();
  printStatus();
}

void loop() {
  updateOutputs();
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { handle(line); line = ""; }
    else if (line.length() < 40) line += c;
  }
}
