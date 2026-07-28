import unittest

from concert_launcher.errors import ConfigurationError
from concert_launcher.process import ConfigParser


CONFIG = {
    "context": {"session": "robot", "params": {"robot": "kyon"}},
    "controller": {
        "cmd": "controller --robot {robot}",
        "variants": {
            "debug": {"cmd": "{cmd} --verbose"},
            "mode": [
                {"position": {"params": {"robot": "position_robot"}}},
                {"torque": {"cmd": "{cmd} --torque"}},
            ],
        },
    },
}


class ProcessConfigTests(unittest.TestCase):
    def test_renders_parameters_and_variants(self):
        config = ConfigParser("controller", CONFIG)
        command = config.parse_cmd(
            user_params={"robot": "centauro"},
            user_variants=["debug", "torque"],
        )
        self.assertEqual(
            command,
            "controller --robot centauro --verbose --torque",
        )

    def test_rejects_multiple_choices_from_same_variant_group(self):
        config = ConfigParser("controller", CONFIG)
        with self.assertRaises(ConfigurationError):
            config.parse_cmd(user_variants=["position", "torque"])

    def test_rejects_unknown_process(self):
        with self.assertRaises(ConfigurationError):
            ConfigParser("missing", CONFIG)
