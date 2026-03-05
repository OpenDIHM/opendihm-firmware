# opendihm-firmware
OpenDIHM Firmware is the core application logic for the open digital in-line holographical microscope. It runs on a Raspberry Pi Zero 2 W, and
shares the image stream with the opendihm-mobile-ios application via WiFi. The WiFi connection is established using a Bluetooth connection with
the mobile device. The mobile device then shares the WiFi connection with the Raspberry Pi Zero 2 W. Furthermore, the firmware also provides an
API for the mobile device to control the microscope. The API is accessible via HTTP and is protected by a simple authentication mechanism.

## Features
- Video stream over RTSP
- HTTP API for microscope control
   - Laser control (on/off via relay)
   - Camera control (zoom (3-levels), v4l2 controls)
- Bluetooth connection for WiFi sharing
- Logrotate for log management
- Systemd service for the application
- Configurable via YAML file
- Configuration YAML can be updated via HTTP API

## Connection Flow
- The Raspberry Pi boots up and broadcasts a Bluetooth Low Energy (BLE) signal.
- You open an app on your iOS device, which connects to the Pi via Bluetooth.
- You type your current Wi-Fi network's SSID and password into the iOS app.
- The app securely sends those credentials over Bluetooth to the Pi.
- A process on the Pi receives the credentials, applies it to NetworkManager, and connects to the Wi-Fi.
- The video stream begins over the new local Wi-Fi connection.

## Platform
- Raspberry Pi Zero 2 W
- Raspberry Pi Camera Module 2
- Raspbian OS (systemd)
- Python 3.11 (venv)

## Project Structure
```
opendihm-firmware/
├── config/
│   ├── config.yaml
│   └── config.yaml.example
├── src/
│   ├── main.py
│   └── .../
│   └── utils/
│       └── utils.py
├── tests/
│   └── test_main.py
└── README.md
```