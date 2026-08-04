import unittest

from concert_launcher.errors import ConfigurationError
from concert_launcher.process import ConfigParser


CONFIG = {
    "context": {"session": "robot", "params": {"robot": "kyon"}},
    "controller": {
        "cmd": "controller --robot {robot}",
        "ready_check": "check-controller --robot {robot}",
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

    def test_ready_check_uses_the_same_resolved_parameters(self):
        config = ConfigParser("controller", CONFIG)
        config.parse_cmd(user_variants=["position"])
        self.assertEqual(
            config.ready_check,
            "check-controller --robot position_robot",
        )

    def test_docker_command_and_readiness_check_are_shell_quoted(self):
        config_data = {
            "context": {"session": "robot"},
            "lidar": {
                "cmd": (
                    "ros2 run hesai_ros_driver hesai_ros_driver_node "
                    "--ros-args -p config_path:=/tmp/lidar.yaml"
                ),
                "ready_check": "timeout 5 ros2 topic echo /lidar_points --once",
                "docker": "kyon-noble-ros2-dev-1",
            },
        }

        config = ConfigParser("lidar", config_data)
        self.assertEqual(
            config.parse_cmd(),
            "docker exec -it kyon-noble-ros2-dev-1 bash -ic "
            "'ros2 run hesai_ros_driver hesai_ros_driver_node --ros-args -p "
            "config_path:=/tmp/lidar.yaml'",
        )
        self.assertEqual(
            config.ready_check,
            "docker exec -i kyon-noble-ros2-dev-1 bash -ic "
            "'timeout 5 ros2 topic echo /lidar_points --once'",
        )

    def test_docker_quoting_preserves_shell_syntax_in_the_inner_command(self):
        config_data = {
            "context": {"session": "robot"},
            "example": {"cmd": 'echo "$HOME"', "docker": "container"},
        }

        command = ConfigParser("example", config_data).parse_cmd()
        self.assertEqual(
            command,
            "docker exec -it container bash -ic 'echo \"$HOME\"'",
        )

    def test_rejects_multiple_choices_from_same_variant_group(self):
        config = ConfigParser("controller", CONFIG)
        with self.assertRaises(ConfigurationError):
            config.parse_cmd(user_variants=["position", "torque"])

    def test_rejects_unknown_process(self):
        with self.assertRaises(ConfigurationError):
            ConfigParser("missing", CONFIG)
