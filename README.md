# 🍷 cheapwine

A project-local Wine prefix and application manager (Wine's version of `uv`). 

`cheapwine` brings modern, declarative, and fast workflow management to Wine environments. Instead of managing a bloated directory of global prefixes (like Lutris or Bottles), `cheapwine` isolates prefixes directly inside your project folders and exposes a clean, git-friendly configuration file named `distillery.json`.

---

## Key Features

* **Project-Local Prefixes**: Automatically sandboxes your Wine environments in `.cheapwine` inside your project directory.
* **Declarative Distillery Settings (`distillery.json`)**: Declare architectures, Windows versions, environment variables, and application commands in a single, portable JSON file.
* **Runner Overrides**: Use system Wine, Proton (via Steam), Wine-GE, Bottles, or custom-compiled Wine builds, both globally and overridden per application.
* **Legacy 32-bit Support**: Create isolated 32-bit Wine prefixes (`win32`) on the fly, even for individual applications in a 64-bit project.
* **Auto-Integration Spam Block**: Prevents Wine from cluttering your Linux host's desktop search menu during app installation by disabling `winemenubuilder` by default.
* **Manual Desktop Export**: Clean CLI tools (`cheapwine export` / `cheapwine unexport`) to manually generate standard Linux desktop launchers (`.desktop` entries) for only the applications you want.
* **Auto-Discovery Scanner**: Scans Wine Start Menu shortcuts and `drive_c/Program Files` to automatically detect newly installed programs.
* **Beautiful CLI & Interactive TUI**: Features a clean, colorful, emoji-rich command-line output (inspired by `uv`) and a live interactive Terminal User Interface (TUI) menu for select-and-run workflows.

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

---

## Command Reference

| Command | Options | Description | Example |
| :--- | :--- | :--- | :--- |
| **`cheapwine init`** | `--arch [win32\|win64]`, `--win-version [win95\|winxp\|win7\|win10]`, `--runner [path]` | Creates `distillery.json` and initializes the Wine prefix. | `cheapwine init --arch win32 --win-version win95` |
| **`cheapwine run`** | `[app_or_exe]`, `[extra_args...]` | Runs a registered app or an executable path. Launches the TUI if no app is specified. | `cheapwine run notepad` |
| **`cheapwine tui`** | *None* | Launches the interactive arrow-key select menu. | `cheapwine tui` |
| **`cheapwine add`** | `--env`, `--workdir`, `--win-version`, `--arch`, `--runner` | Registers an application. If the executable path is omitted, resolves it from auto-detected apps. | `cheapwine add steam` |
| **`cheapwine remove`**| `[app_name]` | Removes an application definition. | `cheapwine remove steam` |
| **`cheapwine list`** | `--all` / `-a`, `--detected` / `-d` | Lists registered and/or auto-detected applications. | `cheapwine list --all` |
| **`cheapwine export`**| `[app_name]` | Generates a desktop launcher in the host Linux applications menu. | `cheapwine export "RetroGame"` |
| **`cheapwine unexport`**| `[app_name]` | Removes an exported desktop launcher from the host. | `cheapwine unexport "RetroGame"` |
| **`cheapwine wine`** | `[wine_args...]` | Runs a Wine utility in the prefix context. Defaults to `winecfg`. | `cheapwine wine regedit` |
| **`cheapwine winetricks`**| `[tricks_args...]` | Runs `winetricks` inside the local prefix context. | `cheapwine winetricks corefonts` |
| **`cheapwine env`** | *None* | Prints shell export commands to manually hook your terminal into the prefix. | `cheapwine env` |

---

## Development & Testing

### Running Tests
To run the full suite of unit and integration tests (uses `click.testing.CliRunner` and mocks Wine processes for speed):

```bash
python3 -m unittest discover -s tests
```

---

## License

MIT License. See [LICENSE](LICENSE) (if present) for details.
