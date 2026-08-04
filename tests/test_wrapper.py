import os
from pathlib import Path
import subprocess
import tempfile
import time
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

    def test_output_file_receives_first_line_before_process_exits(self):
        name = "wrapper_test_{}".format(uuid.uuid4().hex[:10])
        output_file = Path("/tmp/{}.stdout".format(name))
        wrapper = (
            Path(__file__).parents[1]
            / "src"
            / "concert_launcher"
            / "resources"
            / "concert_launcher_wrapper.bash"
        )
        command = "python3 -c 'import time; print(\"first-line\"); time.sleep(1)'"

        with tempfile.TemporaryDirectory() as directory:
            fake_ts = Path(directory) / "ts"
            fake_ts.write_text("#!/bin/sh\ncat\n")
            fake_ts.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = "{}:{}".format(directory, env["PATH"])
            process = subprocess.Popen(
                [str(wrapper), name, command],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 0.7
                while time.monotonic() < deadline:
                    if output_file.exists() and "first-line" in output_file.read_text():
                        break
                    time.sleep(0.05)
                else:
                    self.fail("wrapper did not write the first line before exit")

                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, stderr or stdout)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)
                output_file.unlink(missing_ok=True)
                Path("/tmp/{}.STARTING".format(name)).unlink(missing_ok=True)
                Path("/tmp/{}.KILLING".format(name)).unlink(missing_ok=True)
