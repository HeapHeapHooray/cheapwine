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

def find_installed_runner_locally(type_prefix: str, version_part: str) -> Optional[Path]:
    """Searches RUNNERS_DIR for an already-installed runner matching type_prefix and version_part."""
    if not RUNNERS_DIR.exists():
        return None
        
    normalized_ver = version_part.lower().replace("-", "").replace(".", "")
    
    try:
        entries = sorted(list(RUNNERS_DIR.iterdir()), key=lambda x: x.name, reverse=True)
    except Exception:
        entries = list(RUNNERS_DIR.iterdir())
        
    for p in entries:
        if p.is_dir():
            name_lower = p.name.lower()
            if name_lower.startswith(type_prefix.lower()):
                if normalized_ver:
                    ver_suffix = name_lower[len(type_prefix):].replace("-", "").replace(".", "")
                    if normalized_ver in ver_suffix:
                        wine_exe = find_wine_binary(p)
                        if wine_exe and wine_exe.exists() and is_binary_compatible(wine_exe):
                            return wine_exe
                else:
                    wine_exe = find_wine_binary(p)
                    if wine_exe and wine_exe.exists() and is_binary_compatible(wine_exe):
                        return wine_exe
    return None

def resolve_and_download_runner(runner_name: str) -> Optional[str]:
    """
    Checks if runner_name refers to a downloadable runner (Proton-GE, Wine-GE, Kron4ek, or Soda).
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
    is_kron4ek = "kron4ek" in runner_lower
    is_soda = "soda" in runner_lower
    is_d2d1 = any(k in runner_lower for k in ["wine-d2d1", "d2d1", "dcomp", "mklnln"])
    
    if not (is_wine_ge or is_proton_ge or is_kron4ek or is_soda or is_d2d1):
        return None
        
    # Determine the repo and release tag/prefix
    if is_wine_ge:
        repo = "GloriousEggroll/wine-ge-custom"
        type_prefix = "wine-ge"
    elif is_proton_ge:
        repo = "GloriousEggroll/proton-ge-custom"
        type_prefix = "proton-ge"
    elif is_kron4ek:
        repo = "Kron4ek/Wine-Builds"
        type_prefix = "kron4ek"
        if "staging" in runner_lower:
            type_prefix += "-staging"
        if "tkg" in runner_lower:
            type_prefix += "-tkg"
    elif is_soda:
        repo = "bottlesdevs/wine"
        type_prefix = "soda"
    elif is_d2d1:
        repo = "mklnln/wine-d2d1-dcomp"
        type_prefix = "wine-d2d1"
        
    # Parse version. e.g. "wine-ge-8-26" -> tag "GE-Proton8-26"
    version_part = ""
    # Strip known type prefixes so digits in runner names (e.g. "d2d1") aren't mistaken for versions
    search_name = runner_lower
    if is_d2d1:
        for prefix in ["wine-d2d1", "d2d1", "mklnln", "dcomp"]:
            if search_name.startswith(prefix):
                search_name = search_name[len(prefix):]
                break
    elif is_wine_ge:
        for prefix in ["wine-ge", "ge-wine"]:
            if search_name.startswith(prefix):
                search_name = search_name[len(prefix):]
                break
    elif is_proton_ge:
        for prefix in ["proton-ge", "ge-proton"]:
            if search_name.startswith(prefix):
                search_name = search_name[len(prefix):]
                break
    elif is_kron4ek:
        if search_name.startswith("kron4ek"):
            search_name = search_name[len("kron4ek"):]
    elif is_soda:
        if search_name.startswith("soda"):
            search_name = search_name[len("soda"):]
    search_name = search_name.lstrip("-.")
    # Look for digits separated by dot or dash, or just a standalone number sequence
    versions = re.findall(r"\d+(?:[-.]\d+)*", search_name)
    if versions:
        version_part = versions[0].replace(".", "-") # Normalize to dash-separated, e.g. 8-26
        
    # Check if we already have a compatible local runner matching this description to avoid hitting the GitHub API
    local_wine = find_installed_runner_locally(type_prefix, version_part)
    if local_wine:
        return str(local_wine.absolute())
        
    # Fetch release from GitHub API
    tag_name, download_url, browser_download_name = fetch_github_release(repo, version_part, runner_name)
    if not download_url:
        print_error(f"Could not find a downloadable runner for '{runner_name}' on GitHub repository {repo}.")
        sys.exit(1)
        
    # Target directory name (e.g. ~/.local/share/cheapwine/runners/wine-ge-8-26)
    clean_tag = tag_name.replace("GE-Proton", "").lower()
    if clean_tag.startswith("v") and len(clean_tag) > 1 and clean_tag[1].isdigit():
        clean_tag = clean_tag[1:]
    if clean_tag.startswith(f"{type_prefix}-"):
        clean_tag = clean_tag[len(type_prefix)+1:]
    elif clean_tag.startswith(type_prefix):
        clean_tag = clean_tag[len(type_prefix):]
    target_name = f"{type_prefix}-{clean_tag}"
    runner_dir = RUNNERS_DIR / target_name
    
    # Locate wine executable inside runner_dir
    wine_exe_path = find_wine_binary(runner_dir)
    
    if wine_exe_path and wine_exe_path.exists():
        if is_binary_compatible(wine_exe_path):
            return str(wine_exe_path.absolute())
        else:
            print_warning(f"Installed runner at [bold]{target_name}[/bold] has incompatible architecture. Deleting and redownloading...")
            import shutil
            try:
                shutil.rmtree(runner_dir)
            except Exception as e:
                print_error(f"Failed to remove incompatible runner: {e}")
                sys.exit(1)
        
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

def fetch_github_release(repo: str, version_part: str = "", runner_name: str = "") -> Tuple[str, str, str]:
    """Queries GitHub API to find the matching tag and download asset URL."""
    is_staging = "staging" in runner_name.lower()
    is_tkg = "tkg" in runner_name.lower()

    def get_best_asset(assets, tag_name):
        candidates = []
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(".tar.xz") or name.endswith(".tar.gz") or name.endswith(".tar.zst"):
                if is_matching_arch(name):
                    name_lower = name.lower()
                    score = 0
                    if is_staging == ("staging" in name_lower):
                        score += 10
                    if is_tkg == ("tkg" in name_lower):
                        score += 5
                    if "wow64" in name_lower:
                        score += 1
                    candidates.append((score, asset, name))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_asset = candidates[0][1]
            best_name = candidates[0][2]
            return tag_name, best_asset.get("browser_download_url"), best_name
        return None

    if version_part:
        # Build candidate tags based on common conventions
        tags_to_try = []
        version_dot = version_part.replace("-", ".")
        if "proton-ge-custom" in repo:
            tags_to_try.append(f"GE-Proton{version_part}")
            tags_to_try.append(f"GE-Proton{version_dot}")
        elif "wine-ge-custom" in repo:
            tags_to_try.append(f"GE-Proton{version_part}")
            tags_to_try.append(f"GE-Proton{version_dot}")
            tags_to_try.append(f"wine-ge-{version_part}")
            tags_to_try.append(f"wine-ge-{version_dot}")
            tags_to_try.append(f"GE-wine{version_part}")
            tags_to_try.append(f"GE-wine{version_dot}")
        elif "wine-builds" in repo.lower(): # Kron4ek
            tags_to_try.append(version_dot)
            tags_to_try.append(version_part)
            tags_to_try.append(f"wine-{version_dot}")
            tags_to_try.append(f"wine-{version_part}")
        elif "bottlesdevs/wine" in repo.lower() or "soda" in repo.lower(): # Soda
            tags_to_try.append(f"soda-{version_dot}")
            tags_to_try.append(f"soda-{version_part}")
            for iter_val in ["1", "2", "3", "0", "4", "5", "6", "7", "8", "9"]:
                tags_to_try.append(f"soda-{version_dot}-{iter_val}")
                tags_to_try.append(f"soda-{version_part}-{iter_val}")
        elif "d2d1" in repo.lower() or "mklnln" in repo.lower(): # wine-d2d1-dcomp
            tags_to_try.append(f"v{version_dot}")
            tags_to_try.append(f"v{version_part}")
            tags_to_try.append(version_dot)
            tags_to_try.append(version_part)
            tags_to_try.append(f"wine-d2d1-{version_dot}")
            tags_to_try.append(f"wine-d2d1-{version_part}")
            
        for tag in tags_to_try:
            tag_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
            try:
                req = urllib.request.Request(
                    tag_url,
                    headers={"User-Agent": "cheapwine-runner-downloader"}
                )
                with urllib.request.urlopen(req) as response:
                    release = json.loads(response.read().decode())
                res = get_best_asset(release.get("assets", []), release.get("tag_name", tag))
                if res:
                    return res
            except Exception:
                continue

    # Fallback to paginated search (up to 5 pages)
    page = 1
    max_pages = 5
    while page <= max_pages:
        url = f"https://api.github.com/repos/{repo}/releases?page={page}&per_page=30"
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
                
            if not releases:
                break
                
            for release in releases:
                tag = release.get("tag_name", "")
                if version_part:
                    normalized_tag = tag.lower().replace("-", "").replace(".", "")
                    normalized_ver = version_part.lower().replace("-", "").replace(".", "")
                    if normalized_ver not in normalized_tag:
                        continue
                        
                res = get_best_asset(release.get("assets", []), tag)
                if res:
                    return res
                            
            if not version_part:
                break
                
            page += 1
        except Exception as e:
            # Only print error if it's the first page or we are querying the latest release
            if page == 1 or not version_part:
                print_error(f"Error communicating with GitHub API: {e}")
            break
            
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
    archive_name = archive_path.name.lower()
    is_zst = archive_name.endswith(".tar.zst") or archive_name.endswith(".zst")

    extracted = False
    if is_zst:
        import shutil
        import subprocess
        if shutil.which("tar"):
            try:
                subprocess.run(
                    ["tar", "--zstd", "-xf", str(archive_path), "-C", str(target_dir)],
                    check=True, capture_output=True
                )
                extracted = True
            except Exception:
                pass

        if not extracted and shutil.which("zstd") and shutil.which("tar"):
            try:
                p1 = subprocess.Popen(["zstd", "-dc", str(archive_path)], stdout=subprocess.PIPE)
                p2 = subprocess.Popen(["tar", "-xf", "-", "-C", str(target_dir)], stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if p1.stdout:
                    p1.stdout.close()
                p2.communicate()
                if p2.returncode == 0:
                    extracted = True
            except Exception:
                pass

    if not extracted:
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
    candidates_wine = list(runner_dir.glob("**/bin/wine"))
    valid_wine = [c for c in candidates_wine if os.access(c, os.X_OK) and is_binary_compatible(c)]
    if valid_wine:
        return valid_wine[0]
        
    candidates_wine64 = list(runner_dir.glob("**/bin/wine64"))
    valid_wine64 = [c for c in candidates_wine64 if os.access(c, os.X_OK) and is_binary_compatible(c)]
    if valid_wine64:
        return valid_wine64[0]
        
    if candidates_wine:
        return candidates_wine[0]
    if candidates_wine64:
        return candidates_wine64[0]
        
    return None

def check_elf_binary_architecture(path: Path) -> str:
    """Reads the ELF header of a file and returns its architecture ('x86_64', 'arm64', '32bit', or 'unknown')."""
    try:
        with open(path, "rb") as f:
            header = f.read(20)
        if len(header) < 20:
            return "unknown"
        # Check ELF magic number
        if header[:4] != b"\x7fELF":
            return "unknown"
        
        # Machine is at byte 18-19 in ELF header (little-endian)
        machine = int.from_bytes(header[18:20], byteorder="little")
        if machine == 0x3e:
            return "x86_64"
        elif machine == 0xb7:
            return "arm64"
        elif machine in [0x03, 0x28]:
            return "32bit"
        else:
            return "unknown"
    except Exception:
        return "unknown"

def is_binary_compatible(path: Path) -> bool:
    """Checks if the ELF binary is compatible with the host architecture."""
    host = platform.machine().lower()
    
    # Normalize host
    if host in ["x86_64", "amd64", "x64"]:
        host_norm = "x86_64"
    elif host in ["aarch64", "arm64"]:
        host_norm = "arm64"
    else:
        host_norm = host
        
    binary_arch = check_elf_binary_architecture(path)
    if binary_arch == "unknown":
        # If it's a shell script wrapper (like Proton script) or not ELF, we assume True
        return True
        
    if host_norm == "x86_64":
        if binary_arch == "32bit":
            # 32-bit ELF binaries require 32-bit dynamic loader / multilib
            if not os.path.exists("/lib/ld-linux.so.2") and not os.path.exists("/lib32/ld-linux.so.2"):
                return False
        return binary_arch in ["x86_64", "32bit"] # 32-bit can run on 64-bit host
    elif host_norm == "arm64":
        if binary_arch == "32bit":
            if not os.path.exists("/lib/ld-linux-armhf.so.3"):
                return False
        return binary_arch in ["arm64", "32bit"] # ARM 32-bit/64-bit
        
    return True

def ensure_winetricks(force_download: bool = False) -> str:
    """Ensures winetricks is available. Returns the path to the downloaded executable."""
    local_path = Path("~/.local/share/cheapwine/bin/winetricks").expanduser()
    
    if not force_download:
        # Check local path
        if local_path.exists() and os.access(local_path, os.X_OK):
            return str(local_path.absolute())
        
    # Download winetricks
    local_path.parent.mkdir(parents=True, exist_ok=True)
    url = "https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks"
    
    print_info("Download", "Downloading the latest winetricks script from master...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cheapwine-winetricks-downloader"})
        with urllib.request.urlopen(req) as response:
            content = response.read()
            
        local_path.write_bytes(content)
        # Make it executable (chmod +x)
        os.chmod(local_path, 0o755)
        print_step("Downloaded", f"Winetricks successfully installed at {local_path.name}")
        return str(local_path.absolute())
    except Exception as e:
        print_error(f"Failed to download winetricks: {e}")
        sys.exit(1)


def ensure_chocolatey(project) -> str:
    """Ensures Chocolatey is installed inside the Wine prefix.
    Returns the path to choco.exe inside the prefix.
    """
    import shutil
    import subprocess
    from cheapwine.wine import execute_command

    prefix_path = project.prefix_path
    choco_exe = prefix_path / "drive_c" / "ProgramData" / "chocolatey" / "bin" / "choco.exe"

    if choco_exe.exists():
        return str(choco_exe)

    print_info("Chocolatey", "Chocolatey not found in prefix. Installing...")

    url = "https://github.com/PietJankbal/Chocolatey-for-wine/releases/download/v0.5c.755/Chocolatey-for-wine.7z"
    archive_path = download_file_with_progress(url, "Chocolatey-for-wine.7z")

    extract_dir = RUNNERS_DIR / "chocolatey-installer"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    extracted = False
    for cmd in ["7z", "7za"]:
        sevenz_path = shutil.which(cmd)
        if sevenz_path:
            try:
                subprocess.run(
                    [sevenz_path, "x", str(archive_path), f"-o{extract_dir}", "-y"],
                    check=True, capture_output=True
                )
                extracted = True
                break
            except subprocess.CalledProcessError:
                continue

    if not extracted:
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        print_error(
            "Failed to extract Chocolatey installer. "
            "Please install 'p7zip' or 'p7zip-full' package, or 'py7zr' Python library."
        )
        sys.exit(1)

    installer_exe = None
    for f in extract_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() == ".exe" and "chocinstaller" in f.name.lower():
            installer_exe = f
            break

    if not installer_exe:
        shutil.rmtree(extract_dir)
        print_error("Could not find Chocolatey installer executable in the archive.")
        sys.exit(1)

    print_info("Chocolatey", "Running Chocolatey installer inside Wine prefix (this may take a while)...")
    exit_code = execute_command(project, [str(installer_exe), "/q"])

    shutil.rmtree(extract_dir)

    if exit_code != 0:
        print_error(f"Chocolatey installer failed with exit code {exit_code}.")
        sys.exit(1)

    if not choco_exe.exists():
        print_error("Chocolatey installation completed but choco.exe was not found.")
        sys.exit(1)

    print_step("Chocolatey", "Successfully installed in Wine prefix")
    return str(choco_exe)
