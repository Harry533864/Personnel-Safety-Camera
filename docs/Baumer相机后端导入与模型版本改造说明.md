# Baumer 相机后端导入与模型版本改造说明

本文档用于把当前后端导入 Baumer VAX/AX 智能相机，并把原 Jetson Orin Nano Super 版本与 Baumer Xavier NX 版本的差异拆开管理。

## 1. 当前目标

- 相机 LAN 固定地址：`10.10.10.2/24`
- PC 直连口地址：`10.10.10.1/24`
- SSH 入口：`ssh baumer@10.10.10.2`
- 后端服务端口：`5000`
- 采集方式：Baumer `neoAPI`
- 默认模型版本：FP16 TensorRT engine
- 可选模型版本：INT8 TensorRT engine，必须经过真实场景校准和精度回归

## 2. Orin 版本与 Baumer 版本的后端差异

| 项目 | Orin Nano Super 版本 | Baumer VAX/Xavier NX 版本 |
|---|---|---|
| 默认用户 | `jetson` | `baumer` |
| 默认目录 | `/home/jetson/code/Cam_flaskvue` | `/home/baumer/Cam_flaskvue` |
| 相机采集 | `/dev/video0` + V4L2/GStreamer | `neoAPI` 直接采集内置工业相机 |
| 采集环境变量 | `CAM_CAPTURE_BACKEND=v4l2` | `CAM_CAPTURE_BACKEND=baumer_neoapi` |
| 相机设备等待 | 等 `/dev/video0` | 不等 `/dev/video0` |
| Python / TensorRT | 原项目按 Orin 环境，Python 3.10 / TensorRT 10.x | 当前相机是 Python 3.8 / TensorRT 8.5.2 / CUDA 11.4 |
| TensorRT engine | 在 Orin 设备生成 | 必须在 Baumer 相机本机重新生成 |
| 根分区 | 普通可写 | 默认只读，改系统服务/网络/依赖前要进入 writable `/` |
| 稳定运行 | systemd | systemd，安装后恢复只读模式 |

## 3. 已加入的 Baumer 后端修改

新增采集适配器：

```text
app/Cam/capture_backends.py
```

新增 `BaumerNeoApiCapture`，接口兼容 OpenCV `VideoCapture` 的核心方法：

- `open()`
- `isOpened()`
- `read()`
- `release()`

`CamManager` 已支持通过环境变量切换：

```bash
CAM_CAPTURE_BACKEND=baumer_neoapi
```

原 USB/V4L2 版本仍保留：

```bash
CAM_CAPTURE_BACKEND=v4l2
```

## 4. 导入 Baumer 相机的推荐步骤

### 4.1 确认 LAN 入口

PC 直连口应为：

```text
10.10.10.1/24
```

相机应能 SSH：

```bash
ssh baumer@10.10.10.2
```

密码：

```text
baumer
```

### 4.2 复制后端代码

推荐目录：

```text
/home/baumer/Cam_flaskvue
```

可以用 `git clone`、`scp` 或 `git archive | ssh tar` 的方式导入。不要把本机 `.venv`、`node_modules`、`logs` 当作交付内容上传。

### 4.3 进入 writable `/` 模式

Baumer 相机默认根分区只读。安装系统服务、写 `/etc/systemd/system`、安装依赖前，需要执行：

```bash
sudo /opt/baumer-vax/ro/configure-rw-boot.sh
sudo reboot
```

重启后再 SSH 到：

```bash
ssh baumer@10.10.10.2
```

### 4.4 安装 Baumer 后端服务

在相机上进入仓库目录后运行：

```bash
cd /home/baumer/Cam_flaskvue
sudo bash scripts/install_baumer_systemd_services.sh
```

该脚本会安装：

- `asv-mediamtx.service`
- `asv-backend.service`

并写入 Baumer 专用环境变量：

```text
CAM_CAPTURE_BACKEND=baumer_neoapi
CAMERA_WIDTH=1920
CAMERA_HEIGHT=1080
CAMERA_FPS=60
BAUMER_PIXEL_FORMAT=BGR8
```

### 4.5 验证服务

```bash
systemctl status asv-mediamtx asv-backend
journalctl -u asv-backend -f
```

PC 侧验证：

```bash
curl http://10.10.10.2:5000/api/runtime/status
```

### 4.6 恢复只读生产模式

厂家脚本的非 `permanent` 模式会让下一次正常启动恢复只读根分区。服务安装完成后建议重启验证：

```bash
sudo reboot
```

重启后确认：

```bash
ssh baumer@10.10.10.2
findmnt -no TARGET,OPTIONS /
```

如果 `/` 包含 `ro`，说明只读保护已恢复。

## 5. FP16 与 INT8 模型版本差异

### 5.1 FP16 默认版本

用途：

- 默认交付
- 精度风险低
- 对 Xavier NX 有明显加速
- 不需要校准数据

模型目录建议：

```text
inference/models/Asva_person_v0518_fp16/
  Asva_person_v0518_fp16.engine
  Asva_person_v0518_fp16.txt
```

构建脚本：

```bash
bash scripts/build_baumer_fp16_engine.sh
```

生成后把 `app/AIConfig.yaml` 的模型名设置为：

```yaml
model:
  model_name: Asva_person_v0518_fp16
model_names:
  - Asva_person_v0518_fp16
```

### 5.2 INT8 可选版本

用途：

- 追求更高推理帧率
- 追求更低功耗和发热
- 需要完整校准和误检/漏检回归

风险：

- 人员安全检测不能无校准直接上 INT8
- 校准场景不足时，漏检率可能上升
- 必须拿真实部署画面做测试

模型目录建议：

```text
inference/models/Asva_person_v0518_int8/
  Asva_person_v0518_int8.engine
  Asva_person_v0518_int8.txt
```

先采集校准帧：

```bash
python3 scripts/collect_baumer_calibration_frames.py \
  --output /home/baumer/calibration_frames \
  --count 500 \
  --width 1920 \
  --height 1080
```

准备好 TensorRT calibration cache 后，再构建 INT8：

```bash
CALIB_CACHE=/path/to/baumer_yolo11n_person_int8.cache \
  bash scripts/build_baumer_int8_engine.sh
```

生成后把 `app/AIConfig.yaml` 的模型名设置为：

```yaml
model:
  model_name: Asva_person_v0518_int8
model_names:
  - Asva_person_v0518_fp16
  - Asva_person_v0518_int8
```

## 6. 当前还需要注意的点

1. 这台相机目前没有发现 `trtexec`，但有 TensorRT runtime 和 Python binding。若要在相机上直接构建 engine，需要安装/启用 TensorRT 构建工具，或补 Python TensorRT builder。
2. Baumer 相机是 Python 3.8 环境，原 Orin 文档里的 Python 3.10 wheel 不能直接照搬。
3. `.engine` 不能跨设备复用。Orin Nano 上生成的 engine 不应直接放到 Xavier NX 上跑。
4. 系统配置写入 `/etc` 前必须进入 writable `/` 模式；运行期数据和日志优先放 `/home`。
5. 安全检测默认建议使用 FP16。INT8 只能在校准和回归通过后作为交付选项。
