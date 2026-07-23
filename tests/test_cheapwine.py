import unittest
import os
import shutil
import json
from pathlib import Path
from click.testing import CliRunner
from cheapwine.cli import cli
from cheapwine.project import Project
from unittest.mock import patch

class TestCheapwine(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.test_dir = Path("./tmp_test_cheapwine").resolve()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True)
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_init_explicit(self):
        """Test explicit cheapwine init creates distillery.json."""
        # Run init command without initializing wineprefix mock since we can skip/mock prefix init
        # or let it run (but to keep tests fast, we can test that files are created)
        # Note: cheapwine init will run wineboot, which takes time, so we mock/check distillery.json
        result = self.runner.invoke(cli, ["init"])
        self.assertEqual(result.exit_code, 0)
        
        # Verify distillery.json is created
        config_path = self.test_dir / "distillery.json"
        self.assertTrue(config_path.exists())
        
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["wine_arch"], "win64")
        self.assertEqual(data["name"], "tmp_test_cheapwine")

    def test_add_remove_list_apps(self):
        """Test adding, listing, and removing apps in cheapwine."""
        # 1. Initialize project
        self.runner.invoke(cli, ["init"])
        
        # 2. Add an app
        result = self.runner.invoke(cli, ["add", "mygame", "bin/game.exe", "arg1", "--flag", "-e", "MYVAR=123", "-w", "bin/"])
        self.assertEqual(result.exit_code, 0)
        
        # Verify in config
        project = Project(self.test_dir)
        app = project.get_app("mygame")
        self.assertIsNotNone(app)
        self.assertEqual(app["exe"], "bin/game.exe")
        self.assertEqual(app["args"], ["arg1", "--flag"])
        self.assertEqual(app["env"], {"MYVAR": "123"})
        self.assertEqual(app["workdir"], "bin/")
        
        # 3. List apps
        list_result = self.runner.invoke(cli, ["list"])
        self.assertEqual(list_result.exit_code, 0)
        self.assertIn("mygame", list_result.output)
        
        # 4. Remove app
        remove_result = self.runner.invoke(cli, ["remove", "mygame"])
        self.assertEqual(remove_result.exit_code, 0)
        self.assertIsNone(project.get_app("mygame"))

    def test_init_env_configuration(self):
        """Test cheapwine init with --env / -e options to set and update project environment variables."""
        # 1. Initialize project with environment variables
        result = self.runner.invoke(cli, ["init", "--env", "FOO=bar", "-e", "BAZ=qux"])
        self.assertEqual(result.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["env"].get("FOO"), "bar")
        self.assertEqual(data["env"].get("BAZ"), "qux")
        self.assertEqual(data["env"].get("WINEDEBUG"), "-all")
        
        # 2. Update existing project env with cheapwine init
        result_update = self.runner.invoke(cli, ["init", "-e", "FOO=updated", "-e", "NEWKEY=newval"])
        self.assertEqual(result_update.exit_code, 0)
        
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["env"].get("FOO"), "updated")
        self.assertEqual(data["env"].get("BAZ"), "qux")
        self.assertEqual(data["env"].get("NEWKEY"), "newval")

    def test_init_name_and_wine_version(self):
        """Test cheapwine init with --name / -n and --wine-version options."""
        # 1. Initialize project with name and wine-version
        result = self.runner.invoke(cli, ["init", "--name", "my-custom-project", "--wine-version", "9.0"])
        self.assertEqual(result.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "my-custom-project")
        self.assertEqual(data["wine_version"], "9.0")
        
        # 2. Update existing project name and wine-version
        result_update = self.runner.invoke(cli, ["init", "-n", "updated-project", "--wine-version", "9.1"])
        self.assertEqual(result_update.exit_code, 0)
        
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "updated-project")
        self.assertEqual(data["wine_version"], "9.1")

    def test_win_version_configuration(self):
        """Test initializing with custom win_version and updating it."""
        # 1. Init with custom version
        result = self.runner.invoke(cli, ["init", "--win-version", "win95", "--arch", "win32"])
        self.assertEqual(result.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["win_version"], "win95")
        self.assertEqual(data["wine_arch"], "win32")
        
        # 2. Update existing configuration
        result_update = self.runner.invoke(cli, ["init", "--win-version", "winxp"])
        self.assertEqual(result_update.exit_code, 0)
        
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["win_version"], "winxp")

    def test_app_specific_win_version(self):
        """Test adding and running an app with app-specific win_version."""
        self.runner.invoke(cli, ["init"])
        
        # Add app with app-specific win-version
        result = self.runner.invoke(cli, ["add", "legacyapp", "bin/legacy.exe", "--win-version", "win95"])
        self.assertEqual(result.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["apps"]["legacyapp"]["win_version"], "win95")

    def test_app_specific_wine_arch(self):
        """Test adding an app with app-specific wine_arch override."""
        self.runner.invoke(cli, ["init"])
        
        # Add app with app-specific wine-arch
        result = self.runner.invoke(cli, ["add", "win32app", "bin/win32.exe", "--arch", "win32"])
        self.assertEqual(result.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["apps"]["win32app"]["wine_arch"], "win32")

    def test_tui_invocations(self):
        """Test that cheapwine tui and cheapwine run without args call run_tui."""
        from unittest.mock import patch
        self.runner.invoke(cli, ["init"])
        
        with patch("cheapwine.tui.run_tui") as mock_run_tui:
            # 1. Test cheapwine tui command
            result = self.runner.invoke(cli, ["tui"])
            self.assertEqual(result.exit_code, 0)
            mock_run_tui.assert_called_once()
            
            # 2. Test cheapwine run command with no arguments
            mock_run_tui.reset_mock()
            result_run = self.runner.invoke(cli, ["run"])
            self.assertEqual(result_run.exit_code, 0)
            mock_run_tui.assert_called_once()

    def test_list_all_and_detected(self):
        """Test listing registered and auto-detected applications."""
        from unittest.mock import patch
        self.runner.invoke(cli, ["init"])
        self.runner.invoke(cli, ["add", "registered_app", "reg.exe"])
        
        # Mock scan_installed_apps to return one detected app
        mock_detected = [{"name": "detected_app", "exe": "C:\\Program Files\\detected.exe", "source": "C:\\Program Files"}]
        with patch("cheapwine.tui.scan_installed_apps", return_value=mock_detected):
            # Test list only registered (default)
            res_default = self.runner.invoke(cli, ["list"])
            self.assertEqual(res_default.exit_code, 0)
            self.assertIn("registered_app", res_default.output)
            self.assertNotIn("detected_app", res_default.output)
            
            # Test list all (-a)
            res_all = self.runner.invoke(cli, ["list", "-a"])
            self.assertEqual(res_all.exit_code, 0)
            self.assertIn("registered_app", res_all.output)
            self.assertIn("detected_app", res_all.output)
            
            # Test list only detected (-d)
            res_det = self.runner.invoke(cli, ["list", "-d"])
            self.assertEqual(res_det.exit_code, 0)
            self.assertNotIn("registered_app", res_det.output)
            self.assertIn("detected_app", res_det.output)

    def test_add_auto_detected(self):
        """Test adding an application by auto-detecting it."""
        from unittest.mock import patch
        self.runner.invoke(cli, ["init"])
        
        mock_detected = [{"name": "superapp", "exe": "C:\\Program Files\\superapp.exe", "source": "C:\\Program Files"}]
        with patch("cheapwine.tui.scan_installed_apps", return_value=mock_detected):
            # Try to add without providing executable path
            result = self.runner.invoke(cli, ["add", "superapp"])
            self.assertEqual(result.exit_code, 0)
            
            # Verify it is in the config
            project = Project(self.test_dir)
            app = project.get_app("superapp")
            self.assertIsNotNone(app)
            self.assertEqual(app["exe"], "C:\\Program Files\\superapp.exe")
            
            # Try to add something that is not auto-detected (should fall back to name.exe)
            result_fallback = self.runner.invoke(cli, ["add", "unknownapp"])
            self.assertEqual(result_fallback.exit_code, 0)
            app_fallback = Project(self.test_dir).get_app("unknownapp")
            self.assertIsNotNone(app_fallback)
            self.assertEqual(app_fallback["exe"], "unknownapp.exe")

    def test_export_unexport_command(self):
        """Test exporting and unexporting desktop launchers."""
        self.runner.invoke(cli, ["init"])
        self.runner.invoke(cli, ["add", "myapp", "C:\\Program Files\\myapp.exe"])
        
        # We can export the app. This creates a .desktop file
        result_export = self.runner.invoke(cli, ["export", "myapp"])
        self.assertEqual(result_export.exit_code, 0)
        self.assertIn("Exported", result_export.output)
        
        # Verify the .desktop file was created under ~/.local/share/applications/
        desktop_dir = Path("~/.local/share/applications").expanduser()
        safe_proj_name = self.test_dir.name.replace(" ", "_").lower()
        safe_app_name = "myapp".replace(" ", "_").lower()
        desktop_file_path = desktop_dir / f"{safe_app_name}.desktop"
        
        self.assertTrue(desktop_file_path.exists())
        content = desktop_file_path.read_text(encoding="utf-8")
        self.assertIn("Name=myapp\n", content)
        self.assertNotIn(f"Name={self.test_dir.name} - myapp\n", content)
        
        # Test unexporting
        result_unexport = self.runner.invoke(cli, ["unexport", "myapp"])
        self.assertEqual(result_unexport.exit_code, 0)
        self.assertIn("Unexported", result_unexport.output)
        self.assertFalse(desktop_file_path.exists())

    def test_export_custom_icon(self):
        """Test exporting an application with a custom icon image, SVG, and theme name."""
        from PIL import Image
        self.runner.invoke(cli, ["init"])
        self.runner.invoke(cli, ["add", "iconapp", "C:\\Program Files\\iconapp.exe"])

        # 1. Custom PNG image (non-square to test padding and resizing)
        icon_path = self.test_dir / "my_icon.png"
        img = Image.new("RGB", (128, 64), color="blue")
        img.save(icon_path)

        result_export = self.runner.invoke(cli, ["export", "iconapp", "--icon", str(icon_path)])
        self.assertEqual(result_export.exit_code, 0)
        self.assertIn("Exported", result_export.output)

        desktop_file = Path("~/.local/share/applications/iconapp.desktop").expanduser()
        self.assertTrue(desktop_file.exists())
        content = desktop_file.read_text(encoding="utf-8")
        self.assertIn("Icon=cheapwine-iconapp", content)

        # Check installed icon file exists in hicolor theme
        hicolor_icon = Path("~/.local/share/icons/hicolor/128x128/apps/cheapwine-iconapp.png").expanduser()
        self.assertTrue(hicolor_icon.exists())

        # 2. Custom SVG file
        svg_path = self.test_dir / "vector_icon.svg"
        svg_path.write_text("<svg><rect width='10' height='10'/></svg>", encoding="utf-8")

        result_svg = self.runner.invoke(cli, ["export", "iconapp", "-i", str(svg_path)])
        self.assertEqual(result_svg.exit_code, 0)

        svg_hicolor = Path("~/.local/share/icons/hicolor/scalable/apps/cheapwine-iconapp.svg").expanduser()
        self.assertTrue(svg_hicolor.exists())

        # 3. Icon theme name
        result_theme = self.runner.invoke(cli, ["export", "iconapp", "--icon", "firefox"])
        self.assertEqual(result_theme.exit_code, 0)
        content_theme = desktop_file.read_text(encoding="utf-8")
        self.assertIn("Icon=firefox", content_theme)

    def test_unexport_coexistence(self):
        """Test that unexporting a registered app also unexports its auto-detected counterpart and vice-versa."""
        from unittest.mock import patch
        self.runner.invoke(cli, ["init"])
        self.runner.invoke(cli, ["add", "steam_registered", "C:\\Program Files\\Steam\\Steam.exe"])
        
        desktop_dir = Path("~/.local/share/applications").expanduser()
        safe_proj_name = self.test_dir.name.replace(" ", "_").lower()
        
        desktop_file_reg = desktop_dir / "steam_registered.desktop"
        desktop_file_det = desktop_dir / "steam.desktop"
        
        # Helper to recreate both desktop files
        def create_desktop_files():
            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop_file_reg.write_text("[Desktop Entry]\nName=Steam Registered", encoding="utf-8")
            desktop_file_det.write_text("[Desktop Entry]\nName=Steam Detected", encoding="utf-8")
            
        mock_detected = [{"name": "Steam", "exe": "C:\\Program Files\\Steam\\Steam.exe", "source": "Wine Start Menu"}]
        
        # Test Case 1: unexporting registered app also unexports auto-detected app
        create_desktop_files()
        self.assertTrue(desktop_file_reg.exists())
        self.assertTrue(desktop_file_det.exists())
        
        with patch("cheapwine.tui.scan_installed_apps", return_value=mock_detected):
            result = self.runner.invoke(cli, ["unexport", "steam_registered"])
            self.assertEqual(result.exit_code, 0)
            
        self.assertFalse(desktop_file_reg.exists())
        self.assertFalse(desktop_file_det.exists())
        
        # Test Case 2: unexporting auto-detected app also unexports registered app
        create_desktop_files()
        self.assertTrue(desktop_file_reg.exists())
        self.assertTrue(desktop_file_det.exists())
        
        with patch("cheapwine.tui.scan_installed_apps", return_value=mock_detected):
            result = self.runner.invoke(cli, ["unexport", "Steam"])
            self.assertEqual(result.exit_code, 0)
            
        self.assertFalse(desktop_file_reg.exists())
        self.assertFalse(desktop_file_det.exists())

    def test_runner_overrides(self):
        """Test global and app-specific Wine runner overrides."""
        # 1. Test init with custom global runner
        result_init = self.runner.invoke(cli, ["init", "--runner", "/usr/bin/proton run"])
        self.assertEqual(result_init.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["runner"], "/usr/bin/proton run")
        
        # 2. Test adding app with custom runner override
        result_add = self.runner.invoke(cli, ["add", "mygame", "game.exe", "--runner", "/usr/local/bin/wine-custom"])
        self.assertEqual(result_add.exit_code, 0)
        
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["apps"]["mygame"]["runner"], "/usr/local/bin/wine-custom")

    def test_help_and_disabled_auto_init(self):
        """Test that running without command prints help, and other commands fail without init."""
        # 1. Running cheapwine alone prints help (exit code 0)
        result_help = self.runner.invoke(cli)
        self.assertEqual(result_help.exit_code, 0)
        self.assertIn("cheapwine: A lightweight, project-based Wine prefix", result_help.output)
        
        # 2. Running cheapwine list without init fails with exit code 1
        result_list = self.runner.invoke(cli, ["list"])
        self.assertEqual(result_list.exit_code, 1)
        self.assertIn("No cheapwine project found. Run cheapwine init to start one.", result_list.output)

    @patch("subprocess.run")
    def test_runner_auto_download(self, mock_run):
        """Test auto-downloading when a downloadable runner is specified."""
        from unittest.mock import patch, MagicMock
        
        # Configure subprocess.run to simulate success
        mock_run.return_value = MagicMock(returncode=0)
        
        # Mock resolve_and_download_runner to simulate successful download without hitting GitHub
        mocked_path = "/home/heap/.local/share/cheapwine/runners/proton-ge-8-25/files/bin/wine"
        with patch("cheapwine.runners.resolve_and_download_runner", return_value=mocked_path) as mock_download:
            result_init = self.runner.invoke(cli, ["init", "--runner", "proton-ge-8-25"])
            self.assertEqual(result_init.exit_code, 0)
            
            # Verify resolve_and_download_runner was called with the runner name
            mock_download.assert_any_call("proton-ge-8-25")
            
            # Verify it printed the runner used (robust against console wrapping)
            self.assertIn("using runner", result_init.output)
            self.assertIn("proton-ge-8-25", result_init.output)
            
            # Verify distillery.json stored it
            config_path = self.test_dir / "distillery.json"
            with open(config_path, "r") as f:
                data = json.load(f)
            self.assertEqual(data["runner"], "proton-ge-8-25")

    @patch("subprocess.run")
    def test_run_unregistered_app(self, mock_run):
        """Test running an unregistered application or command."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        
        self.runner.invoke(cli, ["init"])
        result = self.runner.invoke(cli, ["run", "notepad.exe"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Running", result.output)
        self.assertIn("Executable/Command", result.output)

    @patch("subprocess.run")
    def test_run_detected_app(self, mock_run):
        """Test that cheapwine run can execute an unregistered auto-detected app."""
        from unittest.mock import MagicMock, patch
        mock_run.return_value = MagicMock(returncode=0)
        
        self.runner.invoke(cli, ["init"])
        
        mock_detected = [{"name": "Steam", "exe": "C:\\Program Files\\Steam\\steam.exe", "source": "C:\\Program Files"}]
        with patch("cheapwine.tui.scan_installed_apps", return_value=mock_detected):
            # Run using the detected name "Steam" without adding it first
            result = self.runner.invoke(cli, ["run", "Steam"])
            self.assertEqual(result.exit_code, 0)
            self.assertIn("Running", result.output)
            self.assertIn("Auto-detected app", result.output)
            self.assertIn("steam.exe", result.output)

    def test_arch_filtering(self):
        """Test that only matching architectures are accepted by the downloader."""
        from cheapwine.runners import is_matching_arch
        from unittest.mock import patch
        
        # Test on x86_64 machine
        with patch("platform.machine", return_value="x86_64"):
            self.assertTrue(is_matching_arch("GE-Proton11-1.tar.gz"))
            self.assertFalse(is_matching_arch("GE-Proton11-1-aarch64.tar.gz"))
            self.assertFalse(is_matching_arch("GE-Proton11-1-arm64.tar.gz"))
            
        # Test on aarch64 machine
        with patch("platform.machine", return_value="aarch64"):
            self.assertTrue(is_matching_arch("GE-Proton11-1-aarch64.tar.gz"))
            self.assertTrue(is_matching_arch("GE-Proton11-1-arm64.tar.gz"))
            self.assertFalse(is_matching_arch("GE-Proton11-1.tar.gz"))

    @patch("subprocess.run")
    def test_self_healing_runner(self, mock_run):
        """Test that incompatible pre-existing runner binary is deleted and re-downloaded."""
        from unittest.mock import patch, MagicMock
        from cheapwine.runners import resolve_and_download_runner, RUNNERS_DIR
        
        # 1. Create a dummy incompatible arm64 runner binary inside runners directory
        dummy_dir = RUNNERS_DIR / "proton-ge-8-25"
        dummy_bin_dir = dummy_dir / "files" / "bin"
        dummy_bin_dir.mkdir(parents=True, exist_ok=True)
        dummy_wine = dummy_bin_dir / "wine"
        
        # Write ELF arm64 header: \x7fELF + 14 padding bytes + \xb7\x00 (machine 0xb7 = arm64)
        elf_header = b"\x7fELF" + b"\x00"*14 + b"\xb7\x00"
        dummy_wine.write_bytes(elf_header)
        
        # Ensure it exists
        self.assertTrue(dummy_wine.exists())
        
        # Mock resolve_and_download_runner's actual download to return a clean mock path
        # and patch platform.machine to "x86_64" so arm64 is incompatible!
        mocked_path = dummy_bin_dir / "wine_new"
        
        def mock_extract_impl(archive_path, target_dir):
            dummy_bin_dir.mkdir(parents=True, exist_ok=True)
            mocked_path.write_text("dummy binary")
        
        with patch("platform.machine", return_value="x86_64"), \
             patch("cheapwine.runners.fetch_github_release", return_value=("GE-Proton8-25", "http://dummy", "GE-Proton8-25.tar.gz")), \
             patch("cheapwine.runners.download_file_with_progress", return_value=Path("/tmp/dummy.tar.gz")), \
             patch("cheapwine.runners.extract_archive", side_effect=mock_extract_impl) as mock_extract, \
             patch("cheapwine.runners.find_wine_binary", side_effect=[dummy_wine, dummy_wine, mocked_path]):
                 
            # Run resolver. It should detect dummy_wine is arm64 (incompatible), delete it, and download!
            resolve_and_download_runner("proton-ge-8-25")
            
            # Verify the incompatible runner folder was deleted
            self.assertFalse(dummy_wine.exists())
            
            # Verify mock_extract was called to extract the new download
            mock_extract.assert_called()

    def test_kron4ek_staging_resolution(self):
        """Test that Kron4ek staging is prioritized when staging is specified in the runner name, and vanilla is prioritized otherwise."""
        from cheapwine.runners import fetch_github_release
        from unittest.mock import patch, MagicMock
        import io

        mock_release_data = {
            "tag_name": "11.11",
            "assets": [
                {"name": "wine-11.11-amd64-wow64.tar.xz", "browser_download_url": "http://dummy/vanilla"},
                {"name": "wine-11.11-staging-amd64-wow64.tar.xz", "browser_download_url": "http://dummy/staging"}
            ]
        }
        
        # We need mock_urlopen to return mock_release_data when called
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_release_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        
        # Test Case 1: staging requested
        with patch("urllib.request.urlopen", return_value=mock_response), \
             patch("platform.machine", return_value="x86_64"):
            tag, url, asset_name = fetch_github_release("Kron4ek/Wine-Builds", "11.11", "kron4ek-11.11-staging")
            self.assertEqual(tag, "11.11")
            self.assertEqual(url, "http://dummy/staging")
            self.assertEqual(asset_name, "wine-11.11-staging-amd64-wow64.tar.xz")
            
        # Test Case 2: vanilla requested (no staging in runner name)
        mock_response.read.return_value = json.dumps(mock_release_data).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_response), \
             patch("platform.machine", return_value="x86_64"):
            tag, url, asset_name = fetch_github_release("Kron4ek/Wine-Builds", "11.11", "kron4ek-11.11")
            self.assertEqual(tag, "11.11")
            self.assertEqual(url, "http://dummy/vanilla")
            self.assertEqual(asset_name, "wine-11.11-amd64-wow64.tar.xz")

    def test_local_runner_prioritized_over_network(self):
        """Test that resolve_and_download_runner returns locally installed runner without calling GitHub API."""
        from cheapwine.runners import resolve_and_download_runner, RUNNERS_DIR
        from unittest.mock import patch
        
        # 1. Create a dummy compatible local runner binary
        dummy_dir = RUNNERS_DIR / "proton-ge-8-26"
        dummy_bin_dir = dummy_dir / "files" / "bin"
        dummy_bin_dir.mkdir(parents=True, exist_ok=True)
        dummy_wine = dummy_bin_dir / "wine"
        
        # Write ELF x86_64 header: \x7fELF + 14 padding bytes + \x3e\x00 (machine 0x3e = x86_64)
        elf_header = b"\x7fELF" + b"\x00"*14 + b"\x3e\x00"
        dummy_wine.write_bytes(elf_header)
        
        # Patch fetch_github_release to raise an error to prove it was never called
        with patch("platform.machine", return_value="x86_64"), \
             patch("cheapwine.runners.fetch_github_release", side_effect=AssertionError("fetch_github_release should not be called")):
            
            result = resolve_and_download_runner("proton-ge-8-26")
            self.assertEqual(result, str(dummy_wine.absolute()))
            
        # Clean up
        shutil.rmtree(dummy_dir)

    @patch("subprocess.run")
    def test_winetricks_auto_download(self, mock_run):
        """Test that winetricks command always downloads a local copy and does not use system PATH."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        
        self.runner.invoke(cli, ["init"])
        
        # Test when winetricks is NOT yet cached locally (simulates downloading local winetricks)
        local_path = Path("~/.local/share/cheapwine/bin/winetricks").expanduser()
        if local_path.exists():
            local_path.unlink()
            
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("os.chmod") as mock_chmod:
                  
            # Configure mock urlopen read to return binary script content
            mock_response = MagicMock()
            mock_response.read.return_value = b"#!/bin/bash\necho winetricks"
            mock_urlopen.return_value.__enter__.return_value = mock_response
            
            result = self.runner.invoke(cli, ["winetricks", "corefonts"])
            self.assertEqual(result.exit_code, 0)
            
            # Verify the file was written to ~/.local/share/cheapwine/bin/winetricks
            self.assertTrue(local_path.exists())
            self.assertEqual(local_path.read_text(), "#!/bin/bash\necho winetricks")
            mock_chmod.assert_called_with(local_path, 0o755)
            
            # Cleanup
            local_path.unlink()

    @patch("subprocess.run")
    def test_runner_and_version_split(self, mock_run):
        """Test split runner and runner_version configuration in distillery.json."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        
        # 1. Test init with runner and version
        result_init = self.runner.invoke(cli, ["init", "--runner", "proton-ge", "--runner-version", "11-1"])
        self.assertEqual(result_init.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["runner"], "proton-ge")
        self.assertEqual(data["runner_version"], "11-1")
        
        # 2. Test add app with runner and version
        result_add = self.runner.invoke(cli, ["add", "mygame", "game.exe", "--runner", "wine-ge", "--runner-version", "8-26"])
        self.assertEqual(result_add.exit_code, 0)
        
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["apps"]["mygame"]["runner"], "wine-ge")
        self.assertEqual(data["apps"]["mygame"]["runner_version"], "8-26")
        
        # 3. Test running combined name resolution
        # Mock resolve_and_download_runner to see what runner path it requests
        mocked_path = "/home/heap/.local/share/cheapwine/runners/wine-ge-8-26/files/bin/wine"
        with patch("cheapwine.runners.resolve_and_download_runner", return_value=mocked_path) as mock_download:
            result_run = self.runner.invoke(cli, ["run", "mygame"])
            self.assertEqual(result_run.exit_code, 0)
            mock_download.assert_any_call("wine-ge-8-26")

    @patch("subprocess.run")
    def test_declarative_winetricks(self, mock_run):
        """Test declarative winetricks DLLs and components configuration in distillery.json."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        
        # 1. Initialize project and add app with tricks override
        self.runner.invoke(cli, ["init"])
        result_add = self.runner.invoke(cli, ["add", "mygame", "game.exe", "--tricks", "dxvk", "--tricks", "d3dcompiler_43"])
        self.assertEqual(result_add.exit_code, 0)
        
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["apps"]["mygame"]["winetricks"], ["dxvk", "d3dcompiler_43"])
        
        # 2. Run the application
        with patch("cheapwine.runners.ensure_winetricks", return_value="/usr/bin/winetricks"), \
             patch("cheapwine.runners.is_binary_compatible", return_value=True):
            
            result_run = self.runner.invoke(cli, ["run", "mygame"])
            self.assertEqual(result_run.exit_code, 0)
            
            # Verify winetricks execution occurred with correct args
            winetricks_called = False
            for call in mock_run.call_args_list:
                args = call[0][0]
                if len(args) >= 2 and args[0] == "/usr/bin/winetricks":
                    self.assertEqual(args[1], "-q")
                    self.assertIn("dxvk", args)
                    self.assertIn("d3dcompiler_43", args)
                    winetricks_called = True
            self.assertTrue(winetricks_called)
            
            # Check cache state file cheapwine_tricks.json was created
            state_file = self.test_dir / ".cheapwine" / "cheapwine_tricks.json"
            self.assertTrue(state_file.exists())
            with open(state_file, "r") as f:
                state_data = json.load(f)
            self.assertIn("dxvk", state_data)
            self.assertIn("d3dcompiler_43", state_data)
            
            # Reset mock and run again. It should NOT execute winetricks since it is in cache!
            mock_run.reset_mock()
            result_run_again = self.runner.invoke(cli, ["run", "mygame"])
            self.assertEqual(result_run_again.exit_code, 0)
            
            # Verify no winetricks execution occurred
            for call in mock_run.call_args_list:
                args = call[0][0]
                self.assertNotIn("/usr/bin/winetricks", args)

    @patch("os.isatty", return_value=True)
    @patch("sys.stdin.fileno", return_value=0)
    @patch("termios.tcgetattr")
    @patch("termios.tcsetattr")
    @patch("tty.setraw")
    @patch("sys.stdin.read")
    def test_easydistill_tui_main(self, mock_read, mock_setraw, mock_tcsetattr, mock_tcgetattr, mock_fileno, mock_isatty):
        """Test easydistill command starts and responds to TUI inputs."""
        # Configure mock_read to return 'q' immediately to exit the main loop
        mock_read.return_value = "q"
        
        os.environ["CHEAPWINE_TESTING"] = "1"
        try:
            self.runner.invoke(cli, ["init"])
            result = self.runner.invoke(cli, ["easydistill"], input="q")
            self.assertEqual(result.exit_code, 0)
            self.assertIn("cheapwine EasyDistill", result.output)
            self.assertIn("Main Menu", result.output)
        finally:
            del os.environ["CHEAPWINE_TESTING"]

    def test_env_output(self):
        """Test cheapwine env exports match expected prefix paths."""
        self.runner.invoke(cli, ["init"])
        result = self.runner.invoke(cli, ["env"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("export WINEPREFIX=", result.output)
        self.assertIn("export WINEARCH=win64", result.output)

    @patch("subprocess.run")
    def test_latencyflex_support(self, mock_run):
        """Test global and application-specific LatencyFleX support."""
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        
        # 1. Test init with --latencyflex
        self.runner.invoke(cli, ["init", "--latencyflex"])
        config_path = self.test_dir / "distillery.json"
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertTrue(data["latencyflex"])
        
        # 2. Test running app with global latencyflex
        result = self.runner.invoke(cli, ["run", "notepad.exe"])
        self.assertEqual(result.exit_code, 0)
        
        # Check that environment variables for LatencyFleX were set in mock_run call for notepad.exe
        lfx_in_env = False
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd and cmd[-1] == "notepad.exe":
                env = call[1].get("env", {})
                if env.get("LFX") == "1" and env.get("PROTON_ENABLE_NVAPI") == "1":
                    lfx_in_env = True
        self.assertTrue(lfx_in_env)
        
        # 3. Disable global latencyflex
        self.runner.invoke(cli, ["init", "--no-latencyflex"])
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertFalse(data["latencyflex"])
        
        # 4. Add application with application-specific override --latencyflex
        self.runner.invoke(cli, ["add", "mygame", "game.exe", "--latencyflex"])
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertTrue(data["apps"]["mygame"]["latencyflex"])
        
        # 5. Run mygame, verify it has LatencyFleX enabled
        mock_run.reset_mock()
        self.runner.invoke(cli, ["run", "mygame"])
        lfx_in_env = False
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd and cmd[-1] == "game.exe":
                env = call[1].get("env", {})
                if env.get("LFX") == "1" and env.get("PROTON_ENABLE_NVAPI") == "1":
                    lfx_in_env = True
        self.assertTrue(lfx_in_env)
        
        # 6. Add application with override --no-latencyflex when global is true
        self.runner.invoke(cli, ["init", "--latencyflex"])
        self.runner.invoke(cli, ["add", "mygame2", "game.exe", "--no-latencyflex"])
        with open(config_path, "r") as f:
            data = json.load(f)
        self.assertFalse(data["apps"]["mygame2"]["latencyflex"])
        
        # Run mygame2, verify it does NOT have LatencyFleX enabled
        mock_run.reset_mock()
        self.runner.invoke(cli, ["run", "mygame2"])
        lfx_in_env = False
        for call in mock_run.call_args_list:
            cmd = call[0][0]
            if cmd and cmd[-1] == "game.exe":
                env = call[1].get("env", {})
                if env.get("LFX") == "1":
                    lfx_in_env = True
        self.assertFalse(lfx_in_env)

    @patch("subprocess.run")
    def test_chocolatey_already_installed(self, mock_run):
        """Test chocolatey command when choco.exe already exists in prefix."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        self.runner.invoke(cli, ["init"])

        choco_exe = self.test_dir / ".cheapwine" / "drive_c" / "ProgramData" / "chocolatey" / "bin" / "choco.exe"
        choco_exe.parent.mkdir(parents=True, exist_ok=True)
        choco_exe.touch()

        result = self.runner.invoke(cli, ["chocolatey", "list"])
        self.assertEqual(result.exit_code, 0)

    @patch("subprocess.run")
    def test_chocolatey_install_and_run(self, mock_run):
        """Test chocolatey command triggers install when choco.exe is missing."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        self.runner.invoke(cli, ["init"])

        choco_exe_path = str(self.test_dir / ".cheapwine" / "drive_c" / "ProgramData" / "chocolatey" / "bin" / "choco.exe")

        with patch("cheapwine.runners.ensure_chocolatey", return_value=choco_exe_path) as mock_ensure:
            result = self.runner.invoke(cli, ["chocolatey", "install", "firefox"])
            self.assertEqual(result.exit_code, 0)
            mock_ensure.assert_called_once()

    @patch("subprocess.run")
    def test_chocolatey_no_args_shows_help(self, mock_run):
        """Test chocolatey with no args defaults to --help."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        self.runner.invoke(cli, ["init"])

        choco_exe = self.test_dir / ".cheapwine" / "drive_c" / "ProgramData" / "chocolatey" / "bin" / "choco.exe"
        choco_exe.parent.mkdir(parents=True, exist_ok=True)
        choco_exe.touch()

        result = self.runner.invoke(cli, ["chocolatey"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("help", result.output.lower())

    @patch("subprocess.run")
    def test_kron4ek_soda_runners(self, mock_run):
        """Test resolving and downloading Kron4ek and Soda runners."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        
        mocked_kron4ek_path = "/home/heap/.local/share/cheapwine/runners/kron4ek-9.0/bin/wine"
        mocked_soda_path = "/home/heap/.local/share/cheapwine/runners/soda-9.0-1/files/bin/wine"
        
        with patch("cheapwine.runners.resolve_and_download_runner") as mock_resolve:
            mock_resolve.side_effect = lambda r: mocked_kron4ek_path if "kron4ek" in r else mocked_soda_path if "soda" in r else None
            
            # 1. Test init with Kron4ek runner
            result = self.runner.invoke(cli, ["init", "--runner", "kron4ek-9.0"])
            self.assertEqual(result.exit_code, 0)
            mock_resolve.assert_any_call("kron4ek-9.0")
            
            # 2. Test init with Soda runner
            result = self.runner.invoke(cli, ["init", "--runner", "soda-9.0-1"])
            self.assertEqual(result.exit_code, 0)
            mock_resolve.assert_any_call("soda-9.0-1")
            
            # 3. Test resolve_runner_name merges kron4ek and soda versions
            from cheapwine.wine import resolve_runner_name
            self.assertEqual(resolve_runner_name("kron4ek", "9.0"), "kron4ek-9.0")
            self.assertEqual(resolve_runner_name("soda", "9.0-1"), "soda-9.0-1")

    @patch("subprocess.run")
    def test_wine_d2d1_runner(self, mock_run):
        """Test resolving and downloading wine-d2d1 runner from mklnln/wine-d2d1-dcomp."""
        from unittest.mock import patch, MagicMock
        mock_run.return_value = MagicMock(returncode=0)

        mocked_d2d1_path = "/home/heap/.local/share/cheapwine/runners/wine-d2d1-11.0/wine-d2d1/bin/wine"

        with patch("cheapwine.runners.resolve_and_download_runner") as mock_resolve:
            mock_resolve.side_effect = lambda r: mocked_d2d1_path if any(k in r for k in ["wine-d2d1", "d2d1", "mklnln"]) else None

            # 1. Test init with wine-d2d1 runner
            result = self.runner.invoke(cli, ["init", "--runner", "wine-d2d1-11.0"])
            self.assertEqual(result.exit_code, 0)
            mock_resolve.assert_any_call("wine-d2d1-11.0")

            # 2. Test init with mklnln repo name
            result2 = self.runner.invoke(cli, ["init", "--runner", "mklnln/wine-d2d1-dcomp"])
            self.assertEqual(result2.exit_code, 0)
            mock_resolve.assert_any_call("mklnln/wine-d2d1-dcomp")

            # 3. Test resolve_runner_name merges wine-d2d1 version
            from cheapwine.wine import resolve_runner_name
            self.assertEqual(resolve_runner_name("wine-d2d1", "11.0"), "wine-d2d1-11.0")
            self.assertEqual(resolve_runner_name("d2d1", "11.0"), "d2d1-11.0")

    def test_fetch_github_release_d2d1(self):
        """Test fetching release asset for wine-d2d1-dcomp."""
        from cheapwine.runners import fetch_github_release
        from unittest.mock import patch, MagicMock

        mock_release_data = {
            "tag_name": "v11.0",
            "assets": [
                {"name": "wine-d2d1-11.0-x86_64.tar.zst", "browser_download_url": "http://dummy/wine-d2d1-11.0-x86_64.tar.zst"}
            ]
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_release_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", return_value=mock_response), \
             patch("platform.machine", return_value="x86_64"):
            tag, url, asset_name = fetch_github_release("mklnln/wine-d2d1-dcomp", "11.0", "wine-d2d1-11.0")
            self.assertEqual(tag, "v11.0")
            self.assertEqual(url, "http://dummy/wine-d2d1-11.0-x86_64.tar.zst")
            self.assertEqual(asset_name, "wine-d2d1-11.0-x86_64.tar.zst")

    def test_extract_icon_cli_nonexistent(self):
        """Test extract_icon with non-existent executable file."""
        result = self.runner.invoke(cli, ["extract_icon", "nonexistent.exe", "output.png"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not found", result.output.lower())

    def test_extract_icon_cli_success(self):
        """Test extract_icon with mocked extract_icon_to_file success."""
        dummy_exe = self.test_dir / "app.exe"
        dummy_exe.touch()
        target_img = self.test_dir / "out.png"

        with patch("cheapwine.cli.extract_icon_to_file", return_value=True) as mock_extract:
            result = self.runner.invoke(cli, ["extract_icon", str(dummy_exe), str(target_img)])
            self.assertEqual(result.exit_code, 0)
            mock_extract.assert_called_once()
            self.assertIn("Extracted", result.output)

    def test_extract_icon_hyphen_alias(self):
        """Test extract-icon hyphenated alias."""
        dummy_exe = self.test_dir / "app.exe"
        dummy_exe.touch()
        target_img = self.test_dir / "out.png"

        with patch("cheapwine.cli.extract_icon_to_file", return_value=True) as mock_extract:
            result = self.runner.invoke(cli, ["extract-icon", str(dummy_exe), str(target_img)])
            self.assertEqual(result.exit_code, 0)
            mock_extract.assert_called_once()

    def test_extract_icon_to_file_nonexistent_exe(self):
        """Test extract_icon_to_file returns False when exe does not exist."""
        from cheapwine.cli import extract_icon_to_file
        res = extract_icon_to_file("nonexistent_file.exe", "out.png")
        self.assertFalse(res)

    def test_extract_icon_registered_app(self):
        """Test resolving registered app name for extract_icon."""
        self.runner.invoke(cli, ["init"])
        exe_file = self.test_dir / "bin" / "game.exe"
        exe_file.parent.mkdir(parents=True, exist_ok=True)
        exe_file.touch()

        self.runner.invoke(cli, ["add", "mygame", str(exe_file)])

        from cheapwine.cli import resolve_target_exe
        resolved = resolve_target_exe("mygame")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved, exe_file.resolve())

    def test_extract_icon_autodetected_app(self):
        """Test resolving auto-detected app name for extract_icon."""
        self.runner.invoke(cli, ["init"])
        dummy_exe = self.test_dir / ".cheapwine" / "drive_c" / "Program Files" / "7-Zip" / "7zFM.exe"
        dummy_exe.parent.mkdir(parents=True, exist_ok=True)
        dummy_exe.touch()

        detected_app = [{"name": "7-Zip", "exe": "C:\\Program Files\\7-Zip\\7zFM.exe", "wine_arch": "win64"}]
        with patch("cheapwine.tui.scan_installed_apps", return_value=detected_app):
            from cheapwine.cli import resolve_target_exe
            resolved = resolve_target_exe("7-Zip")
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved, dummy_exe.resolve())


if __name__ == "__main__":
    unittest.main()



