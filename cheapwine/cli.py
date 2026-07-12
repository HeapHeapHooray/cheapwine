import click
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional

from cheapwine import __version__
from cheapwine.project import Project
from cheapwine.wine import init_prefix, execute_command, sync_prefix_settings, set_app_win_version, get_wine_prefix_path
from cheapwine.utils import console, print_info, print_step, print_error, print_warning

def ensure_project(start_dir: Path = None, auto_init: bool = False) -> Project:
    """Helper to find or initialize a project."""
    project = Project.find_project(start_dir)
    if not project:
        if auto_init:
            project = Project.get_or_create_project(start_dir)
            print_info("Init", f"No project found. Initializing new cheapwine project in [accent]{project.root_dir}[/accent]...")
            project.init_project_files()
            init_prefix(project)
        else:
            print_error("No cheapwine project found. Run [command]cheapwine init[/command] to start one.")
            sys.exit(1)
    return project

@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show the version and exit.")
@click.pass_context
def cli(ctx: click.Context, version: bool):
    """cheapwine: A lightweight, project-based Wine prefix and application manager (Wine's version of uv)."""
    if version:
        console.print(f"[accent]cheapwine[/accent] version [bold]{__version__}[/bold]")
        sys.exit(0)
        
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command()
@click.option("--arch", type=click.Choice(["win32", "win64"]), default="win64", help="Architecture for the Wine prefix.")
@click.option("--force", is_flag=True, help="Force re-initialization of prefix if it exists.")
@click.option("--win-version", help="Windows version to configure (e.g. win95, winxp, win10).")
@click.option("--runner", help="Global Wine runner to use (e.g. wine, proton, or absolute path).")
@click.option("--runner-version", help="Global Wine runner version to use.")
@click.option("--latencyflex/--no-latencyflex", default=None, help="Enable or disable LatencyFleX support.")
def init(arch: str, force: bool, win_version: str, runner: str, runner_version: str, latencyflex: Optional[bool]):
    """Initialize a new cheapwine project in the current directory."""
    project = Project.get_or_create_project()
    
    config_created = False
    config_changed = False
    
    if not project.exists():
        target_win_ver = win_version if win_version else "win10"
        target_runner = runner if runner else "wine"
        target_lfx = latencyflex if latencyflex is not None else False
        config_created = project.init_project_files(wine_arch=arch, win_version=target_win_ver, runner=target_runner, runner_version=runner_version, latencyflex=target_lfx)
        print_step("Created", f"distillery.json default settings")
    else:
        config = project.load_config()
        if win_version and config.get("win_version") != win_version:
            config["win_version"] = win_version
            config_changed = True
        if arch and config.get("wine_arch") != arch:
            config["wine_arch"] = arch
            config_changed = True
        if runner and config.get("runner") != runner:
            config["runner"] = runner
            config_changed = True
        if runner_version and config.get("runner_version") != runner_version:
            config["runner_version"] = runner_version
            config_changed = True
        if latencyflex is not None and config.get("latencyflex") != latencyflex:
            config["latencyflex"] = latencyflex
            config_changed = True
            
        if config_changed:
            project.save_config(config)
            print_step("Updated", f"distillery.json settings")
        else:
            print_warning(f"distillery.json already exists at {project.config_path}")
            
    prefix_created = init_prefix(project, force=force, runner_version_override=runner_version)
    
    # Sync settings if prefix wasn't just created (since creation already calls sync_prefix_settings)
    if not prefix_created:
        sync_prefix_settings(project)
        
    if not prefix_created and not config_created and not config_changed:
        print_info("Skipped", "Project is already fully initialized.")

@cli.command()
def tui():
    """Launch the interactive Terminal UI to select and run apps."""
    project = ensure_project()
    from cheapwine.tui import run_tui
    run_tui(project)

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("app_or_exe", required=False, metavar="[APP_OR_EXE]")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED, metavar="[EXTRA_ARGS...]")
def run(app_or_exe: Optional[str], extra_args: Tuple[str, ...]):
    """Run a registered application or an arbitrary executable.

    [APP_OR_EXE] is the name of a registered application in distillery.json,
    an auto-detected application, or a path to an arbitrary executable. If
    not specified, launches the interactive selection TUI.

    [EXTRA_ARGS...] are optional additional command line arguments passed
    directly to the running application.

    Examples:
      # Run notepad with no extra arguments:
      cheapwine run notepad.exe

      # Run notepad, passing arguments directly to it:
      cheapwine run notepad.exe /p test.txt

      # Run a registered game in windowed mode:
      cheapwine run mygame -windowed -width 1920

      # Run a game forcing DirectX 11 mode:
      cheapwine run mygame -dx11
    """
    project = ensure_project()
    
    if not app_or_exe:
        from cheapwine.tui import run_tui
        run_tui(project)
        return
        
    app_config = project.get_app(app_or_exe)
    is_detected = False
    
    if not app_config:
        from cheapwine.tui import scan_installed_apps
        with console.status("[bold green]Scanning for installed applications..."):
            detected = scan_installed_apps(project)
        for app in detected:
            if app["name"].lower() == app_or_exe.lower():
                app_config = {
                    "exe": app["exe"],
                    "args": [],
                    "env": {},
                }
                app_or_exe = app["name"]
                is_detected = True
                break
    
    if app_config:
        exe_path = app_config.get("exe", "")
        app_win_ver = app_config.get("win_version")
        app_wine_arch = app_config.get("wine_arch")
        app_runner = app_config.get("runner")
        app_runner_version = app_config.get("runner_version")
        app_winetricks = app_config.get("winetricks")
        app_latencyflex = app_config.get("latencyflex")
        if app_win_ver:
            set_app_win_version(project, exe_path, app_win_ver, wine_arch_override=app_wine_arch, runner_override=app_runner, runner_version_override=app_runner_version)
            
        # Merge configuration args with extra args passed from CLI
        app_args = app_config.get("args", [])
        combined_args = [exe_path] + app_args + list(extra_args)
        
        env = app_config.get("env", {})
        workdir = app_config.get("workdir")
        
        source_label = "Auto-detected app" if is_detected else "Registered app"
        print_info("Running", f"{source_label} [accent]{app_or_exe}[/accent] -> [bold]{exe_path}[/bold] {' '.join(combined_args[1:])}")
        exit_code = execute_command(project, combined_args, app_env=env, workdir=workdir, wine_arch_override=app_wine_arch, runner_override=app_runner, runner_version_override=app_runner_version, app_winetricks=app_winetricks, latencyflex_override=app_latencyflex)
    else:
        # Check if it's a file path
        # If it doesn't exist, we still try to execute it in case it's in the Wine path (like notepad)
        combined_args = [app_or_exe] + list(extra_args)
        print_info("Running", f"Executable/Command -> [bold]{app_or_exe}[/bold] {' '.join(extra_args)}")
        exit_code = execute_command(project, combined_args)
        
    sys.exit(exit_code)

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("name", metavar="<NAME>")
@click.argument("exe", required=False, metavar="[EXE_PATH]")
@click.argument("args", nargs=-1, metavar="[ARGS...]")
@click.option("--env", "-e", multiple=True, help="Environment variables in KEY=VALUE format.")
@click.option("--workdir", "-w", help="Working directory for the app.")
@click.option("--win-version", help="App-specific Windows version (e.g. win95, winxp).")
@click.option("--arch", type=click.Choice(["win32", "win64"]), help="App-specific Wine architecture override.")
@click.option("--runner", help="App-specific Wine runner override.")
@click.option("--runner-version", help="App-specific Wine runner version override.")
@click.option("--tricks", "-t", multiple=True, help="App-specific Winetricks components (can specify multiple times).")
@click.option("--latencyflex/--no-latencyflex", default=None, help="Enable or disable LatencyFleX support for this application.")
def add(name: str, exe: Optional[str], args: Tuple[str, ...], env: Tuple[str, ...], workdir: str, win_version: str, arch: str, runner: str, runner_version: str, tricks: Tuple[str, ...], latencyflex: Optional[bool]):
    """Add a new application to distillery.json.

    <NAME> is the unique registry name for the application.

    [EXE_PATH] is the Windows executable (.exe) path. This is required unless
    registering a known auto-detected application by name.

    [ARGS...] are the default arguments to pass to the executable.
    """
    project = ensure_project()
    
    target_exe = exe
    if not target_exe:
        from cheapwine.tui import scan_installed_apps
        with console.status("[bold green]Scanning for installed applications..."):
            detected = scan_installed_apps(project)
        # Try to find a match (case-insensitive)
        match = None
        for app in detected:
            if app["name"].lower() == name.lower():
                match = app
                break
        if match:
            target_exe = match["exe"]
            print_info("Auto-detect", f"Found auto-detected application '{match['name']}' -> [bold]{target_exe}[/bold]")
        else:
            print_error(f"Executable path is required unless registering a known auto-detected application.")
            print_info("Hint", "Use [command]cheapwine list -d[/command] to see auto-detected applications, or specify the path: [command]cheapwine add <name> <exe_path>[/command]")
            sys.exit(1)

    # Parse env key-values
    env_dict = {}
    for item in env:
        if "=" in item:
            k, v = item.split("=", 1)
            env_dict[k.strip()] = v.strip()
        else:
            print_warning(f"Invalid env format '{item}'. Expected KEY=VALUE. Skipping.")
 
    app_config = project.add_app(
        app_name=name,
        exe_path=target_exe,
        args=list(args),
        env=env_dict,
        workdir=workdir,
        win_version=win_version,
        wine_arch=arch,
        runner=runner,
        runner_version=runner_version,
        winetricks=list(tricks),
        latencyflex=latencyflex
    )
    print_step("Added", f"App [accent]{name}[/accent] ([bold]{target_exe}[/bold]) to distillery.json")

@cli.command(name="remove")
@click.argument("name", metavar="<NAME>")
def remove_cmd(name: str):
    """Remove an application from distillery.json.

    <NAME> is the registry name of the application to remove.
    """
    project = ensure_project(auto_init=False)
    if project.remove_app(name):
        print_step("Removed", f"App [accent]{name}[/accent] from distillery.json")
    else:
        print_error(f"App [accent]{name}[/accent] not found in distillery.json")
        sys.exit(1)

@cli.command(name="list")
@click.option("--all", "-a", is_flag=True, help="List both registered and auto-detected applications.")
@click.option("--detected", "-d", is_flag=True, help="List only auto-detected applications.")
def list_cmd(all: bool, detected: bool):
    """List applications in this project."""
    project = ensure_project(auto_init=False)
    
    show_registered = not detected
    show_detected = all or detected
    
    if show_registered:
        config = project.load_config()
        apps = config.get("apps", {})
        if apps:
            console.print("[bold]Registered Applications (distillery.json):[/bold]")
            for name, app_info in apps.items():
                exe = app_info.get("exe", "")
                args = " ".join(app_info.get("args", []))
                args_str = f" args: {args}" if args else ""
                console.print(f"  • [success]{name:<15}[/success] [bold]{exe}[/bold]{args_str}")
        elif not show_detected:
            print_info("Empty", "No applications registered in distillery.json. Hint: Use [command]--all[/command] or [command]-a[/command] to scan for installed apps.")

    if show_detected:
        from cheapwine.tui import scan_installed_apps
        with console.status("[bold green]Scanning for installed applications..."):
            detected_apps = scan_installed_apps(project)
        if detected_apps:
            # Add a spacer if we also showed registered apps
            if show_registered and apps:
                console.print("")
            console.print("[bold]Auto-Detected Applications:[/bold]")
            for app in detected_apps:
                console.print(f"  • [success]{app['name']:<25}[/success] ({app['source']}) -> [bold]{app['exe']}[/bold]")
        else:
            print_info("Scan", "No auto-detected applications found in the Wine prefix.")

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("wine_args", nargs=-1, type=click.UNPROCESSED, metavar="[WINE_ARGS...]")
def wine(wine_args: Tuple[str, ...]):
    """Run Wine commands inside the local prefix context (e.g. winecfg, regedit).

    [WINE_ARGS...] are arguments passed directly to wine (e.g. 'winecfg', 'regedit').
    If no arguments are provided, defaults to running 'winecfg'.
    """
    project = ensure_project()
    if not wine_args:
        # Default to winecfg if no args provided
        args_list = ["winecfg"]
    else:
        args_list = list(wine_args)
        
    print_info("Wine", f"Executing -> [bold]{' '.join(args_list)}[/bold]")
    exit_code = execute_command(project, args_list)
    sys.exit(exit_code)

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("tricks_args", nargs=-1, type=click.UNPROCESSED, metavar="[TRICKS_ARGS...]")
def winetricks(tricks_args: Tuple[str, ...]):
    """Run winetricks in the context of the local prefix.

    [TRICKS_ARGS...] are arguments passed directly to winetricks.
    If no arguments are provided, winetricks launches its graphical GUI.
    """
    project = ensure_project()
    args_list = ["winetricks"] + list(tricks_args)
    if not tricks_args:
        print_info("Winetricks", "Launching Winetricks GUI...")
        print_info("Hint", "In the welcome dialog, choose [accent]'Select the default wineprefix'[/accent] to configure your project's local prefix (./.cheapwine).")
    else:
        print_info("Winetricks", f"Executing -> [bold]{' '.join(args_list)}[/bold]")
    exit_code = execute_command(project, args_list)
    sys.exit(exit_code)

@cli.command()
def env():
    """Print shell environment exports for the local prefix."""
    project = ensure_project()
    config = project.load_config()
    arch = config.get("wine_arch", "win64")
    
    console.print(f"# Run these commands to configure your shell for this Wine prefix:")
    console.print(f"export WINEPREFIX={project.prefix_path.absolute()}")
    console.print(f"export WINEARCH={arch}")
    
    # Print other project level environment variables
    proj_env = config.get("env", {})
    for k, v in proj_env.items():
        console.print(f"export {k}={v}")

def extract_exe_icon(exe_path: Path, icon_name: str) -> bool:
    """Extract application icon from a Windows executable and install it for the host desktop."""
    try:
        import pefile
        from PIL import Image
        import io
    except ImportError as e:
        print_warning(f"Icon extraction requires pefile and Pillow: {e}")
        return False

    icons_dir = Path("~/.local/share/icons").expanduser()

    try:
        pe = pefile.PE(str(exe_path))
    except Exception as e:
        print_warning(f"Could not parse PE file {exe_path}: {e}")
        return False

    try:
        rt_group_icon = [e for e in pe.DIRECTORY_ENTRY_RESOURCE.entries if e.id == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]]
        if not rt_group_icon:
            print_info("Icon", "No RT_GROUP_ICON resources found in executable")
            return False
        rt_icon = [e for e in pe.DIRECTORY_ENTRY_RESOURCE.entries if e.id == pefile.RESOURCE_TYPE["RT_ICON"]]
        if not rt_icon:
            print_info("Icon", "No RT_ICON resources found in executable")
            return False

        print_info("Icon", f"Found {len(rt_group_icon)} group icon(s), {sum(len(list(t.directory.entries)) for t in rt_icon)} total icon(s)")

        # Build .ico file from RT_GROUP_ICON and RT_ICON resources
        for group_type_entry in rt_group_icon:
            try:
                # Navigate: Type -> ID -> Language -> Data
                group_id_entry = list(group_type_entry.directory.entries)[0]
                group_lang_entry = list(group_id_entry.directory.entries)[0]
                data_rva = group_lang_entry.data.struct.OffsetToData
                data_size = group_lang_entry.data.struct.Size
                group_data = pe.get_memory_mapped_image()[data_rva:data_rva + data_size]
            except Exception:
                continue

            count = int.from_bytes(group_data[4:6], "little")
            icon_data_chunks = []
            icon_sizes = []

            for i in range(count):
                entry_offset = 6 + i * 14
                entry = group_data[entry_offset:entry_offset + 14]
                w = entry[0] or 256
                h = entry[1] or 256
                nid = int.from_bytes(entry[12:14], "little")

                # Find matching RT_ICON by ID (not language)
                for icon_type_entry in rt_icon:
                    try:
                        for icon_id_entry in list(icon_type_entry.directory.entries):
                            if icon_id_entry.id == nid:
                                icon_lang_entry = list(icon_id_entry.directory.entries)[0]
                                rva = icon_lang_entry.data.struct.OffsetToData
                                size = icon_lang_entry.data.struct.Size
                                icon_raw = pe.get_memory_mapped_image()[rva:rva + size]
                                icon_data_chunks.append(icon_raw)
                                icon_sizes.append((w, h))
                                break
                    except Exception:
                        continue

            if not icon_data_chunks:
                continue

            ico_buf = io.BytesIO()
            ico_buf.write(b"\x00\x00\x01\x00")
            ico_buf.write(count.to_bytes(2, "little"))
            offset = 6 + count * 16
            for i, raw in enumerate(icon_data_chunks):
                w = min(icon_sizes[i][0], 255)
                h = min(icon_sizes[i][1], 255)
                ico_buf.write(bytes([w, h, 0, 0]))
                ico_buf.write(b"\x01\x00")
                ico_buf.write(b"\x20\x00")
                ico_buf.write(len(raw).to_bytes(4, "little"))
                ico_buf.write(offset.to_bytes(4, "little"))
                offset += len(raw)
            for raw in icon_data_chunks:
                ico_buf.write(raw)
            ico_buf.seek(0)

            try:
                img = Image.open(ico_buf)
                n_frames = getattr(img, "n_frames", 1)
                print_info("Icon", f"ICO has {n_frames} frame(s)")
                saved = 0
                for i in range(n_frames):
                    img.seek(i)
                    w, h = img.size
                    target = icons_dir / "hicolor" / f"{w}x{h}" / "apps" / f"{icon_name}.png"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    img.save(target, "PNG")
                    saved += 1
                if saved:
                    print_info("Icon", f"Extracted {saved} icon size(s) to {icons_dir / 'hicolor'}")
                    return True
            except Exception:
                continue

        return False
    finally:
        try:
            pe.close()
        except Exception:
            pass


def find_app_uri_schemes(prefix_path: Path, exe_name: str) -> List[str]:
    """Scan Wine registry for URI schemes registered by the given executable."""
    schemes = []
    needle = exe_name.lower().replace("/", "\\")

    for reg_file in ["user.reg", "system.reg"]:
        path = prefix_path / reg_file
        if not path.exists():
            continue

        raw = path.read_bytes()
        text = raw.decode("utf-16-le", errors="replace") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", errors="replace")

        current_key = ""
        has_url_protocol = False
        # Map from key name to whether it has URL Protocol set
        url_keys = {}

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_key = line[1:-1]
                has_url_protocol = False
            elif '"URL Protocol"' in line:
                has_url_protocol = True
                url_keys[current_key] = False
            elif has_url_protocol and current_key and line.startswith("@="):
                cmd = line[3:].strip('"')
                if needle in cmd.lower():
                    url_keys[current_key] = True

        for key, matched in url_keys.items():
            if not matched:
                continue
            parts = key.split("\\")
            if len(parts) >= 2 and parts[0].lower() == "hkey_classes_root":
                scheme = parts[1]
                if scheme not in schemes:
                    schemes.append(scheme)

    return schemes


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("url", metavar="<URL>")
def uri(url: str):
    """Handle a URI from the host system via the exported application's protocol.

    Parses a URI and launches the matching registered application.
    The URI is passed as an argument to the application.
    """
    project = ensure_project()
    scheme = url.split(":")[0].lower()

    config = project.load_config()
    for app_name, app_info in config.get("apps", {}).items():
        exe_path = app_info.get("exe", "")
        exe_name = Path(exe_path.replace("C:\\", "").replace("\\", "/") if "C:\\" in exe_path else exe_path).name
        wine_arch = app_info.get("wine_arch")
        prefix = get_wine_prefix_path(project, wine_arch)
        app_schemes = find_app_uri_schemes(prefix, exe_name)
        if scheme in app_schemes:
            extra_args = [url]
            run.callback(app_or_exe=app_name, extra_args=tuple(extra_args))
            return

    print_error(f"No registered application handles the URI scheme '{scheme}'.")
    print_info("Hint", "Use [command]cheapwine export <app>[/command] to register an application and its URI schemes.")
    sys.exit(1)


@cli.command()
@click.argument("name", metavar="<NAME>")
def export(name: str):
    """Export an application to the host Linux desktop menu.

    <NAME> is the registry name of the application to export.
    """
    project = ensure_project()
    
    # 1. Resolve application
    app_config = project.get_app(name)
    exe_path = None
    if app_config:
        exe_path = app_config.get("exe")
    else:
        # Check auto-detected
        from cheapwine.tui import scan_installed_apps
        with console.status("[bold green]Scanning for installed applications..."):
            detected = scan_installed_apps(project)
        for app in detected:
            if app["name"].lower() == name.lower():
                exe_path = app["exe"]
                name = app["name"] # Keep correct casing
                break
                
    if not exe_path:
        print_error(f"Application [accent]{name}[/accent] not found in registered or auto-detected apps.")
        sys.exit(1)
        
    # 2. Resolve the cheapwine binary path for the desktop launcher
    import shutil
    cheapwine_path = shutil.which("cheapwine") or shutil.which("cw") or "cheapwine"
    
    safe_proj_name = project.root_dir.name.replace(" ", "_").lower()
    safe_app_name = name.replace(" ", "_").lower()
    
    # 3. Extract application icon from the exe
    wine_arch = app_config.get("wine_arch") if app_config else None
    prefix = get_wine_prefix_path(project, wine_arch)
    
    # Resolve the exe path within the Wine prefix
    full_exe_path = None
    if "C:\\" in exe_path or "c:\\" in exe_path:
        relative = exe_path.replace("C:\\", "").replace("c:\\", "").replace("\\", "/")
        full_exe_path = prefix / "drive_c" / relative
    elif "\\" in exe_path:
        relative = exe_path.replace("\\", "/")
        full_exe_path = prefix / "drive_c" / relative
    elif "/" in exe_path:
        full_exe_path = Path(exe_path)
    else:
        # Bare filename like "notepad.exe" — search the prefix
        full_exe_path = prefix / "drive_c" / "windows" / exe_path
    
    print_info("Icon", f"Looking for exe at: {full_exe_path}")
    
    icon_name = f"cheapwine-{safe_proj_name}-{safe_app_name}"
    icon_extracted = extract_exe_icon(full_exe_path, icon_name) if full_exe_path and full_exe_path.exists() else False
    if not icon_extracted:
        print_info("Icon", "Falling back to default wine icon")
    
    # 4. Detect URI schemes registered by the application in the Wine prefix
    exe_name = Path(exe_path.replace("C:\\", "").replace("\\", "/") if "C:\\" in exe_path else exe_path).name
    app_schemes = find_app_uri_schemes(prefix, exe_name)
    
    # 5. Generate .desktop file
    desktop_dir = Path("~/.local/share/applications").expanduser()
    desktop_dir.mkdir(parents=True, exist_ok=True)
    
    desktop_file_path = desktop_dir / f"cheapwine-{safe_proj_name}-{safe_app_name}.desktop"
    
    mime_types = ";".join(f"x-scheme-handler/{s}" for s in app_schemes)
    mime_line = f"MimeType={mime_types};\n" if app_schemes else ""
    
    content = f"""[Desktop Entry]
Name={project.root_dir.name} - {name}
Exec={cheapwine_path} run {name}
Path={project.root_dir.absolute()}
Icon={icon_name if icon_extracted else "wine"}
Terminal=false
Type=Application
Categories=Wine;
{mime_line}"""
    try:
        desktop_file_path.write_text(content, encoding="utf-8")
        
        # Register each URI scheme with xdg-mime
        if app_schemes:
            import subprocess
            for scheme in app_schemes:
                subprocess.run(
                    ["xdg-mime", "default", desktop_file_path.name, f"x-scheme-handler/{scheme}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                )
            schemes_str = ", ".join(app_schemes)
            print_step("Exported", f"App [accent]{name}[/accent] to host desktop launcher + URI schemes: {schemes_str}")
        else:
            print_step("Exported", f"App [accent]{name}[/accent] to host desktop launcher: [bold]{desktop_file_path.name}[/bold]")
    except Exception as e:
        print_error(f"Failed to export application: {e}")
        sys.exit(1)

@cli.command()
@click.argument("name", metavar="<NAME>")
def unexport(name: str):
    """Remove exported desktop launcher for an application.

    <NAME> is the registry name of the application to unexport.
    """
    project = ensure_project()
    
    desktop_dir = Path("~/.local/share/applications").expanduser()
    safe_proj_name = project.root_dir.name.replace(" ", "_").lower()
    safe_app_name = name.replace(" ", "_").lower()
    desktop_file_path = desktop_dir / f"cheapwine-{safe_proj_name}-{safe_app_name}.desktop"
    
    if desktop_file_path.exists():
        try:
            desktop_file_path.unlink()
            print_step("Unexported", f"Removed host desktop launcher: [bold]{desktop_file_path.name}[/bold]")
        except Exception as e:
            print_error(f"Failed to remove desktop file: {e}")
            sys.exit(1)
    else:
        print_warning(f"No exported desktop launcher found at {desktop_file_path}")

@cli.command()
def easydistill():
    """Launch the interactive TUI configuration editor for distillery.json."""
    project = ensure_project()
    from cheapwine.tui import run_easydistill
    run_easydistill(project)

if __name__ == "__main__":
    cli()
