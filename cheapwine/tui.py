import os
import sys
import termios
import tty
from pathlib import Path
from typing import Any, Dict, List, Optional
import click

from cheapwine.project import Project
from cheapwine.wine import execute_command, set_app_win_version, get_wine_prefix_path
from cheapwine.utils import console, print_info, print_step, print_warning, print_error

def scan_installed_apps(project: Project) -> List[Dict[str, Any]]:
    """Scans for installed applications in this prefix by reading Wine-created desktop files and C: drive."""
    apps = []
    
    # 1. Scan Wine desktop files
    desktop_dir = Path("~/.local/share/applications/wine/Programs").expanduser()
    prefix_abs_str = str(project.prefix_path.absolute())
    
    if desktop_dir.exists():
        for path in desktop_dir.rglob("*.desktop"):
            try:
                content = path.read_text(encoding="utf-8")
                # Check if it references this WINEPREFIX
                if prefix_abs_str in content:
                    name = ""
                    exe = ""
                    for line in content.splitlines():
                        if line.startswith("Name="):
                            name = line.split("=", 1)[1].strip()
                        elif line.startswith("Exec="):
                            exec_val = line.split("=", 1)[1].strip()
                            if "start.exe /Unix" in exec_val:
                                unix_path = exec_val.split("start.exe /Unix", 1)[1].strip()
                                unix_path = unix_path.replace("\\ ", " ")
                                if unix_path.startswith('"') and unix_path.endswith('"'):
                                    unix_path = unix_path[1:-1]
                                exe = unix_path
                            elif "wine" in exec_val:
                                parts = exec_val.split("wine", 1)[1].strip().split()
                                if parts:
                                    exe = parts[0].replace("\\\\", "\\").replace("\\ ", " ")
                    
                    if name and exe:
                        apps.append({
                            "name": name,
                            "exe": exe,
                            "source": "Wine Start Menu"
                        })
            except Exception:
                pass

    # 2. Scan drive_c Program Files and Program Files (x86) for common exe files
    c_drive = project.prefix_path / "drive_c"
    if c_drive.exists():
        search_paths = [c_drive / "Program Files", c_drive / "Program Files (x86)"]
        for sp in search_paths:
            if sp.exists():
                for root, dirs, files in os.walk(sp):
                    depth = len(Path(root).relative_to(sp).parts)
                    if depth > 3:
                        dirs.clear() # don't go deeper
                        continue
                    for f in files:
                        if f.lower().endswith(".exe"):
                            f_lower = f.lower()
                            if any(k in f_lower for k in ["uninstall", "uninst", "setup", "helper", "crash", "updater", "patcher"]):
                                continue
                            exe_path = Path(root) / f
                            # Avoid duplicates from desktop scanning
                            if not any(Path(a["exe"]).name.lower() == f_lower for a in apps):
                                apps.append({
                                    "name": exe_path.stem,
                                    "exe": str(exe_path.absolute()),
                                    "source": "C:\\Program Files"
                                })
                                
    return apps

def launch_option(project: Project, option: Dict[str, Any]):
    """Launches the selected app option."""
    exe_path = option["exe"]
    app_args = option["args"]
    env = option["env"]
    workdir = option["workdir"]
    win_ver = option["win_version"]
    wine_arch = option["arch"]
    latencyflex = option.get("latencyflex")
    
    if win_ver:
        set_app_win_version(project, exe_path, win_ver, wine_arch_override=wine_arch)
        
    combined_args = [exe_path] + app_args
    print_info("Running", f"[accent]{option['name']}[/accent] -> [bold]{exe_path}[/bold]")
    
    exit_code = execute_command(project, combined_args, app_env=env, workdir=workdir, wine_arch_override=wine_arch, latencyflex_override=latencyflex)
    sys.exit(exit_code)

def run_tui(project: Project):
    """Launches the interactive Terminal UI to select and run apps."""
    config = project.load_config()
    registered = config.get("apps", {})
    
    with console.status("[bold green]Scanning for installed applications..."):
        detected = scan_installed_apps(project)
        
    options = []
    # Add registered apps
    for name, app_info in registered.items():
        options.append({
            "id": name,
            "name": name,
            "exe": app_info.get("exe"),
            "type": "Registered",
            "arch": app_info.get("wine_arch"),
            "win_version": app_info.get("win_version"),
            "args": app_info.get("args", []),
            "env": app_info.get("env", {}),
            "workdir": app_info.get("workdir"),
            "latencyflex": app_info.get("latencyflex")
        })
        
    # Add detected apps that are not already registered
    for app in detected:
        if not any(opt["exe"] == app["exe"] for opt in options):
            options.append({
                "id": None,
                "name": app["name"],
                "exe": app["exe"],
                "type": f"Detected ({app['source']})",
                "arch": None,
                "win_version": None,
                "args": [],
                "env": {},
                "workdir": None
            })
            
    if not options:
        print_info("Empty", "No applications found. Add one with [command]cheapwine add[/command] or run an installer.")
        return
        
    selected_index = 0
    fd = sys.stdin.fileno()
    
    if not os.isatty(fd):
        # Fallback to listing and prompt
        console.print("[bold]Select an application to run:[/bold]")
        for idx, opt in enumerate(options):
            console.print(f"[{idx}] {opt['name']} ({opt['type']}) -> {opt['exe']}")
        val = click.prompt("Enter number", type=int, default=0)
        if 0 <= val < len(options):
            launch_option(project, options[val])
        return

    old_settings = termios.tcgetattr(fd)
    
    # Hide cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    
    try:
        while True:
            from rich import box
            from rich.panel import Panel
            from rich.table import Table
            
            table = Table(
                box=box.ROUNDED,
                show_header=True,
                header_style="bold bright_cyan",
                border_style="bright_blue",
                padding=(0, 1),
            )
            table.add_column("", width=3)
            table.add_column("Application Name", style="bold")
            table.add_column("Type", style="dim")
            table.add_column("Executable Path")
            
            for idx, opt in enumerate(options):
                is_selected = (idx == selected_index)
                pointer = "▸" if is_selected else " "
                row_style = "reverse" if is_selected else ""
                
                table.add_row(
                    pointer,
                    opt["name"],
                    opt["type"],
                    opt["exe"],
                    style=row_style,
                )
                
            panel = Panel(
                table,
                title="[bold bright_cyan] cheapwine Distillery [/bold bright_cyan]",
                subtitle=" [dim]↑↓[/dim] Navigate  [dim]↵[/dim] Launch  [dim]Q[/dim] Quit ",
                border_style="bright_blue",
                padding=(1, 2),
            )
            
            sys.stdout.write("\033[H\033[J") # Clear screen
            console.print(panel)
            
            # Read key
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b': # Escape sequence
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': # Up arrow
                        selected_index = (selected_index - 1) % len(options)
                    elif ch3 == 'B': # Down arrow
                        selected_index = (selected_index + 1) % len(options)
            elif ch == '\r' or ch == '\n': # Enter
                break
            elif ch == 'q' or ch == 'Q' or ch == '\x1b': # Quit
                selected_index = -1
                break
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        
    if selected_index != -1:
        launch_option(project, options[selected_index])

def get_available_runners() -> List[str]:
    """Helper to detect and list available runners on the system and locally."""
    runners = ["wine"]
    
    import shutil
    if shutil.which("wine64"):
        runners.append("wine64")
        
    from cheapwine.runners import RUNNERS_DIR
    if RUNNERS_DIR.exists():
        for item in RUNNERS_DIR.iterdir():
            if item.is_dir():
                runners.append(item.name)
                
    for r in ["proton-ge", "wine-ge", "kron4ek", "soda", "wine-d2d1"]:
        if r not in runners:
            runners.append(r)
            
    steam_paths = [
        Path("~/.steam/steam/compatibilitytools.d").expanduser(),
        Path("~/.local/share/Steam/compatibilitytools.d").expanduser(),
        Path("~/.var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d").expanduser(),
    ]
    for sp in steam_paths:
        if sp.exists():
            for item in sp.iterdir():
                if item.is_dir():
                    wine_bin = item / "files" / "bin" / "wine"
                    if wine_bin.exists():
                        runners.append(str(wine_bin.absolute()))
                    else:
                        wine64_bin = item / "files" / "bin" / "wine64"
                        if wine64_bin.exists():
                            runners.append(str(wine64_bin.absolute()))
                            
    return list(dict.fromkeys(runners))

def run_easydistill(project: Project):
    """Launches the interactive TUI configuration editor for distillery.json."""
    if not project.exists():
        print_error("Project is not initialized. Run 'cheapwine init' first.")
        sys.exit(1)
        
    try:
        fd = sys.stdin.fileno()
        is_tty = os.isatty(fd)
    except Exception:
        is_tty = os.environ.get("CHEAPWINE_TESTING") == "1"
        fd = 0
        
    if not is_tty:
        print_error("EasyDistill TUI requires an interactive TTY terminal.")
        sys.exit(1)
        
    # Mock settings if termios throws an error (e.g. in test environments)
    try:
        old_settings = termios.tcgetattr(fd)
    except Exception:
        old_settings = None
    
    # Helper to read text input safely by temporarily leaving raw mode
    def read_text_input(prompt_text: str, default_val: str = "") -> str:
        if old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?25h") # Show cursor
        sys.stdout.flush()
        val = click.prompt(prompt_text, default=default_val, show_default=True)
        sys.stdout.write("\033[?25l") # Hide cursor
        sys.stdout.flush()
        if old_settings is not None:
            tty.setraw(fd)
        return val.strip()

    def select_from_list(title: str, choices: List[str], current: Optional[str] = None) -> Optional[str]:
        sel_idx = 0
        if current in choices:
            sel_idx = choices.index(current)
            
        while True:
            from rich import box
            from rich.panel import Panel
            from rich.table import Table
            
            table = Table(
                box=box.ROUNDED,
                show_header=False,
                border_style="bright_blue",
                padding=(0, 1),
            )
            table.add_column("", width=3)
            table.add_column("Option")
            
            for idx, choice in enumerate(choices):
                is_selected = (idx == sel_idx)
                pointer = "▸" if is_selected else " "
                row_style = "reverse" if is_selected else ""
                
                label = choice
                if choice == current:
                    label = f"{choice} [dim](current)[/dim]"
                table.add_row(pointer, label, style=row_style)
                
            panel = Panel(
                table,
                title=f"[bold bright_cyan] Select {title} [/bold bright_cyan]",
                subtitle=" [dim]↑↓[/dim] Navigate  [dim]↵[/dim] Confirm  [dim]ESC[/dim] Cancel ",
                border_style="bright_blue",
                padding=(1, 2),
            )
            
            sys.stdout.write("\033[H\033[J") # Clear screen
            console.print(panel)
            
            ch = sys.stdin.read(1)
            if not ch:
                return None
            if ch == '\x1b': # Escape or arrow key
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': # Up
                        sel_idx = (sel_idx - 1) % len(choices)
                    elif ch3 == 'B': # Down
                        sel_idx = (sel_idx + 1) % len(choices)
                else: # Escape pressed alone
                    return None
            elif ch == 'q' or ch == 'Q':
                return None
            elif ch == '\r' or ch == '\n': # Enter
                return choices[sel_idx]

    # Hide cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    
    # State variables
    state = "MAIN"
    selected_index = 0
    
    # For sub-menus
    selected_app_name = None
    
    try:
        if old_settings is not None:
            tty.setraw(fd)
        while True:
            # Load config freshly each loop to ensure we have latest edits
            config = project.load_config()
            
            # Define options based on current state
            options = []
            menu_title = ""
            menu_subtitle = "Use UP/DOWN arrows, ENTER to select/modify, ESC/q to go back"
            
            if state == "MAIN":
                menu_title = "Main Menu"
                options = [
                    {"label": "Global Configuration", "action": "go_global"},
                    {"label": "Manage Applications", "action": "go_apps"},
                    {"label": "Save & Exit TUI", "action": "exit"}
                ]
            elif state == "GLOBAL":
                menu_title = "Global Settings"
                arch = config.get("wine_arch", "win64")
                win_ver = config.get("win_version", "win10")
                runner = config.get("runner", "wine")
                runner_ver = config.get("runner_version", "None")
                tricks = ", ".join(config.get("winetricks", [])) or "None"
                latencyflex = "Enabled" if config.get("latencyflex", False) else "Disabled"
                
                options = [
                    {"label": f"Wine Architecture: [accent]{arch}[/accent]", "action": "edit_global_arch"},
                    {"label": f"Windows Version: [accent]{win_ver}[/accent]", "action": "edit_global_win_ver"},
                    {"label": f"Wine Runner: [accent]{runner}[/accent]", "action": "edit_global_runner"},
                    {"label": f"Runner Version: [accent]{runner_ver}[/accent]", "action": "edit_global_runner_ver"},
                    {"label": f"Global Winetricks: [accent]{tricks}[/accent]", "action": "edit_global_tricks"},
                    {"label": f"LatencyFleX Support: [accent]{latencyflex}[/accent]", "action": "edit_global_latencyflex"},
                    {"label": "➔ Back to Main Menu", "action": "go_main"}
                ]
            elif state == "APPS_LIST":
                menu_title = "Applications Registry"
                apps = config.get("apps", {})
                for app_name, app_info in apps.items():
                    exe_name = Path(app_info.get("exe", "")).name
                    options.append({
                        "label": f"Edit: [accent]{app_name}[/accent] ({exe_name})",
                        "action": "edit_app",
                        "app_name": app_name
                    })
                options.append({"label": "[+] Register a New Application", "action": "add_app"})
                options.append({"label": "➔ Back to Main Menu", "action": "go_main"})
            elif state == "EDIT_APP":
                menu_title = f"Edit Application: {selected_app_name}"
                app_info = config.get("apps", {}).get(selected_app_name, {})
                if not app_info:
                    state = "APPS_LIST"
                    selected_index = 0
                    continue
                    
                exe = app_info.get("exe", "")
                args_str = " ".join(app_info.get("args", [])) or "None"
                workdir = app_info.get("workdir") or "None"
                win_ver = app_info.get("win_version") or "None (inherits global)"
                arch = app_info.get("wine_arch") or "None (inherits global)"
                runner = app_info.get("runner") or "None (inherits global)"
                runner_ver = app_info.get("runner_version") or "None (inherits global)"
                tricks = ", ".join(app_info.get("winetricks", [])) or "None (inherits global)"
                env_count = len(app_info.get("env", {}))
                lfx = app_info.get("latencyflex")
                if lfx is True:
                    lfx_str = "Enabled"
                elif lfx is False:
                    lfx_str = "Disabled"
                else:
                    lfx_str = "None (inherits global)"
                uri_schemes_str = ", ".join(app_info.get("uri_schemes", [])) or "None"
                
                options = [
                    {"label": f"Application Name: [accent]{selected_app_name}[/accent]", "action": "edit_app_name"},
                    {"label": f"Executable Path (exe): [accent]{exe}[/accent]", "action": "edit_app_exe"},
                    {"label": f"Arguments (args): [accent]{args_str}[/accent]", "action": "edit_app_args"},
                    {"label": f"Working Directory (workdir): [accent]{workdir}[/accent]", "action": "edit_app_workdir"},
                    {"label": f"Windows Version Override: [accent]{win_ver}[/accent]", "action": "edit_app_win_ver"},
                    {"label": f"Wine Arch Override: [accent]{arch}[/accent]", "action": "edit_app_arch"},
                    {"label": f"Wine Runner Override: [accent]{runner}[/accent]", "action": "edit_app_runner"},
                    {"label": f"Runner Version Override: [accent]{runner_ver}[/accent]", "action": "edit_app_runner_ver"},
                    {"label": f"Winetricks Override: [accent]{tricks}[/accent]", "action": "edit_app_tricks"},
                    {"label": f"Environment Variables: [accent]{env_count} keys[/accent]", "action": "edit_app_env"},
                    {"label": f"LatencyFleX Override: [accent]{lfx_str}[/accent]", "action": "edit_app_latencyflex"},
                    {"label": f"URI Schemes: [accent]{uri_schemes_str}[/accent]", "action": "edit_app_uri_schemes"},
                    {"label": "[!] Delete Application from Registry", "action": "delete_app"},
                    {"label": "➔ Back to Applications List", "action": "go_apps"}
                ]
            elif state == "EDIT_APP_ENV":
                menu_title = f"{selected_app_name} > Environment Variables"
                app_info = config.get("apps", {}).get(selected_app_name, {})
                env = app_info.get("env", {})
                for k, v in env.items():
                    options.append({
                        "label": f"{k} = [accent]{v}[/accent]",
                        "action": "edit_env_key",
                        "key": k,
                        "value": v
                    })
                options.append({"label": "[+] Add New Environment Variable", "action": "add_env_key"})
                options.append({"label": "➔ Back to Edit Application", "action": "go_edit_app"})
                
            # Clamp index
            selected_index = max(0, min(selected_index, len(options) - 1))
            
            # Draw screen
            from rich import box
            from rich.panel import Panel
            from rich.table import Table
            
            table = Table(
                box=box.ROUNDED,
                show_header=False,
                border_style="bright_blue",
                padding=(0, 1),
            )
            table.add_column("", width=3)
            table.add_column("Option")
            
            for idx, opt in enumerate(options):
                is_selected = (idx == selected_index)
                pointer = "▸" if is_selected else " "
                row_style = "reverse" if is_selected else ""
                table.add_row(pointer, opt["label"], style=row_style)
                
            panel = Panel(
                table,
                title=f"[bold bright_cyan] cheapwine EasyDistill [/bold bright_cyan] > [bold]{menu_title}[/bold]",
                subtitle=menu_subtitle,
                border_style="bright_blue",
                padding=(1, 2),
            )
            
            sys.stdout.write("\033[H\033[J") # Clear screen
            console.print(panel)
            
            # Read key input
            ch = sys.stdin.read(1)
            if not ch:
                break
            if ch == '\x1b': # Escape or arrow key
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A': # Up
                        selected_index = (selected_index - 1) % len(options)
                    elif ch3 == 'B': # Down
                        selected_index = (selected_index + 1) % len(options)
                else: # Escape pressed alone
                    # Go back one menu level
                    if state == "GLOBAL" or state == "APPS_LIST":
                        state = "MAIN"
                        selected_index = 0
                    elif state == "EDIT_APP":
                        state = "APPS_LIST"
                        selected_index = 0
                    elif state == "EDIT_APP_ENV":
                        state = "EDIT_APP"
                        selected_index = 9
                    elif state == "MAIN":
                        break
            elif ch == 'q' or ch == 'Q':
                if state == "MAIN":
                    break
                elif state == "GLOBAL" or state == "APPS_LIST":
                    state = "MAIN"
                    selected_index = 0
                elif state == "EDIT_APP":
                    state = "APPS_LIST"
                    selected_index = 0
                elif state == "EDIT_APP_ENV":
                    state = "EDIT_APP"
                    selected_index = 9
            elif ch == '\r' or ch == '\n': # Enter / Confirm
                opt = options[selected_index]
                action = opt["action"]
                
                if action == "exit":
                    break
                elif action == "go_global":
                    state = "GLOBAL"
                    selected_index = 0
                elif action == "go_apps":
                    state = "APPS_LIST"
                    selected_index = 0
                elif action == "go_main":
                    state = "MAIN"
                    selected_index = 0
                elif action == "go_edit_app":
                    state = "EDIT_APP"
                    selected_index = 9
                elif action == "edit_app":
                    state = "EDIT_APP"
                    selected_app_name = opt["app_name"]
                    selected_index = 0
                elif action == "edit_app_env":
                    state = "EDIT_APP_ENV"
                    selected_index = 0
                    
                # Global modification actions
                elif action == "edit_global_arch":
                    current = config.get("wine_arch", "win64")
                    selected = select_from_list("Wine Architecture", ["win64", "win32"], current)
                    if selected:
                        config["wine_arch"] = selected
                        project.save_config(config)
                elif action == "edit_global_win_ver":
                    versions = ["win10", "win81", "win8", "win7", "winxp", "win2k", "win98", "win95"]
                    current = config.get("win_version", "win10")
                    selected = select_from_list("Windows Version", versions, current)
                    if selected:
                        config["win_version"] = selected
                        project.save_config(config)
                elif action == "edit_global_runner":
                    current = config.get("runner", "wine")
                    available = get_available_runners()
                    choices = ["[Custom Runner (Type manually)]"] + available
                    selected = select_from_list("Global Wine Runner", choices, current)
                    if selected:
                        if selected == "[Custom Runner (Type manually)]":
                            val = read_text_input("Enter Global Wine Runner", current)
                            if val:
                                config["runner"] = val
                                project.save_config(config)
                        else:
                            config["runner"] = selected
                            project.save_config(config)
                elif action == "edit_global_runner_ver":
                    current = config.get("runner_version", "")
                    val = read_text_input("Enter Runner Version (leave empty to clear)", current)
                    if val:
                        config["runner_version"] = val
                    elif "runner_version" in config:
                        del config["runner_version"]
                    project.save_config(config)
                elif action == "edit_global_tricks":
                    current = ", ".join(config.get("winetricks", []))
                    val = read_text_input("Enter comma-separated global winetricks components", current)
                    config["winetricks"] = [c.strip() for c in val.split(",") if c.strip()]
                    project.save_config(config)
                elif action == "edit_global_latencyflex":
                    current = "Enabled" if config.get("latencyflex", False) else "Disabled"
                    selected = select_from_list("LatencyFleX Support", ["Enabled", "Disabled"], current)
                    if selected:
                        config["latencyflex"] = (selected == "Enabled")
                        project.save_config(config)
                    
                # App registration
                elif action == "add_app":
                    with console.status("[bold green]Scanning for installed applications..."):
                        detected = scan_installed_apps(project)
                        
                    choices = ["[Custom Application (Type manually)]"]
                    for app in detected:
                        choices.append(f"{app['name']} ({app['source']})")
                        
                    selected = select_from_list("New Application Source", choices)
                    if selected:
                        if selected == "[Custom Application (Type manually)]":
                            app_name = read_text_input("Enter new application registry name")
                            if app_name:
                                exe_path = read_text_input("Enter executable path (.exe)")
                                if exe_path:
                                    project.add_app(app_name, exe_path)
                                    selected_app_name = app_name
                                    state = "EDIT_APP"
                                    selected_index = 0
                        else:
                            # User selected an auto-detected app
                            # Find the app definition in detected list
                            app_idx = choices.index(selected) - 1
                            app = detected[app_idx]
                            
                            # Let the user confirm or edit the application registry name
                            app_name = read_text_input("Confirm or edit application registry name", app["name"])
                            if app_name:
                                project.add_app(app_name, app["exe"])
                                selected_app_name = app_name
                                state = "EDIT_APP"
                                selected_index = 0
                            
                # App deletion
                elif action == "delete_app":
                    confirm = read_text_input(f"Are you sure you want to delete '{selected_app_name}'? (y/N)", "N")
                    if confirm.lower() in ["y", "yes"]:
                        project.remove_app(selected_app_name)
                        state = "APPS_LIST"
                        selected_index = 0
                        
                # App specific modification actions
                elif action == "edit_app_name":
                    new_name = read_text_input("Enter new name for the application", selected_app_name)
                    if new_name and new_name != selected_app_name:
                        apps = config.get("apps", {})
                        if new_name in apps:
                            read_text_input("Error: Name already exists. Press Enter to continue...")
                        else:
                            apps[new_name] = apps.pop(selected_app_name)
                            project.save_config(config)
                            selected_app_name = new_name
                elif action == "edit_app_exe":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = app_info.get("exe", "")
                    val = read_text_input("Enter Executable Path", current)
                    if val:
                        app_info["exe"] = val
                        project.save_config(config)
                elif action == "edit_app_args":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = " ".join(app_info.get("args", []))
                    val = read_text_input("Enter space-separated arguments", current)
                    import shlex
                    app_info["args"] = shlex.split(val)
                    project.save_config(config)
                elif action == "edit_app_workdir":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = app_info.get("workdir", "")
                    val = read_text_input("Enter Working Directory path (leave empty to clear)", current)
                    if val:
                        app_info["workdir"] = val
                    elif "workdir" in app_info:
                        del app_info["workdir"]
                    project.save_config(config)
                elif action == "edit_app_win_ver":
                    versions = ["None", "win10", "win81", "win8", "win7", "winxp", "win2k", "win98", "win95"]
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = app_info.get("win_version", "None")
                    selected = select_from_list("App Windows Version Override", versions, current)
                    if selected:
                        if selected == "None":
                            if "win_version" in app_info:
                                del app_info["win_version"]
                        else:
                            app_info["win_version"] = selected
                        project.save_config(config)
                elif action == "edit_app_arch":
                    arches = ["None", "win64", "win32"]
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = app_info.get("wine_arch", "None")
                    selected = select_from_list("App Wine Arch Override", arches, current)
                    if selected:
                        if selected == "None":
                            if "wine_arch" in app_info:
                                del app_info["wine_arch"]
                        else:
                            app_info["wine_arch"] = selected
                        project.save_config(config)
                elif action == "edit_app_runner":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = app_info.get("runner", "")
                    available = get_available_runners()
                    choices = ["[Inherit Global] (None)", "[Custom Runner (Type manually)]"] + available
                    current_choice = current if current else "[Inherit Global] (None)"
                    selected = select_from_list("App Wine Runner Override", choices, current_choice)
                    if selected:
                        if selected == "[Inherit Global] (None)":
                            if "runner" in app_info:
                                del app_info["runner"]
                            project.save_config(config)
                        elif selected == "[Custom Runner (Type manually)]":
                            val = read_text_input("Enter Runner Override (leave empty to clear)", current)
                            if val:
                                app_info["runner"] = val
                            elif "runner" in app_info:
                                del app_info["runner"]
                            project.save_config(config)
                        else:
                            app_info["runner"] = selected
                            project.save_config(config)
                elif action == "edit_app_runner_ver":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = app_info.get("runner_version", "")
                    val = read_text_input("Enter Runner Version Override (leave empty to clear)", current)
                    if val:
                        app_info["runner_version"] = val
                    elif "runner_version" in app_info:
                        del app_info["runner_version"]
                    project.save_config(config)
                elif action == "edit_app_tricks":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = ", ".join(app_info.get("winetricks", []))
                    val = read_text_input("Enter comma-separated winetricks components (leave empty to clear)", current)
                    components = [c.strip() for c in val.split(",") if c.strip()]
                    if components:
                        app_info["winetricks"] = components
                    elif "winetricks" in app_info:
                        del app_info["winetricks"]
                    project.save_config(config)
                elif action == "edit_app_latencyflex":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    lfx = app_info.get("latencyflex")
                    current = "Enabled" if lfx is True else "Disabled" if lfx is False else "None (inherits global)"
                    selected = select_from_list("App LatencyFleX Override", ["None (inherits global)", "Enabled", "Disabled"], current)
                    if selected:
                        if selected == "None (inherits global)":
                            if "latencyflex" in app_info:
                                del app_info["latencyflex"]
                        else:
                            app_info["latencyflex"] = (selected == "Enabled")
                        project.save_config(config)
                elif action == "edit_app_uri_schemes":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    current = ", ".join(app_info.get("uri_schemes", []))
                    val = read_text_input("Enter comma-separated URI schemes (e.g. myapp, myapp2)", current)
                    schemes = [s.strip() for s in val.split(",") if s.strip()]
                    if schemes:
                        app_info["uri_schemes"] = schemes
                    elif "uri_schemes" in app_info:
                        del app_info["uri_schemes"]
                    project.save_config(config)
                    from cheapwine.cli import _sync_app_desktop
                    _sync_app_desktop(project, selected_app_name)
                    
                # App specific env actions
                elif action == "edit_env_key":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    env = app_info.get("env", {})
                    key = opt["key"]
                    value = opt["value"]
                    
                    choice = read_text_input(f"Edit value or delete? [1] Edit [2] Delete (default: 1)", "1")
                    if choice == "2":
                        del env[key]
                        project.save_config(config)
                    else:
                        new_val = read_text_input(f"Enter value for {key}", value)
                        env[key] = new_val
                        project.save_config(config)
                elif action == "add_env_key":
                    app_info = config.get("apps", {}).get(selected_app_name, {})
                    if "env" not in app_info:
                        app_info["env"] = {}
                    env = app_info["env"]
                    key = read_text_input("Enter new Environment Variable Key")
                    if key:
                        val = read_text_input(f"Enter value for {key}")
                        env[key] = val
                        project.save_config(config)
                        
    finally:
        sys.stdout.write("\033[?25h") # Show cursor
        sys.stdout.flush()
        if old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
