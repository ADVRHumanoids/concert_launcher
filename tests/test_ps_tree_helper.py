from pathlib import Path
import subprocess
import sys
import time
import unittest


class PsTreeHelperTests(unittest.TestCase):
    def test_helper_prints_root_process_for_shallow_tree(self):
        helper = (
            Path(__file__).parents[1]
            / "src"
            / "concert_launcher"
            / "resources"
            / "concert_launcher_print_ps_tree.py"
        )
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
        try:
            time.sleep(0.1)
            result = subprocess.run(
                [sys.executable, str(helper), str(process.pid)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PID: {}".format(process.pid), result.stdout)
            self.assertIn("python", result.stdout.lower())
        finally:
            process.terminate()
            process.wait(timeout=5)
