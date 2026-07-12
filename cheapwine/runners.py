import os
import sys
import json
import urllib.request
import tarfile
import re
import platform
from pathlib import Path
from typing import Optional, Tuple
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from cheapwine.utils import console, print_info, print_step, print_error, print_warning

RUNNERS_DIR = Path("~/.local/share/cheapwine/runners").expanduser()

def resolve_and_download_runner(runner_name: str) -> Optional[str]:
    """
    Checks if runner_name refers to a downloadable runner (Proton-GE or Wine-GE).
    If it does, ensures it is downloaded and returns the absolute path to the wine binary.
    If not, returns None.
    """
    runner_lower = runner_name.lower().strip()
    
    # Ignore absolute paths, relative paths, or standard system commands
    if runner_lower.startswith("/") or runner_lower.startswith(".") or runner_lower in ["wine", "wine64"]:
        return None
        
    # Check if it matches our downloadable patterns
    is_wine_ge = "wine-ge" in runner_lower or runner_lower.startswith("ge-wine")
    is_proton_ge = "proton-ge" in runner_lower or runner_lower.startswith("ge-proton")
    
    if not (is_wine_ge or is_proton_ge):
        return None
        
    # Determine the repo and release tag/prefix
    if is_wine_ge:
        repo = "GloriousEggroll/wine-ge-custom"
        type_prefix = "wine-ge"
    else:
        repo = "GloriousEggroll/proton-ge-custom"
        type_prefix = "proton-ge"
        
    # Parse version. e.g. "wine-ge-8-26" -> tag "GE-Proton8-26"
    version_part = ""
    versions = re.findall(r"\d+[-.]\d+", runner_lower)
    if versions:
        version_part = versions[0].replace(".", "-") # Normalize to 8-26
        
    # Fetch release from GitHub API
    tag_name, download_url, browser_download_name = fetch_github_release(repo, version_part)
    if not download_url:
        print_error(f"Could not find a downloadable runner for '{runner_name}' on GitHub repository {repo}.")
        sys.exit(1)
        
    # Target directory name (e.g. ~/.local/share/cheapwine/runners/wine-ge-8-26)
    clean_tag = tag_name.replace("GE-Proton", "").lower()
    target_name = f"{type_prefix}-{clean_tag}"
    runner_dir = RUNNERS_DIR / target_name
    
    # Locate wine executable inside runner_dir
    wine_exe_path = find_wine_binary(runner_dir)
    
    if wine_exe_path and wine_exe_path.exists():
        return str(wine_exe_path.absolute())
        
    # Download and extract
    print_info("Download", f"Downloading runner {tag_name} from GitHub...")
    archive_path = download_file_with_progress(download_url, browser_download_name)
    
    print_info("Extract", f"Extracting to {runner_dir}...")
    extract_archive(archive_path, runner_dir)
    
    # Remove archive
    if archive_path.exists():
        archive_path.unlink()
        
    # Find wine binary again
    wine_exe_path = find_wine_binary(runner_dir)
    if wine_exe_path and wine_exe_path.exists():
        print_step("Downloaded", f"Runner {tag_name} successfully set up at {wine_exe_path.name}")
        return str(wine_exe_path.absolute())
    else:
        print_error(f"Failed to find wine executable in the extracted runner archive at {runner_dir}")
        sys.exit(1)

def is_matching_arch(asset_name: str) -> bool:
    """Helper to check if the asset matches the host architecture."""
    asset_name_lower = asset_name.lower()
    host = platform.machine().lower()
    
    # Normalize host
    if host in ["x86_64", "amd64", "x64"]:
        host_norm = "x86_64"
    elif host in ["aarch64", "arm64"]:
        host_norm = "arm64"
    else:
        host_norm = host
        
    if host_norm == "x86_64":
        # Exclude ARM, 32-bit, or other architectures
        exclusions = ["aarch64", "arm64", "armhf", "armv", "i386", "i686", "386"]
        for excl in exclusions:
            if excl in asset_name_lower:
                return False
        return True
    elif host_norm == "arm64":
        # Must contain arm64 or aarch64
        return "aarch64" in asset_name_lower or "arm64" in asset_name_lower
    else:
        # Fallback: if host name is in asset name, or if no other arch is in asset name
        return host in asset_name_lower

def fetch_github_release(repo: str, version_part: str = "") -> Tuple[str, str, str]:
    """Queries GitHub API to find the matching tag and download asset URL."""
    url = f"https://api.github.com/repos/{repo}/releases"
    if not version_part:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "cheapwine-runner-downloader"}
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
        if not version_part:
            releases = [data]
        else:
            releases = data
            
        for release in releases:
            tag = release.get("tag_name", "")
            if version_part:
                normalized_tag = tag.lower().replace("-", "").replace(".", "")
                normalized_ver = version_part.lower().replace("-", "").replace(".", "")
                if normalized_ver not in normalized_tag:
                    continue
                    
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".tar.xz") or name.endswith(".tar.gz") or name.endswith(".tar.zst"):
                    if is_matching_arch(name):
                        return tag, asset.get("browser_download_url"), name
                    
    except Exception as e:
        print_error(f"Error communicating with GitHub API: {e}")
        
    return "", "", ""

def download_file_with_progress(url: str, filename: str) -> Path:
    """Downloads a file showing a rich progress bar."""
    RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = RUNNERS_DIR / filename
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "cheapwine-runner-downloader"}
        )
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get('content-length', 0))
            
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"Downloading {filename}", total=total_size)
                
                with open(dest_path, "wb") as f:
                    chunk_size = 1024 * 64
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
                        
        return dest_path
    except Exception as e:
        print_error(f"Download failed: {e}")
        if dest_path.exists():
            dest_path.unlink()
        sys.exit(1)

def extract_archive(archive_path: Path, target_dir: Path):
    """Extracts tarball to target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive_path) as tar:
            tar.extractall(path=target_dir)
    except Exception as e:
        print_error(f"Extraction failed: {e}")
        import shutil
        if target_dir.exists():
            shutil.rmtree(target_dir)
        sys.exit(1)

def find_wine_binary(runner_dir: Path) -> Optional[Path]:
    """Recursively searches for the wine executable inside runner_dir."""
    candidates = list(runner_dir.glob("**/bin/wine"))
    if not candidates:
        candidates = list(runner_dir.glob("**/bin/wine64"))
        
    if candidates:
        for c in candidates:
            if os.access(c, os.X_OK):
                return c
        return candidates[0]
        
    return None
