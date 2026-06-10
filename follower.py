import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import String
import json
import time
import math
from so101_ros2.lerobot.so101 import SO101

# Order of joints in the `leader_jointstates` array sent over the remote
# teleop data channel (see teleop_protocol.messages.TeleopLeaderState). Must
# match leader.py's `motor_key_to_joint_name` order.
JOINT_ORDER = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

# Robot modes (from /teleop_remote_command) in which the arm should hold its
# current position rather than track a new target.
HOLD_MODES = {"ESTOPPED", "FROZEN", "IDLE", "HOMING"}

class LeRobotJointStateSubscriber(Node):

    def __init__(self):
        super().__init__('lerobot_subscriber')

        # Declare ROS Parameters
        self.declare_parameter('robot_name', "so101_follower")
        self.declare_parameter('port', "/dev/ttyACM0")
        self.declare_parameter('recalibrate', False)

        # Get parameter values
        self.robot_name = self.get_parameter('robot_name').value
        self.port = self.get_parameter('port').value
        self.recalibrate = self.get_parameter('recalibrate').value

        self.subscription = self.create_subscription(
            JointState,
            '/leader_joint_states',
            self.joint_states_callback,
            10)
        self.subscription

        # Validated remote-operator commands injected by the follower
        # gateway (services/follower-gateway/follower_gateway/ros_backend.py).
        # JSON dict with keys: enabled, clutched, mode, leader_jointstates,
        # gripper, gripper_command. Folded into the same control path as the
        # local /leader_joint_states subscription, gated on
        # enabled and not clutched, so the arm only tracks the remote
        # operator while the session is armed.
        self.remote_command_subscription = self.create_subscription(
            String,
            '/teleop_remote_command',
            self.remote_command_callback,
            10)
        self.remote_command_subscription

        self.follower_publisher = self.create_publisher(JointState, '/follower_joint_states', 10) # prevent unused variable warning

        # Latest state folded in from /teleop_remote_command.
        self.remote_enabled = False
        self.remote_clutched = False
        self.remote_mode = "IDLE"

        self.get_logger().info('LeRobotController node has been started.')

        # Initialize lerobot arm
        self.robot = self.init_lerobot_arm()


    def init_lerobot_arm(self):
        robot = SO101(port=self.port, name=self.robot_name, recalibrate=self.recalibrate)
        try:
            self.get_logger().info("Connecting to lerobot arm...")
            robot.connect()
            self.get_logger().info("LeRobot arm connected.")
            return robot
        except Exception as e:
            self.get_logger().error(f"Failed to connect to lerobot arm: {e}")
            rclpy.shutdown() # Shutdown ROS if robot connection fails
            return None

    def joint_states_callback(self, msg: JointState):
        if self.robot is None:
            self.get_logger().warn("LeRobot arm not initialized. Skipping joint state update.")
            return

        joint_states = {} # This will be populated to be a dict of joint_name: joint_angle_deg
        for joint_name, joint_value in zip(msg.name, msg.position):
            joint_states[joint_name] = math.degrees(joint_value)
            #joint_states[joint_name] = joint_value / (math.pi) * 180

        self._drive_and_report(joint_states)

    def remote_command_callback(self, msg: String):
        if self.robot is None:
            self.get_logger().warn("LeRobot arm not initialized. Skipping remote command.")
            return

        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError as e:
            self.get_logger().error(f"Invalid /teleop_remote_command payload: {e}")
            return

        if "enabled" in command:
            self.remote_enabled = bool(command["enabled"])
        if "clutched" in command:
            self.remote_clutched = bool(command["clutched"])
        if command.get("mode"):
            self.remote_mode = command["mode"]

        if not self.remote_enabled or self.remote_clutched or self.remote_mode in HOLD_MODES:
            return

        leader_jointstates = command.get("leader_jointstates")
        if not leader_jointstates:
            return

        joint_states = {
            name: math.degrees(value)
            for name, value in zip(JOINT_ORDER, leader_jointstates)
        }
        self._drive_and_report(joint_states)

    def _drive_and_report(self, joint_states: dict):
        try:
            self.get_logger().info(f"Sent action: {joint_states}") # Too verbose for constant updates
            self.robot._bus.sync_write("Goal_Position", joint_states)
            #follower_positions = self.robot.get_positions()
            device_state = self.robot.get_device_state()
            follower_msg = JointState()
            follower_msg.header.stamp = self.get_clock().now().to_msg()
            follower_msg.name = list(device_state.keys())
            follower_msg.position = [math.radians(v) for v in device_state.values()]
            self.follower_publisher.publish(follower_msg)
        except Exception as e:
            self.get_logger().error(f"Error sending action to lerobot arm: {e}")

def main(args=None):
    rclpy.init(args=args)
    lerobot_subscriber = LeRobotJointStateSubscriber()
    rclpy.spin(lerobot_subscriber)

    # Ensure lerobot disconnects when ROS node shuts down
    if lerobot_subscriber.robot is not None:
        lerobot_subscriber.get_logger().info("Disconnecting lerobot arm...")
        lerobot_subscriber.robot.disconnect() # [cite: 2]
        lerobot_subscriber.get_logger().info("LeRobot arm disconnected.")

    lerobot_subscriber.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
