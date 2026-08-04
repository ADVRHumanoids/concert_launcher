from pathlib import Path
import unittest


class InspectionWatchTests(unittest.TestCase):
    def test_tail_follow_command_uses_fast_gnu_tail_with_fallback(self):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "concert_launcher"
            / "inspection.py"
        ).read_text()

        self.assertIn("tail --help", source)
        self.assertIn("tail -f -s 0.1 -n {lines} {path}", source)
        self.assertIn("tail -f -n {lines} {path}", source)
