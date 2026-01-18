#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import json
from statistics import mean, pstdev

# ==============================
# Configuration
# ==============================
GPIO_MAP = {
    "GPS": 27,
    "LORA": 16,
    "SDR": 7,
    "USB": 23,
}

FEATURE_META = {
    "GPS":  {"device": "/dev/ttyAMA0", "type": "serial"},
    "LORA": {"type": "spi"},
    "SDR":  {"type": "usb"},
    "USB":  {"type": "usb"},
}

# uConsole reality
BATTERY_SUPPLY = "axp20x-battery"
AC_SUPPLY = "axp22x-ac"

# ==============================
# GPIO Helpers
# ==============================
class GpioController:
    @staticmethod
    def run(cmd):
        try:
            return subprocess.check_output(cmd, text=True).strip()
        except Exception:
            return None

    @staticmethod
    def set_gpio(pin, state):
        subprocess.call([
            "pinctrl", "set", str(pin), "op", "dh" if state else "dl"
        ])

    @staticmethod
    def get_gpio(pin):
        out = GpioController.run(["pinctrl", "get", str(pin)])
        return bool(out and "hi" in out)

# ==============================
# Telemetry
# ==============================
class Telemetry:
    @staticmethod
    def _read_int(path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except Exception:
            return None

    @staticmethod
    def ac_online():
        v = Telemetry._read_int(f"/sys/class/power_supply/{AC_SUPPLY}/online")
        return bool(v) if v is not None else None

    @staticmethod
    def battery_status():
        try:
            with open(f"/sys/class/power_supply/{BATTERY_SUPPLY}/status") as f:
                return f.read().strip()
        except Exception:
            return None

    @staticmethod
    def battery_v_i_w():
        v_uv = Telemetry._read_int(f"/sys/class/power_supply/{BATTERY_SUPPLY}/voltage_now")
        i_ua = Telemetry._read_int(f"/sys/class/power_supply/{BATTERY_SUPPLY}/current_now")
        if v_uv is None or i_ua is None:
            return None

        v = v_uv / 1e6
        i = i_ua / 1e6
        w = abs(v * i)

        return {
            "voltage": round(v, 2),
            "current": round(i, 2),
            "power": round(w, 2),
        }

# ==============================
# Sampling / Measurement
# ==============================
def sample_battery_power(seconds=3.0, interval=0.2):
    currents, powers = [], []
    voltage = None

    end = time.time() + max(0.1, seconds)
    while time.time() < end:
        viw = Telemetry.battery_v_i_w()
        if viw:
            voltage = viw["voltage"]
            currents.append(viw["current"])
            powers.append(viw["power"])
        time.sleep(max(0.05, interval))

    if not currents:
        return None

    return {
        "voltage": voltage,
        "current_mean": round(mean(currents), 2),
        "current_sd": round(pstdev(currents), 2) if len(currents) > 1 else 0.0,
        "power_mean": round(mean(powers), 2),
        "power_sd": round(pstdev(powers), 2) if len(powers) > 1 else 0.0,
        "samples": len(currents),
    }

def measure_feature(feature, sample_seconds=3.0, settle_seconds=1.0, interval=0.2):
    feature = feature.upper()
    if feature not in GPIO_MAP:
        print(f"Unknown feature '{feature}'")
        return 2

    pin = GPIO_MAP[feature]
    orig = GpioController.get_gpio(pin)

    ac = Telemetry.ac_online()
    batt_status = Telemetry.battery_status()

    print(f"Measure: {feature} (GPIO{pin})")
    print(f"Power source: {'AC online' if ac else 'AC offline/unknown'} | Battery status: {batt_status or 'n/a'}")
    print(f"Current state: {'ON' if orig else 'OFF'}")

    if orig:
        print("Sampling ON state...")
        on = sample_battery_power(sample_seconds, interval)
        print(f"Disabling {feature}...")
        GpioController.set_gpio(pin, False)
        time.sleep(settle_seconds)
        print("Sampling OFF state...")
        off = sample_battery_power(sample_seconds, interval)
        print(f"Restoring {feature} to ON...")
        GpioController.set_gpio(pin, True)
    else:
        print("Sampling OFF state...")
        off = sample_battery_power(sample_seconds, interval)
        print(f"Enabling {feature}...")
        GpioController.set_gpio(pin, True)
        time.sleep(settle_seconds)
        print("Sampling ON state...")
        on = sample_battery_power(sample_seconds, interval)
        print(f"Restoring {feature} to OFF...")
        GpioController.set_gpio(pin, False)

    if not on or not off:
        print("Error: telemetry sampling failed.")
        return 1

    d_cur = round(on["current_mean"] - off["current_mean"], 2)
    d_pwr = round(on["power_mean"] - off["power_mean"], 2)

    print("\nResults (battery net draw)")
    print("--------------------------")
    print(f"OFF: {off['voltage']:.2f} V  {off['current_mean']:.2f} A  ({off['power_mean']:.2f} W)  ±{off['power_sd']:.2f}W")
    print(f"ON : {on['voltage']:.2f} V  {on['current_mean']:.2f} A  ({on['power_mean']:.2f} W)  ±{on['power_sd']:.2f}W")
    print("--------------------------")
    sign = "+" if d_pwr >= 0 else "-"
    print(f"Δ   {sign}{abs(d_cur):.2f} A   ({sign}{abs(d_pwr):.2f} W)")

    return 0

# ==============================
# Live / Status
# ==============================
def show_power_live():
    try:
        while True:
            viw = Telemetry.battery_v_i_w()
            ac = Telemetry.ac_online()
            batt = Telemetry.battery_status()

            os.system("clear")
            print("Power Monitor (Ctrl+C to quit)")
            print("-----------------------------")
            print(f"Source: {'AC online' if ac else 'AC offline'} | Battery: {batt or 'n/a'}")

            if viw:
                print(f"{viw['voltage']:.2f} V  {viw['current']:.2f} A  ({viw['power']:.2f} W)")
            else:
                print("Telemetry unavailable")

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting power monitor.")

def show_watch():
    try:
        while True:
            states = [f"{f}:{'ON' if GpioController.get_gpio(p) else 'OFF'}" for f, p in GPIO_MAP.items()]
            viw = Telemetry.battery_v_i_w()
            ac = Telemetry.ac_online()
            batt = Telemetry.battery_status()
            power = viw["power"] if viw else "n/a"

            print(
                "  ".join(states)
                + f"  Src:{'AC' if ac else 'BAT'} Batt:{batt or 'n/a'} Power:{power}W",
                end="\r",
                flush=True,
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting watch mode.")

# ==============================
# Entrypoint
# ==============================
def main():
    if len(sys.argv) == 1:
        for f, p in GPIO_MAP.items():
            print(f"{f:<5} GPIO{p}: {'ON' if GpioController.get_gpio(p) else 'OFF'}")
        return

    if sys.argv[1] == "--power":
        show_power_live()
        return

    if sys.argv[1] == "--watch":
        show_watch()
        return

    if sys.argv[1] == "--measure":
        if len(sys.argv) < 3:
            print("Usage: aiov2_ctl --measure <FEATURE> [--seconds N] [--interval S] [--settle S]")
            return

        feature = sys.argv[2]
        seconds, interval, settle = 3.0, 0.2, 1.0

        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--seconds":
                seconds = float(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--interval":
                interval = float(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--settle":
                settle = float(sys.argv[i + 1]); i += 2
            else:
                i += 1

        sys.exit(measure_feature(feature, seconds, settle, interval))

    if len(sys.argv) == 3:
        feature = sys.argv[1].upper()
        state = sys.argv[2].lower() == "on"
        if feature in GPIO_MAP:
            GpioController.set_gpio(GPIO_MAP[feature], state)
            return

    print("Usage: aiov2_ctl [--power|--watch|--measure <FEATURE>|<feature> on|off]")

if __name__ == "__main__":
    main()
