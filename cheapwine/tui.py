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
    
    if win_ver:
        set_app_win_version(project, exe_path, win_ver, wine_arch_override=wine_arch)
        
    combined_args = [exe_path] + app_args
    print_info("Running", f"[accent]{option['name']}[/accent] -> [bold]{exe_path}[/bold]")
    
    exit_code = execute_command(project, combined_args, app_env=env, workdir=workdir, wine_arch_override=wine_arch)
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
            "workdir": app_info.get("workdir")
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
            from rich.panel import Panel
            from rich.table import Table
            
            table = Table(box=None, show_header=True, header_style="bold blue")
            table.add_column("", width=3)
            table.add_column("Application Name", style="bold")
            table.add_column("Type", style="dim")
            table.add_column("Executable Path")
            
            for idx, opt in enumerate(options):
                is_selected = (idx == selected_index)
                pointer = "➔" if is_selected else ""
                style = "bold green" if is_selected else ""
                
                table.add_row(
                    pointer,
                    opt["name"],
                    opt["type"],
                    opt["exe"],
                    style=style
                )
                
            panel = Panel(
                table,
                title="[bold accent] cheapwine Distillery [/bold accent]",
                subtitle="Use [bold]UP/DOWN[/bold] arrows, [bold]ENTER[/bold] to run, [bold]q/ESC[/bold] to quit",
                border_style="blue"
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
