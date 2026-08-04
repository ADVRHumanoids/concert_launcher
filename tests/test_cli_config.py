import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from concert_launcher.cli import default_config_path


class CliConfigTests(unittest.TestCase):
    def test_default_config_env_overrides_local_launcher_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local_config = root / "launcher.yaml"
            env_config = root / "host.yaml"
            local_config.write_text("context: {}\n")
            env_config.write_text("context: {}\n")

            with mock.patch.dict(
                os.environ,
                {"CONCERT_LAUNCHER_DEFAULT_CONFIG": str(env_config)},
            ):
                old_cwd = os.getcwd()
                try:
                    os.chdir(root)
                    self.assertEqual(default_config_path(), str(env_config))
                finally:
                    os.chdir(old_cwd)

    def test_default_config_uses_local_launcher_yaml_without_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local_config = root / "launcher.yaml"
            local_config.write_text("context: {}\n")

            with mock.patch.dict(os.environ, {}, clear=True):
                old_cwd = os.getcwd()
                try:
                    os.chdir(root)
                    self.assertEqual(default_config_path(), str(local_config))
                finally:
                    os.chdir(old_cwd)
