"""WebRTC video tracks backed by the ROS camera interface."""

from __future__ import annotations

import asyncio
import time

import numpy as np
from aiortc import VideoStreamTrack
from aiortc.mediastreams import VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
from av import VideoFrame
from teleop_gateway_common.ros_interface import ROSInterfaceBase


class ROSVideoTrack(VideoStreamTrack):
    """Streams frames from `ros.get_camera_frame(topic)` at `fps`."""

    def __init__(self, ros: ROSInterfaceBase, topic: str, fps: float = 15.0) -> None:
        super().__init__()
        self._ros = ros
        self._topic = topic
        self._period = 1.0 / fps
        self._start = time.monotonic()
        self._frame_index = 0

    async def recv(self) -> VideoFrame:
        if self.readyState != "live":
            raise RuntimeError("track is not live")

        target = self._start + self._frame_index * self._period
        wait = target - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

        sample = self._ros.get_camera_frame(self._topic)
        if sample is None:
            data = np.zeros((480, 640, 3), dtype=np.uint8)
        else:
            data = sample.data

        frame = VideoFrame.from_ndarray(data, format="bgr24")
        elapsed = time.monotonic() - self._start
        frame.pts = int(elapsed * VIDEO_CLOCK_RATE)
        frame.time_base = VIDEO_TIME_BASE
        self._frame_index += 1
        return frame
