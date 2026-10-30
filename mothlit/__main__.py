"""Entry point: `python -m mothlit [setup | test-lamp | test-ac]`. With no argument it opens the UI."""

import argparse
import sys
import time

from . import config
from .devices import DeviceError, create_ac, create_lamp


def test_lamp() -> None:
    lamp = create_lamp()
    print("Reading the lamp state...")
    initial = lamp.state()
    print(f"  {initial}")

    steps = [
        ("Turning on", lamp.turn_on),
        ("Brightness 20 %", lambda: lamp.set_brightness(20)),
        ("Brightness 100 %", lambda: lamp.set_brightness(100)),
    ]
    if initial.supports_temp:
        steps += [
            ("Warm white", lambda: lamp.set_color_temp(0)),
            ("Cool white", lambda: lamp.set_color_temp(100)),
        ]
    if initial.supports_color:
        steps += [
            ("Red", lambda: lamp.set_color(255, 0, 0)),
            ("Green", lambda: lamp.set_color(0, 255, 0)),
            ("Blue", lambda: lamp.set_color(0, 0, 255)),
        ]
    for name, action in steps:
        print(f"- {name}")
        action()
        time.sleep(2)
    print(f"  State now: {lamp.state()}")

    print("- Restoring the initial state")
    if initial.supports_temp and initial.color_temp is not None:
        lamp.set_color_temp(initial.color_temp)
    lamp.set_brightness(max(initial.brightness, 1))
    if not initial.on:
        lamp.turn_off()
    print("OK")


def test_ac() -> None:
    ac = create_ac()
    print("Declared capabilities:")
    print("  " + ", ".join(sorted(ac.capabilities())))
    state = ac.state()
    print("\nCurrent state:")
    print(f"  On: {state.on}")
    print(f"  Room temperature: {state.room_temp} °C")
    print(f"  Target temperature: {state.target_temp} °C (range {state.target_range})")
    print(f"  Mode: {state.mode}  (available: {state.modes})")
    print(f"  Fan: {state.fan}  (available: {state.fans})")

    answer = input("\nTest commands? Turns on, raises 1 °C, restores the temperature and on/off. [y/N]: ")
    if answer.strip().lower() not in ("y", "yes"):
        return
    target = state.target_temp or 24
    if not state.on:
        print("- Turning on")
        ac.turn_on()
        time.sleep(3)
    print(f"- Target temperature {target + 1:g} °C")
    ac.set_temperature(target + 1)
    time.sleep(3)
    print(f"  Read back: {ac.state().target_temp} °C")
    print(f"- Back to {target:g} °C")
    ac.set_temperature(target)
    if not state.on:
        time.sleep(2)
        print("- Turning off")
        ac.turn_off()
    print("OK")


def verify() -> None:
    """Checks everything the app startup uses, without opening a window or using the network.

    Runs on the freshly built executable before installing (update.cmd): it catches problems that
    only show up when packaged, such as files that do not exist inside the .exe.
    """
    import keyring
    import pystray
    import webview  # noqa: F401  (pywebview and pythonnet must import in the executable)

    from .tray import Tray
    from .ui import app, brand

    steps = [
        ("Interface (web/index.html)", lambda: (app.WEB / "index.html").is_file() or _fail("not found")),
        ("Quick panel (web/flyout.html, common.js)", lambda: all((app.WEB / n).is_file() for n in
            ("flyout.html", "flyout.js", "flyout.css", "common.js")) or _fail("missing files")),
        ("Window icon", brand.ico_file),
        ("Tray icon", brand.tray_ico),
        ("Windows keyring", lambda: "Windows" in type(keyring.get_keyring()).__module__
            or _fail(type(keyring.get_keyring()).__name__)),
        ("Tray (pystray)", lambda: Tray(app.Api(), on_open=lambda: None, on_quit=lambda: None)),
        ("Tray backend", lambda: pystray.Icon.__module__.endswith("_win32") or _fail(pystray.Icon.__module__)),
        ("Configuration and devices", app.Api.from_config),
    ]
    for name, step in steps:
        step()
        print(f"  ok  {name}")
    print("All good.")


def _fail(reason: str):
    raise RuntimeError(reason)


def main() -> int:
    parser = argparse.ArgumentParser(prog="mothlit", description="Control the lamp and the air conditioner.")
    parser.add_argument("command", nargs="?", choices=["setup", "test-lamp", "test-ac", "verify"])
    parser.add_argument("--tray", action="store_true", help="start hidden in the tray (used when launching at startup)")
    # startup entries written by older versions still pass the Portuguese flag
    parser.add_argument("--bandeja", dest="tray", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    config.migrate_legacy()
    try:
        if args.command == "setup":
            from . import setup

            setup.run()
        elif args.command == "test-lamp":
            test_lamp()
        elif args.command == "test-ac":
            test_ac()
        elif args.command == "verify":
            try:
                verify()
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {e}", file=sys.stderr)
                return 1
        else:
            from .ui.app import run

            config.setup_logging()
            run(in_tray=args.tray)
    except (DeviceError, config.ConfigError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
