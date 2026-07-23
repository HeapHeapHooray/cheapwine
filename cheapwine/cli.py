import click
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Union

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
@click.option("--name", "-n", help="Name of the project (defaults to directory name).")
@click.option("--arch", type=click.Choice(["win32", "win64"]), default="win64", help="Architecture for the Wine prefix.")
@click.option("--force", is_flag=True, help="Force re-initialization of prefix if it exists.")
@click.option("--win-version", help="Windows version to configure (e.g. win95, winxp, win10).")
@click.option("--wine-version", help="Wine version setting (e.g. system, 8.0, 9.0).")
@click.option("--runner", help="Global Wine runner to use (e.g. wine, proton, or absolute path).")
@click.option("--runner-version", help="Global Wine runner version to use.")
@click.option("--tricks", "-t", multiple=True, help="Global Winetricks components to apply (can specify multiple times).")
@click.option("--latencyflex/--no-latencyflex", default=None, help="Enable or disable LatencyFleX support.")
@click.option("--env", "-e", multiple=True, help="Environment variables in KEY=VALUE format (can specify multiple times).")
def init(name: Optional[str], arch: str, force: bool, win_version: str, wine_version: str, runner: str, runner_version: str, tricks: Tuple[str, ...], latencyflex: Optional[bool], env: Tuple[str, ...]):
    """Initialize a new cheapwine project in the current directory."""
    project = Project.get_or_create_project()
    
    config_created = False
    config_changed = False
    
    env_dict = {}
    for item in env:
        if "=" in item:
            k, v = item.split("=", 1)
            env_dict[k.strip()] = v.strip()
        else:
            print_warning(f"Invalid env format '{item}'. Expected KEY=VALUE. Skipping.")
    
    if not project.exists():
        target_win_ver = win_version if win_version else "win10"
        target_runner = runner if runner else "wine"
        target_lfx = latencyflex if latencyflex is not None else False
        config_created = project.init_project_files(
            name=name,
            wine_arch=arch,
            win_version=target_win_ver,
            wine_version=wine_version,
            runner=target_runner,
            runner_version=runner_version,
            winetricks=list(tricks) if tricks else None,
            latencyflex=target_lfx,
            env=env_dict if env_dict else None
        )
        print_step("Created", f"distillery.json default settings")
    else:
        config = project.load_config()
        if name and config.get("name") != name:
            config["name"] = name
            config_changed = True
        if win_version and config.get("win_version") != win_version:
            config["win_version"] = win_version
            config_changed = True
        if wine_version and config.get("wine_version") != wine_version:
            config["wine_version"] = wine_version
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
        if tricks:
            config["winetricks"] = list(tricks)
            config_changed = True
        if latencyflex is not None and config.get("latencyflex") != latencyflex:
            config["latencyflex"] = latencyflex
            config_changed = True
        if env_dict:
            if "env" not in config:
                config["env"] = {}
            for k, v in env_dict.items():
                if config["env"].get(k) != v:
                    config["env"][k] = v
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
@click.argument("name", required=False, metavar="[NAME]")
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
@click.option("--uri-scheme", multiple=True, help="URI scheme(s) to register for this app (e.g. myapp). Can specify multiple times.")
@click.option("--icon", "-i", help="Path to custom icon image, executable, or icon name.")
def add(name: Optional[str], exe: Optional[str], args: Tuple[str, ...], env: Tuple[str, ...], workdir: str, win_version: str, arch: str, runner: str, runner_version: str, tricks: Tuple[str, ...], latencyflex: Optional[bool], uri_scheme: Tuple[str, ...], icon: Optional[str] = None):
    """Add a new application to distillery.json.

    [NAME] is the unique registry name for the application. If omitted,
    you will be prompted to select from auto-detected applications.

    [EXE_PATH] is the Windows executable (.exe) path. This is required unless
    registering a known auto-detected application by name.

    [ARGS...] are the default arguments to pass to the executable.
    """
    project = ensure_project()
    
    target_exe = exe
    if not name and not target_exe:
        from cheapwine.tui import scan_installed_apps
        with console.status("[bold green]Scanning for installed applications..."):
            detected = scan_installed_apps(project)
        if not detected:
            print_error("No auto-detected applications found in the Wine prefix.")
            print_info("Hint", "Specify a name and path: [command]cheapwine add <name> <exe_path>[/command]")
            sys.exit(1)
        if len(detected) == 1:
            name = detected[0]["name"]
            target_exe = detected[0]["exe"]
            print_info("Auto-detect", f"Found application '[accent]{name}[/accent]' -> [bold]{target_exe}[/bold]")
        else:
            console.print("\n[bold]Auto-detected applications:[/bold]\n")
            for i, app in enumerate(detected, 1):
                console.print(f"  [accent]{i}.[/accent] {app['name']}  [subtle]({app['exe']})[/subtle]")
            from rich.prompt import Prompt
            choice = Prompt.ask("\nSelect an application to add", default="1")
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(detected):
                    raise ValueError
            except (ValueError, IndexError):
                print_error(f"Invalid selection. Please enter a number between 1 and {len(detected)}.")
                sys.exit(1)
            name = detected[idx]["name"]
            target_exe = detected[idx]["exe"]
            print_info("Selected", f"[accent]{name}[/accent] -> [bold]{target_exe}[/bold]")
    
    if not target_exe or (target_exe and '/' not in target_exe and '\\' not in target_exe and '.' not in target_exe):
        from cheapwine.tui import scan_installed_apps
        with console.status("[bold green]Scanning for installed applications..."):
            detected = scan_installed_apps(project)
        match = None
        if target_exe:
            exe_stem = target_exe.lower()
            for app in detected:
                if app["name"].lower() == name.lower():
                    match = app
                    break
                if Path(app["exe"]).stem.lower() == exe_stem:
                    match = app
        else:
            for app in detected:
                if app["name"].lower() == name.lower():
                    match = app
                    break
        if match:
            target_exe = match["exe"]
            print_info("Auto-detect", f"Found auto-detected application '{match['name']}' -> [bold]{target_exe}[/bold]")
        elif target_exe:
            target_exe = target_exe + ".exe"
        else:
            target_exe = name + ".exe"

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
        latencyflex=latencyflex,
        uri_schemes=list(uri_scheme) if uri_scheme else None,
        icon=icon
    )
    scheme_hint = f" --uri-scheme {' --uri-scheme '.join(uri_scheme)}" if uri_scheme else ""
    if uri_scheme:
        _sync_app_desktop(project, name)
    print_step("Added", f"App [accent]{name}[/accent] ([bold]{target_exe}[/bold]) to distillery.json{scheme_hint}")

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

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("choco_args", nargs=-1, type=click.UNPROCESSED, metavar="[CHOCO_ARGS...]")
def chocolatey(choco_args: Tuple[str, ...]):
    """Run Chocolatey commands inside the local prefix context.

    [CHOCO_ARGS...] are arguments passed directly to choco (e.g. 'install', 'list', 'search').

    If Chocolatey is not already installed in the prefix, it will be
    automatically downloaded and installed from Chocolatey-for-wine.
    """
    project = ensure_project()

    from cheapwine.runners import ensure_chocolatey
    choco_path = ensure_chocolatey(project)

    args_list = [choco_path] + list(choco_args) if choco_args else [choco_path, "--help"]

    if not choco_args:
        print_info("Chocolatey", "No arguments provided. Showing help...")

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


def extract_icon_to_file(exe_path: Union[str, Path], target_path: Union[str, Path]) -> bool:
    """Extract application icon from a Windows executable or DLL and save it to target_path."""
    try:
        import pefile
        from PIL import Image
        import io
    except ImportError as e:
        print_warning(f"Icon extraction requires pefile and Pillow: {e}")
        return False

    exe_path = Path(exe_path).expanduser().resolve()
    target_path = Path(target_path).expanduser()

    if not exe_path.exists():
        print_error(f"Executable file not found: {exe_path}")
        return False

    try:
        pe = pefile.PE(str(exe_path))
    except Exception as e:
        print_error(f"Could not parse PE file {exe_path}: {e}")
        return False

    try:
        if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE") or not pe.DIRECTORY_ENTRY_RESOURCE.entries:
            print_error(f"No resource entries found in {exe_path}")
            return False

        rt_group_icon = [e for e in pe.DIRECTORY_ENTRY_RESOURCE.entries if e.id == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]]
        if not rt_group_icon:
            print_error(f"No RT_GROUP_ICON resources found in {exe_path}")
            return False
        rt_icon = [e for e in pe.DIRECTORY_ENTRY_RESOURCE.entries if e.id == pefile.RESOURCE_TYPE["RT_ICON"]]
        if not rt_icon:
            print_error(f"No RT_ICON resources found in {exe_path}")
            return False

        best_ico_buf = None
        best_frames = []

        for group_type_entry in rt_group_icon:
            try:
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
                frames = []
                for i in range(n_frames):
                    img.seek(i)
                    frames.append(img.copy())
                if frames:
                    best_ico_buf = ico_buf
                    best_frames = frames
                    break
            except Exception:
                continue

        if not best_frames and not best_ico_buf:
            print_error(f"Could not decode icon image from {exe_path}")
            return False

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.suffix.lower() == ".ico":
            with open(target_path, "wb") as f:
                f.write(best_ico_buf.getvalue())
            return True

        best_frame = max(best_frames, key=lambda f: f.size[0] * f.size[1])

        fmt = target_path.suffix.lstrip(".").upper()
        if not fmt:
            fmt = "PNG"
        elif fmt in ("JPG", "JPEG"):
            fmt = "JPEG"

        if fmt == "JPEG" and best_frame.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", best_frame.size, (255, 255, 255))
            if best_frame.mode == "RGBA":
                bg.paste(best_frame, mask=best_frame.split()[3])
            else:
                bg.paste(best_frame.convert("RGBA"))
            bg.save(target_path, format=fmt)
        else:
            if best_frame.mode != "RGBA" and fmt in ("PNG", "WEBP"):
                best_frame = best_frame.convert("RGBA")
            best_frame.save(target_path, format=fmt)

        return True

    finally:
        try:
            pe.close()
        except Exception:
            pass


def process_custom_icon(icon_input: Union[str, Path], icon_name: str, project_root: Optional[Path] = None) -> Tuple[bool, str]:
    """Process a custom icon (image file, ICO, SVG, EXE, or icon theme name) and install it for host desktop."""
    if not icon_input:
        return False, "wine"

    icon_str = str(icon_input).strip()
    p = Path(icon_str).expanduser()

    # Try resolving relative path against project root if not found relative to current working directory
    if not p.is_absolute() and project_root and not p.exists():
        alt_p = (project_root / p).resolve()
        if alt_p.exists():
            p = alt_p

    if p.exists() and p.is_file():
        icons_dir = Path("~/.local/share/icons").expanduser()

        # 1. Executable or DLL file
        if p.suffix.lower() in [".exe", ".dll"]:
            if extract_exe_icon(p, icon_name):
                return True, icon_name
            return False, "wine"

        # 2. SVG vector file
        if p.suffix.lower() in [".svg", ".svgz"]:
            try:
                target = icons_dir / "hicolor" / "scalable" / "apps" / f"{icon_name}.svg"
                target.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(p, target)
                print_info("Icon", f"Installed SVG icon to {target}")
                return True, icon_name
            except Exception as e:
                print_warning(f"Failed to copy SVG icon {p}: {e}")
                return False, "wine"

        # 3. Image file (PNG, JPG, JPEG, WEBP, BMP, ICO, GIF, TIFF, etc.)
        try:
            from PIL import Image
        except ImportError as e:
            print_warning(f"Icon processing requires Pillow: {e}")
            return False, "wine"

        try:
            img = Image.open(p)
            n_frames = getattr(img, "n_frames", 1)
            saved = 0

            # Determine resampling filter
            if hasattr(Image, "Resampling"):
                resample_filter = Image.Resampling.LANCZOS
            else:
                resample_filter = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))

            if n_frames > 1 and p.suffix.lower() in [".ico", ".gif", ".tiff"]:
                for i in range(n_frames):
                    try:
                        img.seek(i)
                        frame = img.copy()
                        if frame.mode != "RGBA":
                            frame = frame.convert("RGBA")
                        w, h = frame.size
                        if w > 0 and h > 0:
                            target = icons_dir / "hicolor" / f"{w}x{h}" / "apps" / f"{icon_name}.png"
                            target.parent.mkdir(parents=True, exist_ok=True)
                            frame.save(target, "PNG")
                            saved += 1
                    except Exception:
                        continue
            else:
                if img.mode != "RGBA":
                    img_rgba = img.convert("RGBA")
                else:
                    img_rgba = img.copy()

                w, h = img_rgba.size
                # If non-square, pad to square RGBA canvas so it doesn't get distorted
                if w != h:
                    max_dim = max(w, h)
                    square_img = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
                    offset = ((max_dim - w) // 2, (max_dim - h) // 2)
                    square_img.paste(img_rgba, offset, mask=img_rgba)
                else:
                    square_img = img_rgba

                orig_w, orig_h = square_img.size
                target = icons_dir / "hicolor" / f"{orig_w}x{orig_h}" / "apps" / f"{icon_name}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                square_img.save(target, "PNG")
                saved += 1

                standard_sizes = [16, 24, 32, 48, 64, 128, 256, 512]
                for size in standard_sizes:
                    if size != orig_w and size <= max(orig_w, 512):
                        resized = square_img.resize((size, size), resample_filter)
                        t = icons_dir / "hicolor" / f"{size}x{size}" / "apps" / f"{icon_name}.png"
                        t.parent.mkdir(parents=True, exist_ok=True)
                        resized.save(t, "PNG")
                        saved += 1

            if saved:
                print_info("Icon", f"Installed custom icon ({saved} sizes) to {icons_dir / 'hicolor'}")
                return True, icon_name
        except Exception as e:
            print_warning(f"Could not process custom icon image {p}: {e}")
            return False, "wine"

    # If icon_str looks like a path or extension but file doesn't exist
    if "/" in icon_str or "\\" in icon_str or any(icon_str.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".ico", ".svg", ".webp", ".bmp"]):
        print_warning(f"Specified icon file not found: {icon_str}")
        return False, "wine"

    # Assume it's a theme icon name (e.g. "wine", "steam", "firefox")
    return True, icon_str


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

        url_protocol_keys = set()
        current_key = ""

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_key = line[1:-1]
            elif '"URL Protocol"' in line:
                url_protocol_keys.add(current_key)
            elif line.startswith("@="):
                cmd = line[3:].strip('"')
                if needle in cmd.lower():
                    for pk in url_protocol_keys:
                        if current_key.startswith(pk + "\\"):
                            parts = pk.split("\\")
                            if len(parts) >= 2 and parts[0].lower() == "hkey_classes_root":
                                scheme = parts[1]
                                if scheme not in schemes:
                                    schemes.append(scheme)
                            break

    return schemes


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("url", metavar="<URL>")
def uri(url: str):
    """Handle a URI from the host system via the exported application's protocol.

    Parses a URI and launches the matching registered application.
    The URI is passed as an argument to the application.
    """
    import tempfile, datetime, urllib.parse
    log = Path(tempfile.gettempdir()) / "cheapwine-uri.log"

    # Some desktop environments/browsers pass URL-encoded URIs via %u
    url = urllib.parse.unquote(url)

    project = ensure_project()

    scheme = url.split(":")[0].lower()
    with open(log, "a") as f:
        f.write(f"[{datetime.datetime.now()}] uri called url={url} scheme={scheme}\n")

    config = project.load_config()
    for app_name, app_info in config.get("apps", {}).items():
        # Check explicit URI schemes from config first
        config_schemes = [s.lower() for s in app_info.get("uri_schemes", [])]
        if scheme in config_schemes:
            with open(log, "a") as f:
                f.write(f"[{datetime.datetime.now()}] matched explicit scheme app={app_name}\n")
            _launch_app_from_uri(project, app_name, app_info, url)
            return

        # Fall back to registry detection
        exe_path = app_info.get("exe", "")
        exe_name = Path(exe_path.replace("C:\\", "").replace("\\", "/") if "C:\\" in exe_path else exe_path).name
        wine_arch = app_info.get("wine_arch")
        prefix = get_wine_prefix_path(project, wine_arch)
        app_schemes = find_app_uri_schemes(prefix, exe_name)
        if scheme in app_schemes:
            with open(log, "a") as f:
                f.write(f"[{datetime.datetime.now()}] matched registry scheme app={app_name} schemes={app_schemes}\n")
            _launch_app_from_uri(project, app_name, app_info, url)
            return
        else:
            with open(log, "a") as f:
                f.write(f"[{datetime.datetime.now()}] no match app={app_name} registry_schemes={app_schemes}\n")

    with open(log, "a") as f:
        f.write(f"[{datetime.datetime.now()}] ERROR: no app matched scheme={scheme}\n")
    print_error(f"No registered application handles the URI scheme '{scheme}'.")
    print_info("Hint", "Use [command]cheapwine export <app>[/command] to register an application and its URI schemes.")
    sys.exit(1)


def _launch_app_from_uri(project, app_name, app_info, url):
    """Launch an app directly with a URI argument, bypassing the run command."""
    from cheapwine.wine import execute_command, set_app_win_version

    exe_path = app_info.get("exe", "")
    app_args = app_info.get("args", [])
    app_env = app_info.get("env", {})
    workdir = app_info.get("workdir")
    app_win_ver = app_info.get("win_version")
    app_wine_arch = app_info.get("wine_arch")
    app_runner = app_info.get("runner")
    app_runner_version = app_info.get("runner_version")
    app_winetricks = app_info.get("winetricks")
    app_latencyflex = app_info.get("latencyflex")

    if app_win_ver:
        set_app_win_version(project, exe_path, app_win_ver, wine_arch_override=app_wine_arch, runner_override=app_runner, runner_version_override=app_runner_version)

    combined_args = [exe_path] + app_args + [url]

    # Write debug log
    import tempfile, datetime
    log = Path(tempfile.gettempdir()) / "cheapwine-uri.log"
    with open(log, "a") as f:
        f.write(f"[{datetime.datetime.now()}] app={app_name} url={url} cmd={' '.join(combined_args)}\n")

    exit_code = execute_command(project, combined_args, app_env=app_env, workdir=workdir, wine_arch_override=app_wine_arch, runner_override=app_runner, runner_version_override=app_runner_version, app_winetricks=app_winetricks, latencyflex_override=app_latencyflex)
    sys.exit(exit_code)


def _sync_app_desktop(project: Project, app_name: str, icon_name: Optional[str] = None):
    """Write or update the .desktop file for an app, syncing URI schemes with the system."""
    config = project.load_config()
    app_info = config.get("apps", {}).get(app_name)
    if not app_info:
        return

    import shutil
    cheapwine_path = shutil.which("cheapwine") or shutil.which("cw") or "cheapwine"

    safe_proj_name = project.root_dir.name.replace(" ", "_").lower()
    safe_app_name = app_name.replace(" ", "_").lower()

    desktop_dir = Path("~/.local/share/applications").expanduser()
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file_path = desktop_dir / f"{safe_app_name}.desktop"

    if icon_name is None:
        if app_info.get("icon"):
            ok, res_icon = process_custom_icon(app_info["icon"], f"cheapwine-{safe_app_name}", project.root_dir)
            if ok:
                icon_name = res_icon
            else:
                icon_name = "wine"
        else:
            icon_name = "wine"
            if desktop_file_path.exists():
                for line in desktop_file_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("Icon="):
                        icon_name = line.split("=", 1)[1].strip()
                        break

    app_schemes = app_info.get("uri_schemes", [])
    mime_line = "MimeType=" + "".join(f"x-scheme-handler/{s};" for s in app_schemes) if app_schemes else ""

    content = f"""[Desktop Entry]
Name={app_name}
Exec={cheapwine_path} run "{app_name}" %u
Path={project.root_dir.absolute()}
Icon={icon_name}
Terminal=false
Type=Application
Categories=Wine;
{mime_line}
"""

    try:
        desktop_file_path.write_text(content, encoding="utf-8")

        import subprocess
        if app_schemes:
            for scheme in app_schemes:
                subprocess.run(
                    ["xdg-mime", "default", f"{desktop_file_path.name}", f"x-scheme-handler/{scheme}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                )
                subprocess.run(
                    ["gio", "mime", f"x-scheme-handler/{scheme}", f"{desktop_file_path.name}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                )
            subprocess.run(
                ["update-desktop-database", str(desktop_dir)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
            )
    except Exception:
        pass


@cli.command()
@click.argument("name", metavar="<NAME>")
@click.option("--uri-scheme", multiple=True, help="URI scheme(s) to register (e.g. myapp). Can specify multiple times.")
@click.option("--icon", "-i", help="Path to custom icon image, executable, or icon name.")
def export(name: str, uri_scheme: Tuple[str, ...], icon: Optional[str] = None):
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
    
    # If app was auto-detected (not registered), register it now so we can persist URI schemes and icon
    if app_config is None:
        print_info("Register", f"Auto-registering [accent]{name}[/accent] in distillery.json")
        app_config = project.add_app(app_name=name, exe_path=exe_path, uri_schemes=list(uri_scheme) if uri_scheme else None, icon=icon)
    elif icon:
        app_config["icon"] = icon
    
    # 2. Resolve the cheapwine binary path for the desktop launcher
    import shutil
    cheapwine_path = shutil.which("cheapwine") or shutil.which("cw") or "cheapwine"
    
    safe_proj_name = project.root_dir.name.replace(" ", "_").lower()
    safe_app_name = name.replace(" ", "_").lower()
    icon_name = f"cheapwine-{safe_app_name}"
    
    # 3. Determine application icon
    icon_to_use = icon or (app_config.get("icon") if app_config else None)
    icon_resolved = False
    final_icon_name = "wine"

    if icon_to_use:
        success, res_icon = process_custom_icon(icon_to_use, icon_name, project.root_dir)
        if success:
            final_icon_name = res_icon
            icon_resolved = True

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

    if not icon_resolved:
        if full_exe_path and full_exe_path.exists():
            print_info("Icon", f"Looking for exe at: {full_exe_path}")
            if extract_exe_icon(full_exe_path, icon_name):
                final_icon_name = icon_name
                icon_resolved = True
        
        if not icon_resolved:
            print_info("Icon", "Falling back to default wine icon")
            final_icon_name = "wine"
    
    # 4. Detect URI schemes registered by the application in the Wine prefix
    exe_name = Path(exe_path.replace("C:\\", "").replace("\\", "/") if "C:\\" in exe_path else exe_path).name
    app_schemes = find_app_uri_schemes(prefix, exe_name)
    
    # Merge with explicit URI schemes from config or CLI
    config_schemes = app_config.get("uri_schemes", []) if app_config else []
    explicit_schemes = list(uri_scheme) if uri_scheme else config_schemes
    app_schemes = list(dict.fromkeys(app_schemes + explicit_schemes))  # deduplicate preserving order
    
    # Fallback: infer URI scheme from exe's parent directory name
    # e.g. ".../MyApp 2026/MyApp.exe" -> parent dir "MyApp 2026" -> "myapp"
    if not app_schemes and full_exe_path:
        import re
        parent = full_exe_path.parent.name
        # Strip trailing version numbers like " 2026", " 9.0", " 2.0.1"
        name_part = re.sub(r'\s*\d[\d.]*\s*$', '', parent).strip()
        inferred = name_part.lower().replace(' ', '').replace('-', '')
        # Also fall back to exe stem if directory name yields nothing
        if not inferred:
            inferred = Path(exe_name).stem.lower()
        if inferred:
            app_schemes = [inferred]
            print_info("Inferred", f"URI scheme [accent]{inferred}[/accent] from executable's parent directory")
    
    # Persist config back to distillery.json
    if app_config is not None:
        if icon:
            app_config["icon"] = icon
        if app_schemes:
            app_config["uri_schemes"] = app_schemes
        config = project.load_config()
        config["apps"][name] = app_config
        project.save_config(config)
    
    # 5. Sync the .desktop file and register URI schemes with the system
    try:
        _sync_app_desktop(project, name, icon_name=final_icon_name)
        if app_schemes:
            schemes_str = ", ".join(app_schemes)
            print_step("Exported", f"App [accent]{name}[/accent] to host desktop launcher + URI schemes: {schemes_str}")
        else:
            print_step("Exported", f"App [accent]{name}[/accent] to host desktop launcher")
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
    
    # Compile a set of names to unexport
    unexport_names = {name}
    
    # Find auto-detected and registered apps to check if there are matches to unexport
    from cheapwine.tui import scan_installed_apps
    
    # Load registered apps
    config = project.load_config()
    registered_apps = config.get("apps", {})
    
    # Scan for auto-detected apps
    try:
        detected_apps = scan_installed_apps(project)
    except Exception:
        detected_apps = []
        
    def get_norm_path(p_str: str, app_conf: Optional[dict] = None) -> Optional[str]:
        if not p_str:
            return None
        wine_arch = app_conf.get("wine_arch") if app_conf else None
        prefix = get_wine_prefix_path(project, wine_arch)
        
        if "C:\\" in p_str or "c:\\" in p_str:
            relative = p_str.replace("C:\\", "").replace("c:\\", "").replace("\\", "/")
            full_path = prefix / "drive_c" / relative
        elif "\\" in p_str:
            relative = p_str.replace("\\", "/")
            full_path = prefix / "drive_c" / relative
        elif "/" in p_str:
            full_path = Path(p_str)
        else:
            full_path = prefix / "drive_c" / "windows" / p_str
            
        try:
            return str(full_path.resolve().absolute()).lower()
        except Exception:
            return str(full_path.absolute()).lower()
            
    # Resolve the target name to any known matching executables
    target_exes = set()
    
    # 1. Check if target matches any registered app name (case-insensitive)
    for reg_name, reg_conf in registered_apps.items():
        if reg_name.lower() == name.lower():
            unexport_names.add(reg_name)
            p = get_norm_path(reg_conf.get("exe"), reg_conf)
            if p:
                target_exes.add(p)
                
    # 2. Check if target matches any auto-detected app name (case-insensitive)
    for det_app in detected_apps:
        if det_app.get("name", "").lower() == name.lower():
            unexport_names.add(det_app["name"])
            p = get_norm_path(det_app.get("exe"))
            if p:
                target_exes.add(p)
                
    # 3. For any target executables found, find all other apps that share them
    if target_exes:
        for reg_name, reg_conf in registered_apps.items():
            p = get_norm_path(reg_conf.get("exe"), reg_conf)
            if p in target_exes:
                unexport_names.add(reg_name)
        for det_app in detected_apps:
            p = get_norm_path(det_app.get("exe"))
            if p in target_exes:
                unexport_names.add(det_app.get("name"))
                
    # Unexport each found name
    for app_name in sorted(unexport_names):
        safe_app_name = app_name.replace(" ", "_").lower()
        desktop_file_path = desktop_dir / f"{safe_app_name}.desktop"
        
        if desktop_file_path.exists():
            try:
                desktop_file_path.unlink()
                print_step("Unexported", f"Removed host desktop launcher: [bold]{desktop_file_path.name}[/bold]")
            except Exception as e:
                print_error(f"Failed to remove desktop file: {e}")
                sys.exit(1)
        else:
            # If this was the explicitly requested app, print the warning
            if app_name.lower() == name.lower():
                print_warning(f"No exported desktop launcher found at {desktop_file_path}")
                
    # Also clean up any URI handler files for this app
    import glob
    for handler in glob.glob(str(desktop_dir / f"cheapwine-uri-*")):
        h = Path(handler)
        try:
            h.unlink()
        except Exception:
            pass

@cli.command()
def easydistill():
    """Launch the interactive TUI configuration editor for distillery.json."""
    project = ensure_project()
    from cheapwine.tui import run_easydistill
    run_easydistill(project)

@cli.command(name="extract_icon")
@click.argument("exe_path", type=click.Path(path_type=Path))
@click.argument("target_path", type=click.Path(path_type=Path))
def extract_icon(exe_path: Path, target_path: Path):
    """Extract an icon from a Windows executable or DLL into an image file."""
    if extract_icon_to_file(exe_path, target_path):
        print_step("Extracted", f"Icon extracted from [accent]{exe_path}[/accent] to [bold]{target_path}[/bold]")
    else:
        sys.exit(1)

cli.add_command(extract_icon, name="extract-icon")

if __name__ == "__main__":
    cli()

