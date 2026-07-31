import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid


class WrapperTests(unittest.TestCase):
    def test_timestamp_pipeline_preserves_command_exit_status(self):
        name = "wrapper_test_{}".format(uuid.uuid4().hex[:10])
        output_file = Path("/tmp/{}.stdout".format(name))
        wrapper = (
            Path(__file__).parents[1]
            / "src"
            / "concert_launcher"
            / "resources"
            / "concert_launcher_wrapper.bash"
        )

        with tempfile.TemporaryDirectory() as directory:
            fake_ts = Path(directory) / "ts"
            fake_ts.write_text("#!/bin/sh\ncat\n")
            fake_ts.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = "{}:{}".format(directory, env["PATH"])
            try:
                result = subprocess.run(
                    [str(wrapper), name, "echo wrapper-output; exit 17"],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(result.returncode, 17, result.stderr)
                self.assertIn("wrapper-output", output_file.read_text())
                self.assertIn("process exited with code 17", output_file.read_text())
            finally:
                output_file.unlink(missing_ok=True)
                Path("/tmp/{}.STARTING".format(name)).unlink(missing_ok=True)
                Path("/tmp/{}.KILLING".format(name)).unlink(missing_ok=True)
