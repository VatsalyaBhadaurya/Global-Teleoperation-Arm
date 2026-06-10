# Runs on the leader/operator-side machine, alongside leader.py. Build
# context must be the repo root, e.g.:
#   docker build -f services/leader-gateway/Dockerfile -t teleop-leader-gateway .
#
# To use the real ROS 2 backend instead of the mock, install rclpy and the
# robot's ROS 2 packages into this image (or run the gateway directly inside
# the robot's existing ROS 2 environment instead of this container) and set
# TELEOP_ROS_BACKEND=rclpy.
FROM python:3.11-slim

WORKDIR /app

COPY shared/protocol shared/protocol
COPY shared/gateway_common shared/gateway_common
COPY services/leader-gateway services/leader-gateway

RUN pip install --no-cache-dir \
    ./shared/protocol \
    ./shared/gateway_common \
    ./services/leader-gateway

ENV TELEOP_ROS_BACKEND=mock

CMD ["python", "-m", "leader_gateway.main"]
