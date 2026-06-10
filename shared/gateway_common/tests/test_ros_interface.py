from teleop_gateway_common.ros_interface import MockROSInterface


def test_mock_jointstates():
    ros = MockROSInterface(num_joints=6)
    sample = ros.get_jointstates()
    assert len(sample.positions) == 6
    assert all(isinstance(p, float) for p in sample.positions)


def test_mock_camera_frame_shape():
    ros = MockROSInterface(frame_size=(64, 96))
    frame = ros.get_camera_frame("gripper_cam")
    assert frame.data.shape == (64, 96, 3)
    assert frame.data.dtype.name == "uint8"


def test_mock_camera_frames_distinct_per_topic():
    ros = MockROSInterface(frame_size=(32, 32))
    gripper = ros.get_camera_frame("gripper_cam")
    global_cam = ros.get_camera_frame("global_cam")
    assert not (gripper.data == global_cam.data).all()


async def test_mock_injected_command_updates_state():
    ros = MockROSInterface()
    assert ros.get_command_state()["enabled"] is False
    await ros.publish_injected_command({"enabled": True, "mode": "TRACKING"})
    state = ros.get_command_state()
    assert state["enabled"] is True
    assert state["mode"] == "TRACKING"
    assert ros.injected_commands == [{"enabled": True, "mode": "TRACKING"}]
