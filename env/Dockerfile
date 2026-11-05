# Pinned ROS 2 Jazzy base (rclpy 7.1.12, rmw_fastrtps_cpp 8.4.4, Fast DDS 2.14.7; checked 2026-10-21).
# SUBNET discovery: agents run one container each on a user-defined bridge (infra/probe_x3.sh).
FROM ros:jazzy@sha256:103b6c417973394659af6804d4917cd489b91e5ed22eb7bef263025a3bed2410
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
