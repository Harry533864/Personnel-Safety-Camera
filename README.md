# Personnel Safety Camera

Vue + Flask edge camera platform for the Jetson deployment branch.

## Branches

- `jetson`: Jetson Orin Nano deployment.
- `baumer`: Baumer smart camera adaptation.

## Fresh Jetson Setup

Clone the Jetson branch:

```bash
git clone -b jetson https://github.com/Harry533864/Personnel-Safety-Camera.git
cd Personnel-Safety-Camera
```

Run the bootstrap script:

```bash
bash scripts/bootstrap_jetson.sh
```

If the device is missing common packages such as `python3-venv`, `npm`,
`v4l2-ctl`, or `gst-inspect-1.0`, run:

```bash
INSTALL_APT=1 bash scripts/bootstrap_jetson.sh
```

The bootstrap script creates a `.venv` with `--system-site-packages`, installs
Python and frontend dependencies, creates `.env` when missing, fixes executable
permissions, and verifies the core runtime imports.

## Run Manually

Start backend + MediaMTX once:

```bash
RUN_NOW=1 bash scripts/bootstrap_jetson.sh
```

Start backend + MediaMTX + Vite frontend once:

```bash
RUN_NOW=1 START_FRONTEND=1 bash scripts/bootstrap_jetson.sh
```

Default URLs:

```text
Backend: http://<jetson-ip>:5000/api/runtime/status
Stream:  http://<jetson-ip>:8889
Frontend dev server: http://<jetson-ip>:5173
```

## Install Boot Services

Install systemd services so the backend and MediaMTX start on power-up:

```bash
INSTALL_SYSTEMD=1 bash scripts/bootstrap_jetson.sh
```

Useful service commands:

```bash
systemctl status asv-mediamtx asv-backend
journalctl -u asv-backend -f
```

## Update An Existing Device

```bash
cd Personnel-Safety-Camera
git checkout jetson
git pull
bash scripts/bootstrap_jetson.sh
sudo systemctl restart asv-mediamtx asv-backend
```

## Factory Check

After setup:

```bash
bash scripts/factory_readiness_check.sh
```

This checks Super/25W mode, hardware encoder availability, camera 1080p60
support, and optional backend status.

## Notes

- Do not install generic `opencv-python` on Jetson; it can replace the Jetson
  OpenCV build that includes GStreamer/CUDA support.
- TensorRT `.engine` files are device/runtime specific. Regenerate the engine
  on the target Jetson when JetPack, TensorRT, or hardware changes:

```bash
bash scripts/build_tensorrt_engine.sh \
  inference/models/yolo11n_person.onnx \
  inference/models/yolo11n_person.engine
```
