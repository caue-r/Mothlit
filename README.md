# Mothlit

Personal desktop app to control from the PC, without going through Alexa:

- **Ekaza lamp** (Tuya / Smart Life platform): **local** control over the LAN with [tinytuya](https://github.com/jasonacox/tinytuya).
- **Samsung air conditioner**: [SmartThings REST API](https://developer.smartthings.com/docs/api/public).

## Installation

Uses [uv](https://docs.astral.sh/uv/). It installs Python 3.12 if needed and pins the versions in `uv.lock`, so the environment is reproducible.

```powershell
uv sync
uv run pytest            # tests (they do not need the devices)
```

## Configuration

```powershell
uv run python -m mothlit setup
```

Setup saves:

- what is not sensitive (IDs, IP, protocol version) in `%APPDATA%\Mothlit\.env` (template in `.env.example`);
- the secrets (the lamp's `local_key` and the SmartThings token) in the Windows **keyring** (Credential Manager › Windows Credentials › `mothlit`).

### Lamp (Tuya)

Local control needs the `device_id`, the `local_key`, the IP and the **protocol version**. The `local_key` only comes from the Tuya cloud, so you need a developer account once:

1. Create an account at [iot.tuya.com](https://iot.tuya.com) › *Cloud › Development › Create Cloud Project*. Choose the data center of your Smart Life account (in Brazil it is usually *Western America*, region `us`).
2. In *Devices › Link App Account*, scan the QR code with the Smart Life app.
3. Write down the project's **Access ID** and **Access Secret**.

In setup, choose:

- **Option 1 (automatic)**: enter the Access ID, Access Secret and region. Mothlit fetches the `device_id` and the `local_key` from the cloud and looks up the IP and version on the local network. The Access Secret is not saved.
- **Option 2 (manual)**: run `uv run python -m tinytuya wizard` (creates `devices.json` with `id` and `key`) and `uv run python -m tinytuya scan` (shows IP and version), and type the values.

> The `local_key` changes if you pair the lamp again in the app. If that happens, run setup again.
> Reserve the lamp's IP on the router (static DHCP).

### Air conditioner (SmartThings)

Setup asks how Mothlit will access SmartThings:

#### 1. OAuth (recommended: authorize once and it renews itself)

The access token lasts about 24 h and is **renewed automatically** with the refresh token, which lasts 30 days and changes on every renewal. As long as Mothlit runs at least once every 30 days, you do not need to do anything else (with "Launch at Windows startup" on, that is practically guaranteed).

One-time step, create an OAuth app in your account with the [SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli) (registering through the website is not available yet):

1. Install the CLI: download and run `smartthings.msi` from the [releases page](https://github.com/SmartThingsCommunity/smartthings-cli/releases).
2. Run `smartthings apps:create`. The first time, it opens the browser so you can sign in to your Samsung account.
   - App type: **OAuth-In App**
   - Display Name: `Mothlit` · Description: any text · Icon Image URL and Target URL: blank
   - Scopes: `r:devices:*` and `x:devices:*`
   - Redirect URI: **Add Redirect URI** › `https://httpbin.org/get` › *Finish editing Redirect URIs* › *Finish and create OAuth-In SmartApp*
3. Keep the **OAuth Client Id** and the **OAuth Client Secret**. The secret is shown only once.
4. Run `uv run python -m mothlit setup`, choose **OAuth** and paste the Client Id and the Client Secret. The browser opens Samsung's authorization screen. After you authorize, it goes to an httpbin page: copy the **full address** from the browser bar and paste it into setup.

Details:
- The credentials (client id/secret and tokens) are kept in the keyring, in chunks if they are large (Windows limits each secret to ~1280 characters).
- Each refresh token can only be used once. Mothlit saves the new one to the keyring right away and refreshes in a thread-safe way (several simultaneous calls cause a single refresh).
- Mothlit tries `https://api.smartthings.com/oauth/token` and, if it does not exist, `.../v1/oauth/token` (the new docs and the community mention different addresses).
- If the authorization expires (more than 30 days without running, or revoked), the app tells you and you just run setup again.

#### 2. Personal access token (PAT)

1. Go to <https://account.smartthings.com/tokens> and create a token with the **Devices** permissions: *List*, *See* and *Control* (`r:devices:*`, `x:devices:*`).
2. In setup, choose **Personal access token** and paste the token.

**Limitation:** PATs created after 12/30/2024 are valid for only **24 hours**. When it expires, paste a new one in **Settings › SmartThings access**: Mothlit validates the token before saving it.

### Upgrading from an older version

Older versions saved the settings with Portuguese names (`LAMPADA_*` in the `.env`, `preferencias.json`, etc.). Mothlit renames them automatically the first time the new version runs, so you do not need to run setup again.
## Usage

```powershell
uv run python -m mothlit             # opens the interface
uv run python -m mothlit test-lamp   # turns on, changes brightness/temperature/color and restores the initial state
uv run python -m mothlit test-ac     # shows capabilities and state; commands only if you confirm
```

### System tray

- **–** (minimize) hides the window in the tray; **×** quits the app (or goes to the tray, see below).
- **Click the moth icon**: opens the **quick panel** next to the tray, with just the essentials (lamp: on/off and brightness; AC: on/off, temperature − / + and room temperature). It disappears when you click outside (or Esc). The expand button opens the full app, and each device's › arrow opens straight on its tab.
- **Right-click the icon**: the menu has **Open Mothlit** (full app), **Turn light on/off**, **Turn AC on/off** (the label follows the current state) and **Quit**. Tray actions show a Windows notification.
- The state of both devices is reread every 30 s (and with the ⟳ button or F5).
- There is only one instance: opening Mothlit again brings up the window that is already running (even if it started hidden).

### Settings (settings button)

- **Launch at Windows startup**: writes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (your user only, no admin). Mothlit opens hidden in the tray (`--tray`), without a console.
- **Minimize to tray on close**: × and Alt+F4 hide the app; to quit, use **Quit** in the tray menu. Saved in `%APPDATA%\Mothlit\preferences.json`.
## Executable (Windows)

```powershell
uv run pyinstaller packaging/mothlit.spec --noconfirm        # builds dist\Mothlit\
powershell -ExecutionPolicy Bypass -File packaging\install.ps1
```

Or double-click `packaging\install.cmd`: it runs the installer and waits for an Enter at the end so you can read the result (or the error).

The build creates a folder (`onedir`) with two executables that share the dependencies:

| File | What for |
|---|---|
| `Mothlit.exe` | Interface and tray, no console. This is the one that launches at Windows startup. |
| `mothlit-cli.exe` | Command line: `mothlit-cli setup`, `test-lamp`, `test-ac`. |

I used a folder instead of a single file because `onefile` unpacks itself into a temporary folder on every launch: it starts more slowly (bad for "Launch at Windows startup") and often triggers antivirus false positives.

`install.ps1` (no administrator):
- copies to `%LOCALAPPDATA%\Programs\Mothlit` and creates the **Mothlit** shortcut in the Start Menu;
- closes the installed Mothlit if it is open;
- if "Launch at Windows startup" is on, points the registry to the new `Mothlit.exe`.

Configuration (`%APPDATA%\Mothlit`) and secrets (keyring) live outside the app folder, so reinstalling or updating loses nothing. **To update** the installed app after code changes, double-click `packaging\update.cmd`: it builds, runs `mothlit-cli verify` on the new executable (icons, interface, tray, keyring; without opening a window or using the network) and only reinstalls if everything passes. The installed app is a copy and does not change by itself. If Mothlit is open, the installer asks it to quit (without leaving a ghost icon in the tray) and reopens it in the tray with the new version.

The executable writes a log to `%APPDATA%\Mothlit\mothlit.log` (rotated, up to ~3 MB): that is where to look if something goes wrong, since there is no console.

Requirement: WebView2 Runtime, which already ships with Windows 11.
## Structure

```
mothlit/
  __main__.py            CLI (setup, test-lamp, test-ac)
  config.py              .env + keyring
  setup.py               interactive onboarding
  devices/
    base.py              Device protocol + DeviceError
    lamp.py              tinytuya.BulbDevice (detects type and features from the DPS)
    smartthings.py       httpx client + authentication (AuthPAT, AuthOAuth)
    air_conditioner.py   capabilities switch, thermostatCoolingSetpoint,
                         airConditionerMode, airConditionerFanMode, temperatureMeasurement,
                         fanOscillationMode, custom.airConditionerOptionalMode
  tray.py                tray icon (pystray) with quick actions
  startup.py             launch at Windows startup (user Run registry key)
  ui/
    app.py               pywebview window (frameless) + Api: the bridge the JavaScript calls
    flyout.py            tray quick panel (opens next to the taskbar, hides when it loses focus)
    brand.py             builds the moth .ico from web/moth.svg
    web/                 HTML/CSS/JS interface: index.html/app.js (full), flyout.* (quick panel),
                         common.js (icons, bridge to Python, sliders), style.css, moth.svg
packaging/               mothlit.spec (PyInstaller), mothlit_app.py (.exe entry point), install.ps1/.cmd, update.cmd
tests/                   pytest with mocks (mocked tinytuya, httpx.MockTransport)
```

## Technical details

- **Interface**: [pywebview](https://pywebview.flowrl.com/) using WebView2 (the Edge engine, already included in Windows 11). The look is HTML/CSS/SVG, with GPU-accelerated transitions. Each JavaScript call to `pywebview.api` runs in a separate Python thread, so the network never freezes the interface. To open the developer tools: `set MOTHLIT_DEBUG=1`.
- **Lamp**: the type (A/B/C) is detected from the DPS with `detect_bulb()`. Color temperature and color only show up if the lamp has those features. The timeout is 2 s with 2 retries, instead of the tinytuya default (5 s × 5 retries). The socket is guarded by a lock, because tinytuya is not thread-safe.
- **Air conditioner**:
  - The capabilities come from `GET /devices/{id}`, minus the ones listed in `custom.disabledCapabilities`.
  - The modes and fan speeds come from `availableAcModes` and `availableAcFanModes`, which change with the current mode (in `auto`, for example, the only fan speed is `auto`). If they are missing, the app uses `supportedAcModes` and `supportedAcFanModes`.
  - The temperature range comes from `coolingSetpointRange`. If it is missing, the default is 16–30 °C.

## License

[MIT](LICENSE)
