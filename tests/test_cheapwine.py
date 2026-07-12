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
            
            # Try to add something that is not auto-detected (should fail)
            result_fail = self.runner.invoke(cli, ["add", "unknownapp"])
            self.assertNotEqual(result_fail.exit_code, 0)
            self.assertIn("Executable path is required", result_fail.output)

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
        desktop_file_path = desktop_dir / f"cheapwine-{safe_proj_name}-{safe_app_name}.desktop"
        
        self.assertTrue(desktop_file_path.exists())
        
        # Test unexporting
        result_unexport = self.runner.invoke(cli, ["unexport", "myapp"])
        self.assertEqual(result_unexport.exit_code, 0)
        self.assertIn("Unexported", result_unexport.output)
        self.assertFalse(desktop_file_path.exists())

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

    def test_env_output(self):
        """Test cheapwine env exports match expected prefix paths."""
        self.runner.invoke(cli, ["init"])
        result = self.runner.invoke(cli, ["env"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("export WINEPREFIX=", result.output)
        self.assertIn("export WINEARCH=win64", result.output)

if __name__ == "__main__":
    unittest.main()
