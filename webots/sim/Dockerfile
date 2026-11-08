FROM cyberbotics/webots:R2025a-ubuntu22.04@sha256:f0023e30daf38b172e4e6ad24ed345909bcd9551df34d63d824e121a7cebf099

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-pip \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir paho-mqtt==1.6.1
