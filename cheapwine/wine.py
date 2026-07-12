import os
import subprocess
import shlex
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from cheapwine.project import Project
from cheapwine.utils import console, print_info, print_step, print_error, print_warning

def get_wine_prefix_path(project: Project, wine_arch_override: Optional[str] = None) -> Path:
    """Helper to resolve the prefix path based on default or overridden architecture."""
    config = project.load_config()
    default_arch = config.get("wine_arch", "win64")
    if wine_arch_override and wine_arch_override != default_arch:
        return project.root_dir / f".cheapwine_{wine_arch_override}"
    return project.prefix_path

def resolve_runner_command(runner: str) -> str:
    """Resolves a runner name. If it matches a downloadable runner, downloads and returns the absolute path."""
    from cheapwine.runners import resolve_and_download_runner
    downloaded_path = resolve_and_download_runner(runner)
    if downloaded_path:
        return downloaded_path
    return runner

def resolve_runner_name(runner: str, version: Optional[str] = None) -> str:
    """Combines runner type and version if version is specified."""
    if not version:
        return runner
        
    runner_lower = runner.lower().strip()
    if version.lower() in runner_lower:
        return runner
        
    # Only combine if it matches standard downloadable runner templates
    if runner_lower in ["proton-ge", "wine-ge", "ge-proton", "ge-wine", "kron4ek", "soda"]:
        return f"{runner}-{version}"
        
    return runner

def get_wine_env(project: Project, app_env: Optional[Dict[str, str]] = None, wine_arch_override: Optional[str] = None, runner_override: Optional[str] = None, runner_version_override: Optional[str] = None, latencyflex_override: Optional[bool] = None) -> Dict[str, str]:
    """Generates the environment dictionary for Wine execution."""
    config = project.load_config()
    
    # Base environment inherits from parent shell
    env = os.environ.copy()
    
    # Configure Wineprefix and Winearch
    prefix_path = get_wine_prefix_path(project, wine_arch_override)
    arch = wine_arch_override if wine_arch_override else config.get("wine_arch", "win64")
    
    env["WINEPREFIX"] = str(prefix_path.absolute())
    env["WINEARCH"] = arch
    
    # Set WINE runner path for helpers (like winetricks)
    raw_runner = runner_override or config.get("runner") or "wine"
    raw_version = runner_version_override or config.get("runner_version")
    combined_runner = resolve_runner_name(raw_runner, raw_version)
    runner = resolve_runner_command(combined_runner)
    runner_parts = shlex.split(runner)
    if runner_parts:
        env["WINE"] = runner_parts[0]
    
    # Apply project-level Wine env settings
    project_env = config.get("env", {})
    for k, v in project_env.items():
        env[k] = str(v)
        
    # Apply app-level env settings if provided
    if app_env:
        for k, v in app_env.items():
            env[k] = str(v)
            
    # Apply LatencyFleX settings if enabled
    is_lfx = False
    if latencyflex_override is True:
        is_lfx = True
    elif latencyflex_override is False:
        is_lfx = False
    else:
        is_lfx = config.get("latencyflex", False)
        
    if is_lfx:
        env["LFX"] = "1"
        env["PROTON_ENABLE_NVAPI"] = "1"
        env["DXVK_NVAPI_DRIVER_VERSION"] = "49729"
        env["DXVK_NVAPI_ALLOW_OTHER_DRIVERS"] = "1"
            
    return env

def init_prefix(project: Project, force: bool = False, wine_arch_override: Optional[str] = None, runner_override: Optional[str] = None, runner_version_override: Optional[str] = None) -> bool:
    """Initializes the Wine prefix if it doesn't exist or if forced."""
    prefix_path = get_wine_prefix_path(project, wine_arch_override)
    
    if prefix_path.exists() and not force:
        return False

    config = project.load_config()
    wine_arch = wine_arch_override if wine_arch_override else config.get("wine_arch", "win64")
    
    # Create the parent directory if needed
    prefix_path.parent.mkdir(parents=True, exist_ok=True)
    
    raw_runner = runner_override or config.get("runner") or "wine"
    raw_version = runner_version_override or config.get("runner_version")
    combined_runner = resolve_runner_name(raw_runner, raw_version)
    
    print_info("Prefix", f"Initializing Wine prefix at [accent]./{prefix_path.name}[/accent] ({wine_arch}) using runner [bold]{combined_runner}[/bold]...")
    
    runner = resolve_runner_command(combined_runner)
    env = get_wine_env(project, wine_arch_override=wine_arch_override, runner_override=runner)
    env["WINEDEBUG"] = "-all"
    
    runner_parts = shlex.split(runner)
    boot_cmd = runner_parts + ["wineboot", "-u"]
    
    try:
        # Use rich status spinner for a beautiful CLI experience
        with console.status("[bold green]Creating Wine prefix (this might take a few seconds)..."):
            result = subprocess.run(
                boot_cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        print_step("Initialized", f"Wine prefix successfully created at ./{prefix_path.name}")
        # Apply configurations like Windows version
        sync_prefix_settings(project, wine_arch_override=wine_arch_override, runner_override=runner)
        # Disable winemenubuilder to prevent host menu integration spam
        disable_host_integration(project, wine_arch_override=wine_arch_override, runner_override=runner)
        
        # Apply global winetricks if specified in config
        global_tricks = config.get("winetricks", [])
        if global_tricks:
            apply_winetricks_components(project, global_tricks, wine_arch_override=wine_arch_override, runner_override=runner)
            
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to initialize Wine prefix: {e}")
        return False
    except FileNotFoundError:
        print_error(f"Wine runner '{runner}' is not installed or not in your PATH.")
        return False

def sync_prefix_settings(project: Project, wine_arch_override: Optional[str] = None, runner_override: Optional[str] = None, runner_version_override: Optional[str] = None) -> bool:
    """Syncs settings from distillery.json (like win_version) to the Wine prefix registry."""
    config = project.load_config()
    win_version = config.get("win_version")
    if not win_version:
        return False
        
    env = get_wine_env(project, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override)
    env["WINEDEBUG"] = "-all"
    
    raw_runner = runner_override or config.get("runner") or "wine"
    raw_version = runner_version_override or config.get("runner_version")
    combined_runner = resolve_runner_name(raw_runner, raw_version)
    runner_parts = shlex.split(resolve_runner_command(combined_runner))
    
    try:
        # Run reg add to update the Windows version in Wine registry
        subprocess.run(
            runner_parts + ["reg", "add", "HKCU\\Software\\Wine", "/v", "Version", "/d", win_version, "/f"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        prefix_path = get_wine_prefix_path(project, wine_arch_override)
        print_info("Sync", f"Set Windows version to [accent]{win_version}[/accent] inside [bold]./{prefix_path.name}[/bold]")
        return True
    except Exception as e:
        print_warning(f"Failed to sync Windows version '{win_version}' to prefix registry: {e}")
        return False

def execute_command(
    project: Project,
    cmd_args: List[str],
    app_env: Optional[Dict[str, str]] = None,
    workdir: Optional[str] = None,
    wine_arch_override: Optional[str] = None,
    runner_override: Optional[str] = None,
    runner_version_override: Optional[str] = None,
    app_winetricks: Optional[List[str]] = None,
    latencyflex_override: Optional[bool] = None
) -> int:
    """Executes a command inside the Wine prefix context."""
    # Ensure prefix is initialized first
    init_prefix(project, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override)
    
    config = project.load_config()
    
    # Resolve the runner for applying winetricks
    raw_runner = runner_override or config.get("runner") or "wine"
    raw_version = runner_version_override or config.get("runner_version")
    combined_runner = resolve_runner_name(raw_runner, raw_version)
    
    # Apply global winetricks if specified
    global_tricks = config.get("winetricks", [])
    if global_tricks:
        apply_winetricks_components(project, global_tricks, wine_arch_override=wine_arch_override, runner_override=combined_runner, runner_version_override=runner_version_override)
        
    # Apply app-specific winetricks if specified
    if app_winetricks:
        apply_winetricks_components(project, app_winetricks, wine_arch_override=wine_arch_override, runner_override=combined_runner, runner_version_override=runner_version_override)
        
    env = get_wine_env(project, app_env, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override, latencyflex_override=latencyflex_override)
    
    # Resolve the executable if it exists locally
    resolved_args = list(cmd_args)
    if resolved_args:
        exe_candidate = Path(resolved_args[0])
        # If it's a relative path, resolve it relative to the project root
        if not exe_candidate.is_absolute():
            local_path = project.root_dir / exe_candidate
            if local_path.exists():
                resolved_args[0] = str(local_path.absolute())
    
    # Determine the working directory
    resolved_workdir = project.root_dir
    if workdir:
        resolved_workdir = Path(workdir)
        if not resolved_workdir.is_absolute():
            resolved_workdir = project.root_dir / resolved_workdir
    elif resolved_args:
        # Default to the exe's folder if it exists locally
        exe_path = Path(resolved_args[0])
        if exe_path.exists() and exe_path.is_file():
            resolved_workdir = exe_path.parent
            
    # Execute Wine command
    final_cmd = []
    if resolved_args:
        first_arg = resolved_args[0]
        # Winetricks is a host script, run it directly without prepending the wine runner
        # (It will automatically use env["WINE"] which we set in get_wine_env)
        if first_arg == "winetricks":
            from cheapwine.runners import ensure_winetricks
            winetricks_bin = ensure_winetricks()
            final_cmd = [winetricks_bin] + resolved_args[1:]
        else:
            config = project.load_config()
            raw_runner = runner_override or config.get("runner") or "wine"
            raw_version = runner_version_override or config.get("runner_version")
            combined_runner = resolve_runner_name(raw_runner, raw_version)
            runner = resolve_runner_command(combined_runner)
            runner_parts = shlex.split(runner)
            final_cmd = runner_parts + resolved_args
            
    if not final_cmd:
        print_error("No command specified to run.")
        return 1

    try:
        # Run the command, inheriting stdin/stdout/stderr
        result = subprocess.run(
            final_cmd,
            env=env,
            cwd=str(resolved_workdir.absolute()),
            stdin=None,
            stdout=None,
            stderr=None
        )
        return result.returncode
    except FileNotFoundError as e:
        print_error(f"Failed to execute command: {e}")
        return 127
    except Exception as e:
        print_error(f"Error executing command: {e}")
        return 1

def set_app_win_version(project: Project, exe_name: str, win_version: str, wine_arch_override: Optional[str] = None, runner_override: Optional[str] = None, runner_version_override: Optional[str] = None) -> bool:
    """Configures a specific application to run under a specific Windows version in the registry."""
    # Ensure the prefix is initialized
    init_prefix(project, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override)
    
    env = get_wine_env(project, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override)
    env["WINEDEBUG"] = "-all"
    
    # We only want the filename (e.g., "game.exe") for AppDefaults registry matching
    filename = Path(exe_name).name
    
    config = project.load_config()
    raw_runner = runner_override or config.get("runner") or "wine"
    raw_version = runner_version_override or config.get("runner_version")
    combined_runner = resolve_runner_name(raw_runner, raw_version)
    runner = resolve_runner_command(combined_runner)
    runner_parts = shlex.split(runner)
    
    try:
        # Update HKEY_CURRENT_USER\Software\Wine\AppDefaults\<filename>\Version in Wine registry
        subprocess.run(
            runner_parts + ["reg", "add", f"HKCU\\Software\\Wine\\AppDefaults\\{filename}", "/v", "Version", "/d", win_version, "/f"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        prefix_path = get_wine_prefix_path(project, wine_arch_override)
        print_info("Sync", f"Configured app [accent]{filename}[/accent] to run under [accent]{win_version}[/accent] inside [bold]./{prefix_path.name}[/bold]")
        return True
    except Exception as e:
        print_warning(f"Failed to set Windows version '{win_version}' for app '{filename}': {e}")
        return False

def disable_host_integration(project: Project, wine_arch_override: Optional[str] = None, runner_override: Optional[str] = None, runner_version_override: Optional[str] = None) -> bool:
    """Disables Wine's winemenubuilder in the registry to prevent host desktop shortcut spam."""
    env = get_wine_env(project, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override)
    env["WINEDEBUG"] = "-all"
    
    config = project.load_config()
    raw_runner = runner_override or config.get("runner") or "wine"
    raw_version = runner_version_override or config.get("runner_version")
    combined_runner = resolve_runner_name(raw_runner, raw_version)
    runner = resolve_runner_command(combined_runner)
    runner_parts = shlex.split(runner)
    
    try:
        subprocess.run(
            runner_parts + ["reg", "add", "HKCU\\Software\\Wine\\DllOverrides", "/v", "winemenubuilder.exe", "/d", "", "/f"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except Exception as e:
        print_warning(f"Failed to disable host menu integration: {e}")
        return False

def apply_winetricks_components(project: Project, components: List[str], wine_arch_override: Optional[str] = None, runner_override: Optional[str] = None, runner_version_override: Optional[str] = None) -> bool:
    """Applies a list of winetricks components to the prefix if not already applied."""
    if not components:
        return True
        
    prefix_path = get_wine_prefix_path(project, wine_arch_override)
    prefix_path.mkdir(parents=True, exist_ok=True)
    state_file = prefix_path / "cheapwine_tricks.json"
    
    # Load already applied tricks
    applied = set()
    if state_file.exists():
        try:
            with open(state_file, "r") as f:
                applied = set(json.load(f))
        except Exception:
            pass
            
    # Filter missing components
    missing = [c for c in components if c not in applied]
    if not missing:
        return True
        
    print_info("Winetricks", f"Applying missing winetricks components to prefix: {', '.join(missing)}")
    
    from cheapwine.runners import ensure_winetricks
    winetricks_bin = ensure_winetricks()
    
    env = get_wine_env(project, wine_arch_override=wine_arch_override, runner_override=runner_override, runner_version_override=runner_version_override)
    env["WINEDEBUG"] = "-all"
    
    cmd = [winetricks_bin, "-q"] + missing
    
    try:
        with console.status(f"[bold green]Running Winetricks to apply {', '.join(missing)}..."):
            subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        # Update applied tricks file
        applied.update(missing)
        with open(state_file, "w") as f:
            json.dump(list(applied), f)
        print_step("Winetricks", f"Successfully applied winetricks components: {', '.join(missing)}")
        return True
    except Exception as e:
        print_warning(f"Failed to apply winetricks components {missing}: {e}")
        return False
