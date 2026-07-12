import click
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional

from cheapwine import __version__
from cheapwine.project import Project
from cheapwine.wine import init_prefix, execute_command, sync_prefix_settings, set_app_win_version
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
def init(arch: str, force: bool, win_version: str, runner: str, runner_version: str):
    """Initialize a new cheapwine project in the current directory."""
    project = Project.get_or_create_project()
    
    config_created = False
    config_changed = False
    
    if not project.exists():
        target_win_ver = win_version if win_version else "win10"
        target_runner = runner if runner else "wine"
        config_created = project.init_project_files(wine_arch=arch, win_version=target_win_ver, runner=target_runner, runner_version=runner_version)
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
@click.argument("app_or_exe", required=False)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def run(app_or_exe: Optional[str], extra_args: Tuple[str, ...]):
    """Run a registered application or an arbitrary executable."""
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
        if app_win_ver:
            set_app_win_version(project, exe_path, app_win_ver, wine_arch_override=app_wine_arch, runner_override=app_runner, runner_version_override=app_runner_version)
            
        # Merge configuration args with extra args passed from CLI
        app_args = app_config.get("args", [])
        combined_args = [exe_path] + app_args + list(extra_args)
        
        env = app_config.get("env", {})
        workdir = app_config.get("workdir")
        
        source_label = "Auto-detected app" if is_detected else "Registered app"
        print_info("Running", f"{source_label} [accent]{app_or_exe}[/accent] -> [bold]{exe_path}[/bold] {' '.join(combined_args[1:])}")
        exit_code = execute_command(project, combined_args, app_env=env, workdir=workdir, wine_arch_override=app_wine_arch, runner_override=app_runner, runner_version_override=app_runner_version)
    else:
        # Check if it's a file path
        # If it doesn't exist, we still try to execute it in case it's in the Wine path (like notepad)
        combined_args = [app_or_exe] + list(extra_args)
        print_info("Running", f"Executable/Command -> [bold]{app_or_exe}[/bold] {' '.join(extra_args)}")
        exit_code = execute_command(project, combined_args)
        
    sys.exit(exit_code)

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("name")
@click.argument("exe", required=False)
@click.argument("args", nargs=-1)
@click.option("--env", "-e", multiple=True, help="Environment variables in KEY=VALUE format.")
@click.option("--workdir", "-w", help="Working directory for the app.")
@click.option("--win-version", help="App-specific Windows version (e.g. win95, winxp).")
@click.option("--arch", type=click.Choice(["win32", "win64"]), help="App-specific Wine architecture override.")
@click.option("--runner", help="App-specific Wine runner override.")
@click.option("--runner-version", help="App-specific Wine runner version override.")
def add(name: str, exe: Optional[str], args: Tuple[str, ...], env: Tuple[str, ...], workdir: str, win_version: str, arch: str, runner: str, runner_version: str):
    """Add a new application to distillery.json."""
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
        runner_version=runner_version
    )
    print_step("Added", f"App [accent]{name}[/accent] ([bold]{target_exe}[/bold]) to distillery.json")

@cli.command(name="remove")
@click.argument("name")
def remove_cmd(name: str):
    """Remove an application from distillery.json."""
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
@click.argument("wine_args", nargs=-1, type=click.UNPROCESSED)
def wine(wine_args: Tuple[str, ...]):
    """Run Wine commands inside the local prefix context (e.g. winecfg, regedit)."""
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
@click.argument("tricks_args", nargs=-1, type=click.UNPROCESSED)
def winetricks(tricks_args: Tuple[str, ...]):
    """Run winetricks in the context of the local prefix."""
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

@cli.command()
@click.argument("name")
def export(name: str):
    """Export an application to the host Linux desktop menu."""
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
        
    # 2. Generate .desktop file
    desktop_dir = Path("~/.local/share/applications").expanduser()
    desktop_dir.mkdir(parents=True, exist_ok=True)
    
    # Filename format: cheapwine-<project_name>-<app_name>.desktop
    safe_proj_name = project.root_dir.name.replace(" ", "_").lower()
    safe_app_name = name.replace(" ", "_").lower()
    desktop_file_path = desktop_dir / f"cheapwine-{safe_proj_name}-{safe_app_name}.desktop"
    
    content = f"""[Desktop Entry]
Name={project.root_dir.name} - {name}
Exec=cheapwine run {name}
Path={project.root_dir.absolute()}
Icon=wine
Terminal=false
Type=Application
Categories=Wine;
"""
    try:
        desktop_file_path.write_text(content, encoding="utf-8")
        print_step("Exported", f"App [accent]{name}[/accent] to host desktop launcher: [bold]{desktop_file_path.name}[/bold]")
    except Exception as e:
        print_error(f"Failed to export application: {e}")
        sys.exit(1)

@cli.command()
@click.argument("name")
def unexport(name: str):
    """Remove exported desktop launcher for an application."""
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

if __name__ == "__main__":
    cli()
