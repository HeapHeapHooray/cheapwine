# 🍷 cheapwine

[![Publish to PyPI](https://github.com/HeapHeapHooray/cheapwine/actions/workflows/publish.yml/badge.svg)](https://github.com/HeapHeapHooray/cheapwine/actions/workflows/publish.yml)

A project-local Wine prefix and application manager (Wine's version of `uv`). 

`cheapwine` brings modern, declarative, and fast workflow management to Wine environments. Instead of managing a bloated directory of global prefixes (like Lutris or Bottles), `cheapwine` isolates prefixes directly inside your project folders and exposes a clean, git-friendly configuration file named `distillery.json`.

> [!NOTE]
> This project was fully designed and built by **Gemini** and **DeepSeek** (Advanced Agentic Coding AIs) in pair programming with the user! 🤖✨

---

## Key Features

* **Project-Local Prefixes**: Automatically sandboxes your Wine environments in `.cheapwine` inside your project directory.
* **Declarative Distillery Settings (`distillery.json`)**: Declare architectures, Windows versions, environment variables, and application commands in a single, portable JSON file.
* **Runner Overrides**: Use system Wine, Proton (via Steam), Wine-GE, Kron4ek, Soda, or custom-compiled Wine builds, both globally and overridden per application.
* **Runner Auto-Downloads**: Automatically download Wine-GE, Proton-GE, Kron4ek, and Soda runners from GitHub by name (e.g. `wine-ge-8-26`, `kron4ek-9.0`).
* **Custom Runner Versions**: Pin specific runner versions (e.g. `wine-ge-8-26`) globally or per application.
* **Declarative Winetricks**: Define winetricks components (DLLs, codecs, fonts) in `distillery.json` — applied automatically on prefix init and cached to avoid re-application.
* **Chocolatey Integration**: Install and manage Windows packages (like browsers, runtimes, or utilities) directly inside the prefix with automated installation of `Chocolatey-for-wine`.
* **LatencyFleX Support**: Built-in LatencyFleX environment variable configuration for competitive gaming (NVIDIA Reflex-like latency reduction).
* **Legacy 32-bit Support**: Create isolated 32-bit Wine prefixes (`win32`) on the fly, even for individual applications in a 64-bit project.
* **Auto-Integration Spam Block**: Prevents Wine from cluttering your Linux host's desktop search menu during app installation by disabling `winemenubuilder` by default.
* **Manual Desktop Export**: Clean CLI tools (`cheapwine export` / `cheapwine unexport`) to manually generate standard Linux desktop launchers (`.desktop` entries) for only the applications you want.
* **Auto-Discovery Scanner**: Scans Wine Start Menu shortcuts and `drive_c/Program Files` to automatically detect newly installed programs.
* **Beautiful CLI & Interactive TUI**: Features a clean, colorful, emoji-rich command-line output (inspired by `uv`) and a live interactive Terminal User Interface (TUI) menu for select-and-run workflows.
* **EasyDistill TUI Editor**: Full-screen interactive configuration editor (`cheapwine easydistill`) for editing `distillery.json` without touching JSON directly.

---

## Installation

To install `cheapwine` locally in editable mode (or from the repository root):

```bash
pip install -e .
```

This registers the `cheapwine` and `cw` entrypoints in your shell.

---

## Quick Start

### 1. Initialize a Project
Create a new directory and initialize the environment. This generates the `distillery.json` settings file and creates the local Wine prefix:

```bash
mkdir my-project && cd my-project
cheapwine init
```

### 2. Install a Program
Run your installer (e.g., `setup.exe`) inside the project prefix. `cheapwine` will block it from writing shortcuts to your Linux host applications menu, keeping your desktop clean:

```bash
cheapwine run setup.exe
```

### 3. Scan & List Installed Programs
Search the prefix for newly installed executables or shortcuts:

```bash
cheapwine list --all
# or only show auto-detected ones
cheapwine list --detected
```

### 4. Register the Application by Name
Register the auto-detected application in `distillery.json` by name only (it will automatically resolve the path to the executable):

```bash
cheapwine add "My Application"
```

### 5. Launch the TUI Menu
To see a menu of all registered and detected applications, use the arrow keys to navigate, and press Enter to launch:

```bash
cheapwine
# or
cheapwine run
```

---

## Configuration (`distillery.json`)

Here is an example of a fully configured `distillery.json`:

```json
{
  "name": "my-legacy-workspace",
  "wine_arch": "win64",
  "wine_version": "system",
  "win_version": "win10",
  "runner": "wine",
  "runner_version": "wine-ge-8-26",
  "latencyflex": false,
  "winetricks": ["corefonts", "vcrun2022"],
  "env": {
    "WINEDEBUG": "-all"
  },
  "apps": {
    "notepad": {
      "exe": "notepad.exe",
      "args": ["/A"],
      "env": {}
    },
    "win95_game": {
      "exe": "C:\\Program Files\\MyGame\\game.exe",
      "win_version": "win95",
      "wine_arch": "win32",
      "runner": "/home/user/wine-ge/bin/wine"
    },
    "my_game": {
      "exe": "C:\\Games\\game.exe",
      "latencyflex": true,
      "winetricks": ["d3dx11_43", "dxvk"],
      "args": ["-dx11"]
    }
  }
}
```

---

## Advanced Configurations

### Running a Legacy 32-bit Windows 95 App
If you have a game or program that requires a pure 32-bit prefix configured for Windows 95, you can add it with specific overrides:

```bash
cheapwine add "RetroGame" "C:\Program Files\game.exe" --arch win32 --win-version win95
```
When running `cheapwine run RetroGame`, a separate, isolated 32-bit Wine prefix is created inside `.cheapwine_win32`, and the registry is set to Windows 95 compatibility mode for this app.

### Using Custom Runners (like Proton)
You can configure a custom Wine runner (such as Proton for Steam games, Bottles runners, or custom builds) either globally or per-application:

**Globally:**
```bash
cheapwine init --runner "/home/user/.steam/steam/compatibilitytools.d/GE-Proton8-25/files/bin/wine"
```

**Per-Application:**
```bash
cheapwine add "SteamApp" "game.exe" --runner "proton run"
```

### Auto-Downloading Runners by Name
Specify a downloadable runner by name and version — cheapwine fetches it from GitHub automatically:

```bash
cheapwine init --runner "wine-ge" --runner-version "8-26"
cheapwine init --runner "proton-ge" --runner-version "8-25"
cheapwine init --runner "kron4ek" --runner-version "9.0"
cheapwine init --runner "soda" --runner-version "9.0-1"
```

### Declarative Winetricks
Define winetricks components in `distillery.json` and they are applied automatically on prefix init:

```bash
cheapwine init --runner "wine-ge-8-26"
# Then edit distillery.json to add:
# "winetricks": ["corefonts", "vcrun2022", "dxvk"]
```
Components are applied on `cheapwine init` and when running an app that has them configured. Applied components are cached per prefix in `cheapwine_tricks.json` so they are only applied once.

Per-application winetricks:
```bash
cheapwine add "MyGame" "game.exe" --tricks d3dx11_43 --tricks dxvk
```

### LatencyFleX Support
Enable LatencyFleX globally or per-application for NVIDIA Reflex-like latency reduction in competitive games:

**Globally:**
```bash
cheapwine init --latencyflex
```

**Per-Application:**
```bash
cheapwine add "CS2" "cs2.exe" --latencyflex
```

### Chocolatey Package Manager Integration
`cheapwine` supports installing and managing Windows applications and dependencies via Chocolatey directly inside your local prefix.

When you run `cheapwine chocolatey` for the first time, it automatically downloads and installs `Chocolatey-for-wine` in the prefix.

Examples:
```bash
# Install Firefox inside the prefix
cheapwine chocolatey install firefox

# Search for available packages
cheapwine chocolatey search git

# List installed packages
cheapwine chocolatey list
```

### Desktop Export & Custom URI Schemes
You can export any registered or auto-detected application to your host Linux desktop menu (generating a `.desktop` file and extracting its native `.exe` icon automatically). Additionally, you can register custom URI schemes (like `myapp://...`) so that clicking links in your browser launches the app inside the correct project prefix context.

#### Exporting an App
Export an application by name. This will extract its embedded icon using `pefile` and `Pillow`, place it in `~/.local/share/icons`, and generate a launcher file in `~/.local/share/applications`:
```bash
cheapwine export "SteamApp"
```

#### Registering Custom URI Schemes
You can associate custom URI/protocol handlers with an application:
```bash
cheapwine export "SteamApp" --uri-scheme "steam" --uri-scheme "steamlink"
```
Or define them during registration:
```bash
cheapwine add "SteamApp" "steam.exe" --uri-scheme "steam"
```
Once registered and exported, any URIs starting with `steam://` clicked on your host system will launch the `SteamApp` executable inside this specific project's prefix and pass the URI payload directly to it.

To remove host integration:
```bash
cheapwine unexport "SteamApp"
```

---

## Command Reference

| Command | Options | Description | Example |
| :--- | :--- | :--- | :--- |
| **`cheapwine init`** | `--arch [win32\|win64]`, `--win-version`, `--runner`, `--runner-version`, `--tricks`/`-t`, `--latencyflex/--no-latencyflex`, `--force` | Creates `distillery.json` and initializes the Wine prefix. | `cheapwine init --arch win32 --win-version win95 --latencyflex` |
| **`cheapwine run`** | `[app_or_exe]`, `[extra_args...]` | Runs a registered app or an executable path. Launches TUI if no app specified. | `cheapwine run mygame -dx11` |
| **`cheapwine tui`** | *None* | Launches the interactive arrow-key select menu. | `cheapwine tui` |
| **`cheapwine add`** | `--env`/`-e`, `--workdir`/`-w`, `--win-version`, `--arch`, `--runner`, `--runner-version`, `--tricks`/`-t`, `--latencyflex/--no-latencyflex`, `--uri-scheme` | Registers an application. If EXE path omitted, resolves from auto-detected apps. | `cheapwine add steam` |
| **`cheapwine remove`**| `<name>` | Removes an application definition. | `cheapwine remove steam` |
| **`cheapwine list`** | `--all` / `-a`, `--detected` / `-d` | Lists registered and/or auto-detected applications. | `cheapwine list --all` |
| **`cheapwine export`**| `<name>`, `--uri-scheme` | Generates a desktop launcher in the host Linux applications menu and registers URI protocols. | `cheapwine export "RetroGame" --uri-scheme myapp` |
| **`cheapwine unexport`**| `<name>` | Removes an exported desktop launcher and associated URI handlers from the host. | `cheapwine unexport "RetroGame"` |
| **`cheapwine wine`** | `[wine_args...]` | Runs a Wine utility in the prefix context. Defaults to `winecfg`. | `cheapwine wine regedit` |
| **`cheapwine winetricks`**| `[tricks_args...]` | Runs `winetricks` inside the local prefix context. | `cheapwine winetricks corefonts` |
| **`cheapwine chocolatey`**| `[choco_args...]` | Runs Chocolatey commands inside the local prefix context (auto-installs if missing). | `cheapwine chocolatey install firefox` |
| **`cheapwine env`** | *None* | Prints shell environment exports to manually hook your terminal into the prefix. | `cheapwine env` |
| **`cheapwine uri`** | `<URL>` | Handles a URI from the host system via the exported application's protocol. | `cheapwine uri myapp://args` |
| **`cheapwine easydistill`**| *None* | Launches the interactive TUI configuration editor for `distillery.json`. | `cheapwine easydistill` |

---

## Development & Testing

### Running Tests
To run the full suite of unit and integration tests (uses `click.testing.CliRunner` and mocks Wine processes for speed):

```bash
python3 -m unittest discover -s tests
```

---

## Publishing to PyPI

This project is configured to publish automatically to PyPI via GitHub Actions using **Trusted Publishing (OIDC)**.

### How to Release a New Version
1. Create and push a version tag matching `v*` (e.g. `v0.1.0`):
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
2. The workflow will automatically extract the version (stripping the leading `v`), write it into `pyproject.toml`, build the distribution packages, and publish to PyPI.

Alternatively, you can trigger the build manually from the GitHub Actions tab, selecting a custom version override if desired.

---

## License

MIT License. See [LICENSE](LICENSE) (if present) for details.
