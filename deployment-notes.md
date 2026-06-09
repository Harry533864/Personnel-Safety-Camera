# 打包、部署与常见注意事项

> 适用分支：`baumer`  
> 当前默认目标机器：`192.168.18.172`（Windows 前端）  
> 当前默认相机后端地址：`192.168.1.173:5000`

## 1. 打包方式（Windows 安装包）

### 环境准备
- Node.js 可用（建议 16+，当前工程依赖 Vite + Vue3）
- Windows PowerShell
- 当前分支已切到 `baumer`

### 一键构建
在项目根目录执行：

```powershell
npm install
npm run package:win
```

执行流程：
- 运行 `scripts/build_frontend_installer.ps1`
- 临时把路由模式改为 `hash`
- `npm run build -- --base ./` 生成前端产物
- 使用 IExpress 打包：
  - `release\ASV-Safety-Camera-Setup.exe`
- 安装包会内置：
  - 前端静态文件（`dist`）
  - 本地启动脚本（启动到 `127.0.0.1:51730`）
  - 自动生成桌面与开始菜单快捷方式
  - `ASV Safety Camera` 图标

注意：
- 打包会清理 `release\installer-source`，仓库中已忽略该目录（`.gitignore`）
- 图标来源于 `src/assets/asv-logo.png`，图标脚本会先转换并写入前端资源再打包
- 每次打包前端必须是可编译状态，否则会直接失败

## 2. 配置文件（重要）

打包前检查以下配置是否与当前部署一致：

- `.env.production`
  - `VITE_FLASK_BACKEND_URL=http://192.168.1.173:5000`
  - `VITE_VIDEO_STREAM_URL=http://192.168.1.173:8889`
  - `VITE_FRONTEND_HOST=192.168.1.11`
  - `VITE_CAMERA_CANDIDATE_HOSTS=192.168.1.173,192.168.18.173,10.10.10.2`
  - `VITE_CAMERA_SCAN_SUBNETS=192.168.1,192.168.18,10.10.10`
- `.env` 目前同步了上述值，主要用于本地开发校准；前端发布使用 `.env.production`

如果目标机与摄像机网段变化，请先改 `.env.production` 后再打包。

## 3. 前端安装到 `192.168.18.172` 的动作

1. 把 `release\ASV-Safety-Camera-Setup.exe` 复制到 `192.168.18.172`
2. 以正常用户运行安装（首次安装会创建以下目录）：
   - `%LOCALAPPDATA%\ASV Safety Camera`
3. 安装完成后双击桌面图标启动：
   - 后端请求会走 `127.0.0.1:51730` 的本地预览页
   - 页面里的后端/流地址会按环境默认值自动尝试（`192.168.1.173` 优先）
4. 若首次打不开或白屏：
   - 检查 `192.168.18.172` 能访问 `127.0.0.1:51730`
   - 检查本地防火墙是否放行应用出站访问

## 4. 相机与网段注意项（从“10.10.10.2”到“192.168.18.173”）

- 当前后端候选主机为：
  - `192.168.1.173`
  - `192.168.18.173`
  - `10.10.10.2`
- 后台扫描子网为：
  - `192.168.1.0/24`
  - `192.168.18.0/24`
  - `10.10.10.0/24`

快速校准脚本：
- Windows 侧：`scripts/configure_windows_eth_192_168_18_172.ps1`
- 相机侧（baumer）：`scripts/configure_camera_lan_alias_192_168_18_173.sh`

脚本行为：
- Windows 脚本会自动给相机网卡配置本机 IP（默认 `192.168.18.172`）并写入到 `192.168.18.173` 的静态路由
- 相机脚本会把 `eth0` 同时带上 `10.10.10.2/24` 与 `192.168.18.173/24`，用于双网段回连与扫描

## 5. 后端服务自启动（baumer）

核心服务名：
- `asv-mediamtx.service`
- `asv-backend.service`

安装脚本：
- `scripts/install_baumer_systemd_services.sh`

安装后可查命令（在相机端）：
- `systemctl status asv-mediamtx`
- `systemctl status asv-backend`
- `systemctl is-enabled asv-mediamtx.service asv-backend.service`

默认环境变量：
- 后端端口 `5000`
- `CAMERA_WIDTH=1920`
- `CAMERA_HEIGHT=1080`
- `CAMERA_FPS=60`（可按需改）
- `CAM_AUTO_START=1`

服务默认日志：
- `$REPO_DIR/logs/mediamtx.{out,err}.log`
- `$REPO_DIR/logs/flask.{out,err}.log`

说明：
- baumer 分支已做过服务开机即自启配置，重启后应自动恢复接口和 RTSP/WEBRTC 流服务

## 6. 模型与检测配置重要信息

- 目标检测模型默认展示名：`ASV_person_FP16`
- 对应目录：
  - `inference/models/ASV_person_FP16/ASV_person_FP16.engine`
  - `inference/models/ASV_person_FP16/ASV_person_FP16.txt`
- 模型列表是从文件夹/模型管理联合加载的，不建议手动改数据库配置文件中的“显示名”与文件夹不一致
- 若要切换检测模型，优先在“模型管理”上传/启用后，再到检测设置里选择

## 7. 一次性自检清单（部署后先跑）

- 后端健康：`http://192.168.1.173:5000`
- RTSP/流：`http://192.168.1.173:8889`
- 前端：在本机执行后打开 `127.0.0.1:51730`
- 端口连通：5000 与 8889 在部署机与前端机间可互达
- 旧配置兼容：若历史安装留下 localStorage 旧值，先手动确认前端连接配置或清理浏览器缓存

## 8. 常见问题（故障优先级）

1. 安装后打不开
- 常见于本地 51730 被占用/防火墙拦截
- 先确认安装目录快捷方式存在（桌面/开始菜单），目标是 `start-asv-camera.cmd`

2. 页面能开，但看不到画面
- 优先确认候选 IP 与当前扫描网段有命中
- 检查相机进程服务是否还活着：`systemctl status asv-backend`
- 确认前端环境变量中的 `VITE_VIDEO_STREAM_URL` 是否指向真实机柜端口

3. 检测结果没出现
- 先确认“模型管理”里有 `ASV_person_FP16`，且检测设置里选中该模型
- 观察后端日志看 model 是否加载成功
- 若模型未完全加载，前端仍会显示原始画面

4. 频率看起来偏慢、卡顿
- 优先降低推送分辨率与开启自动调参，不要同时开过高 fps、超大分辨率与高吞吐推理
- 首次连接后先看页面上的预览帧率再调参数

## 9. Git 记录

- 本文档是对“打包 + 直接部署 + 网络扫描 + 自启动 + 模型一致性”核心流程的固化说明
- 变更建议在 `baumer` 分支提交，并与远端 `origin/baumer` 同步
