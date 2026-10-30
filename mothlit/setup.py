"""Interactive onboarding: `python -m mothlit setup`."""

import re
import webbrowser
from getpass import getpass
from urllib.parse import parse_qs, urlparse

import tinytuya

from . import config
from .devices import DeviceError, save_oauth_credentials
from .devices.smartthings import (
    DEFAULT_REDIRECT,
    AuthOAuth,
    AuthPAT,
    SmartThingsClient,
    authorization_url,
    exchange_code,
)

# Tuya lighting categories (dj = bulb, dd = strip, xdd = ceiling, fwd = ambient, dc = string)
_LIGHT_CATEGORIES = {"dj", "dd", "xdd", "fwd", "dc"}
_TUYA_REGIONS = ["us", "us-e", "eu", "eu-w", "sg", "in", "cn"]


def run() -> None:
    print("=== Mothlit setup ===")
    print(f"Non-sensitive configuration: {config.env_path()}")
    print("Secrets (local_key, tokens): Windows keyring (Credential Manager)\n")

    if _yes("Configure the lamp (Tuya)?"):
        _setup_lamp()
    if _yes("Configure the air conditioner (SmartThings)?"):
        _setup_ac()
    print("\nDone. Test with: uv run python -m mothlit test-lamp  |  uv run python -m mothlit test-ac")


# --- lamp ---


def _setup_lamp() -> None:
    print(
        "\nLocal control needs: device_id, local_key, IP and protocol version.\n"
        "  1) Automatic: enter the Access ID/Secret of your Tuya IoT Platform project\n"
        "     (iot.tuya.com > Cloud > your project). The data is fetched from the cloud once\n"
        "     and the IP/version is looked up on the local network. The Access Secret is NOT saved.\n"
        "  2) Manual: run `python -m tinytuya wizard` (creates devices.json with id and key)\n"
        "     and `python -m tinytuya scan` (shows IP and version), and type the values here."
    )
    choice = input("Option [1/2] (1): ").strip() or "1"
    data = _lamp_automatic() if choice == "1" else None
    if data is None:
        data = _lamp_manual()

    device_id, local_key, ip, version, name = data
    config.save_secret(config.SECRET_LAMP_KEY, local_key)
    config.save_env({"LAMP_ID": device_id, "LAMP_IP": ip, "LAMP_VERSION": str(version),
                     "LAMP_NAME": name or "Lamp"})
    print(f"Lamp saved: {device_id} at {ip} (protocol {version}).")
    print("Tip: reserve this IP on the router (static DHCP) so it does not change.")


def _lamp_automatic():
    access_id = input("Access ID: ").strip()
    access_secret = getpass("Access Secret (hidden): ").strip()
    region = input(f"Region {_TUYA_REGIONS} (us): ").strip() or "us"

    cloud = tinytuya.Cloud(apiRegion=region, apiKey=access_id, apiSecret=access_secret, configFile="")
    if getattr(cloud, "error", None):
        print(f"Failed to authenticate with Tuya: {cloud.error}")
        return None
    devices = cloud.getdevices()
    if not isinstance(devices, list) or not devices:
        print(f"No devices found in this region ({devices}). Try another region or the manual mode.")
        return None

    lights = [d for d in devices if d.get("category") in _LIGHT_CATEGORIES] or devices
    chosen = _choose(lights, lambda d: f"{d.get('name')}  [{d.get('id')}]  {d.get('product_name', '')}")

    print("Looking for the device on the local network (up to ~20 s)...")
    found = tinytuya.deviceScan(verbose=False, maxretry=15, byID=True)
    local = found.get(chosen["id"], {})
    ip = local.get("ip") or input("Not found on the network. Lamp IP: ").strip()
    version = local.get("version") or input("Protocol version (e.g. 3.3, 3.5): ").strip()
    return chosen["id"], chosen["key"], ip, float(version), chosen.get("name") or ""


def _lamp_manual():
    device_id = input("device_id: ").strip()
    local_key = getpass("local_key (hidden): ").strip()
    ip = input("IP: ").strip()
    version = float(input("Protocol version (e.g. 3.3, 3.5): ").strip())
    name = input("Display name (Lamp): ").strip()
    return device_id, local_key, ip, version, name


# --- air conditioner ---


def _setup_ac() -> None:
    print(
        "\nHow will Mothlit access SmartThings?\n"
        "  1) OAuth (recommended): you authorize once and access renews itself\n"
        "     (Mothlit just needs to run at least once every 30 days)\n"
        "  2) Personal access token (PAT): simpler, but new tokens expire in 24 h"
    )
    choice = input("Option [1/2] (1): ").strip() or "1"
    auth = _setup_oauth() if choice == "1" else _setup_pat()
    if auth is None:
        return

    client = SmartThingsClient(auth)
    try:
        devices = client.list_devices()
    except DeviceError as e:
        print(f"Error: {e}")
        return
    finally:
        client.close()

    def caps(d):
        return {c["id"] for comp in d.get("components", []) for c in comp.get("capabilities", [])}

    candidates = [d for d in devices if "airConditionerMode" in caps(d)] or devices
    if not candidates:
        print("No devices in the account.")
        return
    chosen = _choose(candidates, lambda d: f"{d.get('label') or d.get('name')}  [{d['deviceId']}]")
    config.save_env({"SMARTTHINGS_DEVICE_ID": chosen["deviceId"]})
    print(f"Air conditioner saved: {chosen.get('label')}.")


def _setup_pat():
    print(
        "\nCreate a Personal Access Token at https://account.smartthings.com/tokens\n"
        "with the Devices permissions: List, See and Control (r:devices:*, x:devices:*)."
    )
    token = getpass("Token (hidden): ").strip()
    if not token:
        return None
    config.save_secret(config.SECRET_SMARTTHINGS_PAT, token)
    config.delete_secret_json(config.SECRET_SMARTTHINGS_OAUTH)  # PAT chosen: the old OAuth goes away
    return AuthPAT(token)


def _setup_oauth():
    print(
        "\nOne-time step: create an OAuth app in your account with the SmartThings CLI.\n"
        "  1. Install the CLI: download smartthings.msi from\n"
        "     https://github.com/SmartThingsCommunity/smartthings-cli/releases\n"
        "  2. In a terminal, run:  smartthings apps:create\n"
        "     (the first time it opens the browser so you can sign in to your Samsung account)\n"
        "     - App type:              OAuth-In App\n"
        "     - Display Name:          Mothlit\n"
        "     - Description:           PC control\n"
        "     - Icon Image URL and Target URL: leave blank (Enter)\n"
        "     - Scopes:                select r:devices:* and x:devices:*\n"
        f"     - Redirect URI:          Add Redirect URI -> {DEFAULT_REDIRECT}\n"
        "       then 'Finish editing Redirect URIs' and 'Finish and create OAuth-In SmartApp'\n"
        "  3. Copy the OAuth Client Id and the OAuth Client Secret (the secret is shown only ONCE)."
    )
    client_id = input("\nOAuth Client Id: ").strip()
    client_secret = getpass("OAuth Client Secret (hidden): ").strip()
    if not (client_id and client_secret):
        print("Client Id and Client Secret are required.")
        return None
    redirect = input(f"Redirect URI ({DEFAULT_REDIRECT}): ").strip() or DEFAULT_REDIRECT

    url, state = authorization_url(client_id, redirect)
    print(
        "\nOpen the address below (I will try to open it for you), sign in to your Samsung account and authorize.\n"
        f"\n  {url}\n\n"
        "After authorizing, the browser goes to an httpbin page.\n"
        "Copy the full ADDRESS from the browser bar (or just the value of \"code\") and paste it here."
    )
    webbrowser.open(url)
    for _ in range(3):
        try:
            code = extract_code(input("\nAddress or code: "), state)
            credentials = exchange_code(client_id, client_secret, code, redirect)
            break
        except ValueError as e:
            print(f"Could not understand: {e}")
        except DeviceError as e:
            print(f"Error: {e}")
    else:
        return None

    save_oauth_credentials(credentials)
    print("Authorized! Access will be renewed automatically.")
    return AuthOAuth(credentials, save=save_oauth_credentials)


def extract_code(text: str, expected_state: str | None = None) -> str:
    """Accepts the redirect address, the JSON of the httpbin page or just the code."""
    text = text.strip()
    if not text:
        raise ValueError("nothing was pasted.")
    if text.startswith("http"):
        params = parse_qs(urlparse(text).query)
        if "error" in params:
            raise ValueError(f"SmartThings refused the authorization ({params['error'][0]}).")
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [None])[0]
        if expected_state and state and state != expected_state:
            raise ValueError("the address is not from this authorization (state mismatch). Use the new link.")
    elif "\"code\"" in text:
        match = re.search(r'"code"\s*:\s*"([^"]+)"', text)
        code = match.group(1) if match else ""
    else:
        code = text
    if not re.fullmatch(r"[A-Za-z0-9._~-]+", code or ""):
        raise ValueError("could not find the authorization code.")
    return code

# --- utilities ---


def _choose(items: list, label):
    if len(items) == 1:
        print(f"Found: {label(items[0])}")
        return items[0]
    for i, item in enumerate(items, 1):
        print(f"  {i}) {label(item)}")
    while True:
        answer = input("Number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(items):
            return items[int(answer) - 1]


def _yes(question: str) -> bool:
    return input(f"{question} [Y/n]: ").strip().lower() not in ("n", "no")
