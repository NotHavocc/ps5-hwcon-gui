from functools import reduce
from math import gcd

APP_TITLE = "PS5 Hardware Control"

FAN_MIN = 40
FAN_MAX = 90
FAN_DEFAULT = 65
FAN_BOOT_TARGET = 80
FAN_MAX_COOLING = 50
GUARD_MIN = 80
GUARD_MAX = 100
GUARD_DEFAULT = 95
GUARD_HYSTERESIS = 10
LED_LOOP_MIN = 2
LED_LOOP_MAX = 30
LED_LOOP_DEFAULT = 6
CPU_CLOCK_STEP = 100
GPU_CLOCK_STEP = 25
STATUS_POLL_MS = 2000
SETTING_SAVE_DELAY_MS = 600

FAN_PRESETS = [
    ("quiet", "Quiet", 85),
    ("default", "Default", FAN_BOOT_TARGET),
    ("balanced", "Balanced", 72),
    ("cool", "Cool", 65),
    ("max", "Max Cooling", FAN_MAX_COOLING),
]

FAN_CURVE_POINTS = 8
FAN_CURVE_TEMP_MIN = 20
FAN_CURVE_TEMP_MAX = 90
FAN_PWM_MAX = 255
FAN_MODE_FULL = 0
FAN_MODE_CURVE = 2
FAN_MODE_LABELS = {FAN_MODE_FULL: "Full Speed", 1: "Manual", FAN_MODE_CURVE: "Curve"}
# Temperatures of the driver's built-in quiet curve; its PWM values depend on the board.
FAN_QUIET_TEMPS = [50, 60, 65, 70, 75, 80, 85, 87]
FAN_QUIET_STOP = 45


def pwm_to_percent(pwm):
    return round(pwm * 100 / FAN_PWM_MAX)


def percent_to_pwm(percent):
    return round(percent * FAN_PWM_MAX / 100)


def _curve(stop, points):
    return {"stop": stop, "points": [[temp, percent_to_pwm(pct)] for temp, pct in points]}


# (id, label, subtitle, curve); a curve of None means the driver's default.
FAN_CURVE_PRESETS = [
    ("quiet", "Quiet", "Kernel default", None),
    (
        "balanced",
        "Balanced",
        "100% at 85 °C",
        _curve(40, [(45, 15), (55, 25), (60, 35), (65, 45), (70, 60), (75, 75), (80, 90), (85, 100)]),
    ),
    (
        "cool",
        "Cool",
        "100% at 80 °C",
        _curve(35, [(40, 20), (50, 30), (55, 40), (60, 50), (65, 65), (70, 80), (75, 90), (80, 100)]),
    ),
]

CURATED_LED_PRESETS = [
    ("off", "Off"),
    ("white_bright", "White Bright"),
    ("blue_rich", "Blue Rich"),
    ("purple", "Purple"),
    ("orange_breathe", "Orange Breathe"),
    ("pink_breathe", "Pink Breathe"),
]

GOVERNORS = {
    "performance": ("Performance", "Highest clocks"),
    "powersave": ("Powersave", "Lowest clocks"),
    "schedutil": ("Schedutil", "Follows scheduler load"),
    "ondemand": ("Ondemand", "Jumps up under load"),
    "conservative": ("Conservative", "Ramps up gradually"),
    "userspace": ("Userspace", "Speed set by a program"),
}

EPP_GOVERNORS = {
    "performance": ("Performance", "Biased to max clocks"),
    "powersave": ("Powersave", "Firmware managed"),
}

GPU_GOVERNORS = {
    "simple_ondemand": ("Ondemand", "Follows GPU load"),
    "performance": ("Performance", "Highest clock"),
    "powersave": ("Powersave", "Lowest clock"),
    "userspace": ("Userspace", "Clock set by a program"),
}


def clamp(value, low, high):
    return min(high, max(low, value))


def format_temp(celsius):
    return f"{round(celsius)} °C"


def format_freq(mhz):
    return f"{mhz / 1000:.2f} GHz" if mhz >= 1000 else f"{mhz} MHz"


def prettify(identifier):
    return " ".join(part[:1].upper() + part[1:] for part in identifier.split("_") if part)


def is_epp_driver(driver):
    return driver is not None and (driver.endswith("-epp") or driver == "intel_pstate")


def governor_info(identifier, driver):
    if is_epp_driver(driver) and identifier in EPP_GOVERNORS:
        return EPP_GOVERNORS[identifier]
    return GOVERNORS.get(identifier, (prettify(identifier), "Kernel governor"))


def gpu_governor_info(identifier):
    return GPU_GOVERNORS.get(identifier, (prettify(identifier), "Kernel governor"))


def nearest(value, choices):
    if not choices:
        return value
    return min(choices, key=lambda choice: (abs(choice - value), choice))


def slider_step(steps, fallback):
    if len(steps) < 2:
        return fallback
    return reduce(gcd, (b - a for a, b in zip(steps, steps[1:])), 0) or fallback
