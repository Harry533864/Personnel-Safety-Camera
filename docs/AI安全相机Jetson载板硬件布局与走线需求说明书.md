# AI 人员安全相机 Jetson 载板硬件布局与走线需求说明书

文档版本：V1.0  
编写日期：2026-06-03  
适用对象：AI 人员安全相机产品化载板、硬件外包设计、样机评审、量产导入  
目标平台：NVIDIA Jetson Orin Nano / Orin Nano Super 软件平台兼容方案  

---

## 1. 文档目的

本文档用于向硬件设计方明确 AI 人员安全相机产品化载板的最小功能配置、布局原则、走线重点、调试接口保留方式、量产刷机要求和硬件验收标准。

本产品不是通用开发板，而是面向客户现场部署的边缘 AI 安全相机。硬件设计目标是：

1. 客户日常使用接口尽量简单。
2. 工厂、售后、救砖、刷机能力必须完整保留。
3. 满足 1080p 视频采集、边缘 AI 推理、LAN 前端管理、GPIO/IO 联动报警、离线时间记录和本地存储。
4. 兼容当前 USB 摄像头方案，并预留后续 CSI 摄像头升级空间。
5. 支持 NVMe 作为系统盘或主要数据盘，满足量产和长期运行可靠性要求。

---

## 2. 产品基本假设

| 项目 | 当前要求 | 说明 |
| --- | --- | --- |
| 计算核心 | Jetson Orin Nano / Orin Nano Super 软件兼容 | 以当前软件部署环境为基准 |
| 主电源 | 19V 输入优先 | 可评估 9-36V 宽压工业输入，但第一版建议保持 19V 方案 |
| 系统存储 | NVMe M.2 Key-M | 建议作为量产默认存储，优于 microSD |
| 当前相机 | 内置 USB 摄像头 | 客户不需要外露 USB 摄像头口 |
| 未来相机 | 预留 1 路 CSI 底座 | 用于后续 CSI 摄像头版本 |
| 管理通讯 | LAN 口 | 前端管理、视频预览、参数配置、维护调试 |
| 刷机救砖 | USB-C + Recovery | 必须保留，可隐藏，不建议删除 |
| 离线时间 | RTC 电池 | 断电后保持时间，保证离线报警记录可信 |
| 散热 | 4pin 5V PWM 风扇 | 建议保留 PWM 和 TACH 转速反馈 |
| IO 联动 | 40pin 或等效工业 IO | 建议转成隔离输入/输出和端子，不建议裸 GPIO 直连外设 |

---

## 3. 接口保留策略

### 3.1 客户侧建议外露接口

| 接口 | 是否外露 | 用途 | 设计建议 |
| --- | --- | --- | --- |
| 电源输入 | 必须外露 | 整机供电 | 19V DC 输入，带防反接、过压、浪涌和保险保护 |
| LAN | 必须外露 | 前端管理、视频流、参数配置 | RJ45 靠板边，保留 ESD/浪涌保护 |
| 报警 IO 端子 | 建议外露 | 声光报警器、PLC、继电器、干接点 | 使用可插拔端子，做隔离和保护 |
| 状态灯 | 建议外露 | 电源、运行、网络、报警、故障 | 不影响密封和结构强度 |

### 3.2 工厂/售后隐藏维护接口

| 接口 | 是否保留 | 是否客户可见 | 用途 | 特别要求 |
| --- | --- | --- | --- | --- |
| USB-C Recovery | 必须保留 | 可隐藏 | 刷机、救砖、量产烧录 | 外壳打开后必须能接线 |
| Recovery / Reset / Power / GND | 必须保留 | 可隐藏 | 进入强制恢复、复位、电源控制 | 建议做测试点或小排针 |
| Debug UART | 必须保留 | 隐藏 | 无 LAN/无系统时诊断启动日志 | 建议 3pin/4pin 测试点 |
| 关键电源测试点 | 必须保留 | 隐藏 | 工厂测试和维修 | 19V、5V、3.3V、RTC、风扇电源等 |
| USB 调试口 | 可选 | 隐藏 | 工程维护 | 若空间允许，可保留一个内部维护 USB |

### 3.3 板内接口

| 接口 | 是否必须 | 用途 | 说明 |
| --- | --- | --- | --- |
| 内置 USB 摄像头接口 | 必须 | 当前摄像头接入 | 建议使用锁扣线束或板对线连接器 |
| CSI FPC 底座 | 建议必须 | 后续 CSI 摄像头版本 | 即使第一版不用，也建议按规范预留 |
| NVMe M.2 Key-M | 必须 | 系统盘/数据盘/模型/日志 | 建议支持 2280，条件允许兼容 2242/2260 |
| RTC 电池座 | 必须 | 离线时间保持 | 远离高温区，方便更换 |
| 4pin 风扇座 | 必须 | 散热 | 5V / GND / PWM / TACH |

---

## 4. 总体布局原则

### 4.1 推荐分区

| 区域 | 推荐位置 | 布局原则 |
| --- | --- | --- |
| Jetson 模组区 | 板中心或靠近散热核心位置 | 上方预留散热器高度，周围保留装配和返修空间 |
| 电源区 | 靠近电源输入 | 大电流路径短、粗，远离 CSI/USB/LAN 高速信号 |
| LAN 区 | 靠板边 | RJ45、磁性器件、ESD/浪涌保护集中放置 |
| USB-C 维护区 | 靠板边或可打开维护位置 | 必须能接线进入 Recovery |
| 内置 USB 相机区 | 靠近相机结构位置 | 线束短，避免跨越电源和风扇 |
| CSI 区 | 靠近未来相机位置 | FPC 短、直、少换层，预留相机电源和控制线 |
| NVMe 区 | 远离高温和大电流开关节点 | 保留固定柱、散热贴、拆装空间 |
| IO 端子区 | 靠板边 | 便于客户接线，隔离电路靠近端子 |
| RTC 电池区 | 边缘可维护位置 | 远离散热器、风扇热风和电源高温器件 |
| 风扇区 | 靠近散热风道 | 线束短，不穿越 CSI/USB/NVMe 高速区域 |

### 4.2 机械布局注意点

| ID | 注意点 | 要求 |
| --- | --- | --- |
| MECH-01 | 散热器高度 | 外壳内部必须给 Jetson 散热器和风扇留足高度 |
| MECH-02 | 风道 | 设计明确进风口、出风口和灰尘防护，不允许只靠内部空气循环 |
| MECH-03 | 相机位置 | 镜头开孔、摄像头固定、线束长度和视场角要在 PCB 布局前确定 |
| MECH-04 | NVMe 拆装 | NVMe 固定螺丝和散热贴不能被外壳或线束遮挡 |
| MECH-05 | RTC 更换 | RTC 电池应可维护，不能被散热器、胶水、结构件永久遮住 |
| MECH-06 | 维护接口 | USB-C、Recovery、UART 测试点至少在拆开外壳后可达 |

---

## 5. PCB 层叠与通用走线要求

| ID | 项目 | 要求 |
| --- | --- | --- |
| PCB-01 | 层数 | 不建议 2 层板；至少 4 层，优先 6 层或以上 |
| PCB-02 | 参考地 | USB、CSI、PCIe/NVMe、LAN 等高速信号下方必须有连续参考地 |
| PCB-03 | 控阻抗 | 所有高速差分线必须按板厂叠层计算控阻抗，不允许凭经验随意走线 |
| PCB-04 | 地平面 | 高速差分线下方禁止跨分割地、开槽、缺铜区域 |
| PCB-05 | 换层 | 高速信号尽量少换层；必须换层时旁边放置回流地过孔 |
| PCB-06 | 串扰 | 高速差分线与电源电感、开关节点、风扇线、IO 大电流线保持距离 |
| PCB-07 | 测试点 | 高速差分线不建议随意加测试点，避免形成 stub |
| PCB-08 | 长度匹配 | 差分对组内等长、对间长度按接口规范控制 |
| PCB-09 | ESD | 外露接口和外部线束接口必须有 ESD/浪涌保护路径 |
| PCB-10 | 量产测试 | 关键电源轨、启动控制、Recovery、UART、IO 输入输出应有可探测测试点 |

注：具体线宽、线距、阻抗值、长度容差必须由硬件商结合 NVIDIA Product Design Guide、P3768 参考设计、连接器规范和 PCB 板厂叠层共同确认。本文档不替代 NVIDIA 官方设计规则。

---

## 6. 电源设计与走线注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| PWR-01 | 主电源输入 | 第一版建议 19V 输入，电源适配器和板内电源按整机峰值功耗留余量 |
| PWR-02 | 功耗余量 | 不能只按 Jetson 25W 计算，还要加入 USB/CSI 相机、NVMe、风扇、LAN、IO 外设 |
| PWR-03 | 输入保护 | 电源入口建议具备保险、反接保护、浪涌/TVS、过压/欠压保护 |
| PWR-04 | DC/DC 布局 | 电源转换器、电感、开关节点集中在电源区，远离 CSI、USB、LAN、RTC |
| PWR-05 | 大电流走线 | 19V 输入、5V 风扇、USB 供电、外设供电走线要短、粗、回流明确 |
| PWR-06 | 电源时序 | Jetson 模组相关电源轨必须按 NVIDIA 参考设计和模组要求处理 |
| PWR-07 | USB 相机供电 | 摄像头电源建议单独限流和滤波，不与风扇噪声电源直接混接 |
| PWR-08 | NVMe 供电 | NVMe 3.3V 要考虑上电瞬态电流和掉电稳定性 |
| PWR-09 | RTC 供电 | RTC 后备电池线路要低漏电，远离高温和高噪声区域 |
| PWR-10 | 掉电保护 | 软件会运行数据库/日志/视频，硬件应评估突然断电下的文件系统风险 |

---

## 7. USB 摄像头与 USB-C 走线注意 ID

### 7.1 内置 USB 摄像头

| ID | 注意点 | 要求 |
| --- | --- | --- |
| USB-01 | USB 类型确认 | 确认当前摄像头是 USB2 还是 USB3；USB3 需要额外 SuperSpeed 差分对 |
| USB-02 | 线束固定 | 内置摄像头建议使用锁扣连接器，避免运输震动导致接触不良 |
| USB-03 | 差分线 | D+/D- 以及 USB3 TX/RX 差分对必须控阻抗、等长、少过孔 |
| USB-04 | 供电保护 | 摄像头 VBUS 建议有过流保护、ESD 和滤波 |
| USB-05 | 噪声隔离 | USB 线不要贴近 DC/DC 电感、风扇线、报警输出线 |
| USB-06 | 维护空间 | 内置摄像头线束要能装配和更换，不要被散热器压住 |

### 7.2 USB-C Recovery

| ID | 注意点 | 要求 |
| --- | --- | --- |
| USBC-01 | 功能定位 | USB-C 必须支持 Device / Recovery，不是普通充电口 |
| USBC-02 | 可达性 | USB-C 可隐藏，但拆开外壳后必须能稳定接线刷机 |
| USBC-03 | CC/方向识别 | USB-C CC 逻辑、ESD、VBUS 检测按参考设计处理 |
| USBC-04 | Recovery 配合 | USB-C 维护区域附近应有 Recovery / Reset / GND 测试点 |
| USBC-05 | 显示误解 | 不要求 USB-C 输出显示；不要按显示口使用 |

---

## 8. CSI 摄像头预留走线注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| CSI-01 | 底座位置 | CSI FPC 底座尽量靠近未来相机模组位置，避免长 FPC 穿过整机 |
| CSI-02 | FPC 方向 | 确认底接/顶接、触点方向、装配方向和外壳开孔方向 |
| CSI-03 | MIPI 差分对 | MIPI CSI 差分对必须控阻抗、组内等长、少换层、连续参考地 |
| CSI-04 | 控制信号 | 必须同时预留 I2C、RESET、PWDN/POWER_EN、MCLK 等相机控制信号 |
| CSI-05 | 相机电源 | 预留传感器所需电源轨和使能控制，不能只留数据线 |
| CSI-06 | 噪声隔离 | CSI 区域远离 DC/DC、风扇、报警 IO、LAN 磁性器件 |
| CSI-07 | 软件适配 | CSI 传感器型号变化会带来设备树、驱动和 ISP/Argus 配置工作 |
| CSI-08 | 预留价值 | 如果 CSI 座放得过远、走线绕远或穿越噪声区，实际等于没有预留 |

---

## 9. NVMe M.2 存储走线注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| NVME-01 | 规格 | 建议 M.2 Key-M，优先支持 2280；空间允许兼容 2242/2260 固定孔 |
| NVME-02 | PCIe 通道 | NVMe 使用 PCIe 高速线，必须按 NVIDIA lane 配置和设备树匹配 |
| NVME-03 | 差分线 | PCIe TX/RX 差分对必须控阻抗、等长、短路径、少过孔 |
| NVME-04 | 参考时钟 | REFCLK、PERST#、CLKREQ# 等控制/时钟信号按规范布线 |
| NVME-05 | 供电 | 3.3V 电源需满足 NVMe 启动瞬态电流，靠近插槽布置去耦电容 |
| NVME-06 | 散热 | 预留导热垫或散热片空间，避免 NVMe 位于 Jetson 热风直吹死角 |
| NVME-07 | 量产刷机 | 若 NVMe 作为系统盘，massflash/SDK Manager/刷机脚本目标必须固定为 NVMe |
| NVME-08 | 可维护 | NVMe 固定螺丝可拆，售后可更换；若授权绑定存储，需有换盘流程 |

---

## 10. LAN 口走线注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| LAN-01 | 板边放置 | RJ45 靠板边，便于客户插拔 |
| LAN-02 | 保护器件 | ESD/TVS/浪涌保护靠近接口，接地路径短 |
| LAN-03 | 磁性器件 | 磁性器件、共模电感、中心抽头电路按 PHY/参考设计要求放置 |
| LAN-04 | 差分线 | 以太网差分对控阻抗、等长、少过孔，不跨分割地 |
| LAN-05 | 隔离距离 | 网络隔离区域和机壳地/数字地策略由硬件商按认证要求设计 |
| LAN-06 | 生产测试 | LAN 需做上电链路、DHCP/静态维护地址、吞吐、长时间稳定性测试 |

---

## 11. 风扇与散热注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| FAN-01 | 风扇类型 | 建议 4pin 5V PWM 风扇，包含 5V、GND、PWM、TACH |
| FAN-02 | 转速反馈 | TACH 线要能被系统读取，用于风扇故障检测 |
| FAN-03 | PWM 控制 | PWM 线电平、上拉、电气兼容性需确认 |
| FAN-04 | 供电噪声 | 风扇电源和走线远离相机、CSI、RTC、高速差分线 |
| FAN-05 | 风道 | 风扇必须服务于 Jetson 散热器，不能只在壳内搅动热空气 |
| FAN-06 | 降频风险 | 散热不足会导致 MAXN_SUPER/25W 模式下温度降频，影响 AI 推理和视频稳定 |

---

## 12. RTC 电池与离线时间注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| RTC-01 | 功能定位 | RTC 电池只负责保时间，不负责整机供电 |
| RTC-02 | 电池类型 | 纽扣电池或超级电容方案由硬件商评估寿命、维护和认证 |
| RTC-03 | 低漏电 | RTC 供电线路必须低漏电，避免电池寿命过短 |
| RTC-04 | 位置 | RTC 电池远离高温区域，避免靠近 Jetson 散热器和电源热源 |
| RTC-05 | 可维护 | 电池座应方便售后更换 |
| RTC-06 | 软件验证 | 离线断电后重启，系统时间必须能保持，报警记录时间不能回到默认日期 |

---

## 13. 40pin / 工业 IO 设计注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| IO-01 | 不直驱外设 | Jetson GPIO 不应直接驱动声光报警器、继电器、PLC 输入等外部设备 |
| IO-02 | 隔离输出 | 外部报警输出建议使用光耦、MOS、继电器或隔离驱动 |
| IO-03 | 电压兼容 | 客户现场可能是 12V/24V，必须明确输入/输出电压范围 |
| IO-04 | 干接点 | 若客户需要接 PLC 或报警主机，建议提供干接点输出选项 |
| IO-05 | 保护 | IO 端子必须有 ESD、过流、反接、浪涌保护 |
| IO-06 | 端子位置 | IO 端子靠板边，客户线束不要跨过 Jetson、NVMe、CSI 区域 |
| IO-07 | Pinmux | 所用 GPIO/I2C/SPI/UART/PWM 必须在 pinmux 表和设备树里固定 |
| IO-08 | 方向默认值 | 上电默认态必须安全，不能上电瞬间误触发报警器 |
| IO-09 | 软件一致性 | 硬件 IO 编号、Linux GPIO 编号、前端配置名称要建立映射表 |
| IO-10 | 电平标准 | 3.3V 容忍、开漏、上拉/下拉等必须按 NVIDIA pinmux 要求确认 |

---

## 14. Debug、Recovery 与量产测试点注意 ID

| ID | 注意点 | 要求 |
| --- | --- | --- |
| DBG-01 | Debug UART | 必须保留串口日志接口，用于无系统/无网络诊断 |
| DBG-02 | Recovery | 必须保留 Recovery 与 GND 进入强制恢复模式 |
| DBG-03 | Reset | 必须保留 Reset 控制点 |
| DBG-04 | Power | 建议保留 Power 控制点或自动上电配置点 |
| DBG-05 | GND | 维护接口附近必须有可靠 GND 测试点 |
| DBG-06 | 工装夹具 | 测试点位置要适合 pogo pin 工装，不应被高器件遮挡 |
| DBG-07 | 标识 | PCB 丝印或生产图纸必须标清测试点编号和功能 |

---

## 15. 高风险设计项清单

| 风险 ID | 风险描述 | 后果 | 规避要求 |
| --- | --- | --- | --- |
| RISK-01 | 删除或藏死 USB-C Recovery | 系统损坏后无法救砖/刷机 | 必须可接线、可进入 RCM |
| RISK-02 | 不保留 Debug UART | 启动失败无法定位原因 | 必须留测试点 |
| RISK-03 | CSI 座离相机太远 | 后续 CSI 版本画面不稳定或不可用 | CSI 座靠近相机，走线短且连续参考地 |
| RISK-04 | GPIO 直接接报警器 | 烧毁模组或误触发 | 必须隔离和驱动 |
| RISK-05 | NVMe/USB/PCIe lane 冲突 | 设备无法识别或刷机失败 | 硬件 lane、ODMDATA、设备树、刷机配置一致 |
| RISK-06 | 电源余量不足 | 重启、掉线、相机黑屏、NVMe 掉盘 | 按整机峰值功耗设计余量 |
| RISK-07 | 高速线跨分割地 | USB/CSI/LAN/NVMe 不稳定 | 高速线下方保持完整参考地 |
| RISK-08 | RTC 放在高温区 | 电池寿命短、时间丢失 | 远离热源，低漏电设计 |
| RISK-09 | 无风扇 TACH | 风扇坏了软件不知道 | 使用 4pin 风扇并接入转速反馈 |
| RISK-10 | NVMe 热设计不足 | 写入降速、掉盘、寿命下降 | 预留导热垫和散热路径 |
| RISK-11 | LAN 无保护 | 工业现场浪涌导致损坏 | 接口侧加入保护和隔离设计 |
| RISK-12 | 默认 IO 态不安全 | 上电误报警或误动作 | IO 默认电平必须安全 |

---

## 16. 软件与硬件联动要求

| 项目 | 硬件要求 | 软件影响 |
| --- | --- | --- |
| 自定义载板 | 提供 board name、EEPROM/ID 策略、设备树修改 | 需要更新 MB1/MB2、ODMDATA、device tree、flash config |
| NVMe 系统盘 | M.2 Key-M 供电和 PCIe 稳定 | 刷机脚本、massflash、rootfs 目标改为 NVMe |
| GPIO/IO | 明确 pinmux、默认态、电平、隔离方式 | 后端 IO 映射表、前端配置、报警输出逻辑要对应 |
| CSI 相机 | 明确传感器型号、电源、I2C、reset、MCLK | 需要驱动、设备树、V4L2/Argus 测试 |
| RTC | 保证离线保时 | 后端日志、报警记录、授权时间校验依赖系统时间 |
| 风扇 TACH | 转速反馈可读 | 软件可做温度/风扇故障报警 |
| LAN | 默认 DHCP + 维护地址策略 | 前端扫描和自动连接逻辑依赖网络稳定 |
| USB-C Recovery | 可进入 RCM | 支持救砖、完整刷机、量产烧录 |

NVIDIA 官方文档明确指出，自定义载板不同于 P3768 开发板时，需要同步修改 kernel device tree、MB1、MB2、ODMDATA 和 flashing configuration。因此硬件设计不能只交 PCB，还必须同步交软件适配资料。

---

## 17. 硬件商交付物清单

| 类型 | 交付物 | 要求 |
| --- | --- | --- |
| 原理图 | PDF + 源文件 | 标注与 NVIDIA 参考设计差异 |
| PCB | Layout 源文件 + Gerber + 钻孔 + 坐标文件 | 包含层叠、阻抗、差分线规则 |
| BOM | 可采购清单 | 标注关键器件、替代料、寿命和温度等级 |
| 叠层 | PCB stackup | 明确每层用途、介质厚度、铜厚、目标阻抗 |
| 走线报告 | 高速线长度/阻抗/规则报告 | USB、CSI、PCIe/NVMe、LAN 必须覆盖 |
| 电源报告 | 电源树、功耗预算、温升评估 | 包括 Jetson、相机、NVMe、风扇、IO |
| Pinmux | pinmux 表、GPIO 映射表 | 软件可直接使用 |
| BSP 资料 | device tree、MB1/MB2、ODMDATA、flash config 修改说明 | 支持量产刷机 |
| 测试报告 | 样机 bring-up 测试 | 包括上电、刷机、LAN、USB 摄像头、CSI 预留、NVMe、RTC、风扇、IO |
| 结构资料 | 3D 模型、接口位置图 | 与外壳、镜头、风扇、线束联动 |

---

## 18. 样机验收检查表

| 检查项 | 验收方法 | 结果 |
| --- | --- | --- |
| 19V 上电 | 接入适配器，设备自动启动 | 待测 |
| MAXN_SUPER/25W 模式 | 运行 nvpmodel 检查模式 | 待测 |
| LAN 通讯 | 前端可扫描并连接设备 | 待测 |
| USB 摄像头 | 后端可打开摄像头并输出视频流 | 待测 |
| NVMe | 系统可识别、读写稳定、可作为刷机目标 | 待测 |
| USB-C Recovery | 主机可识别 RCM 设备并刷机 | 待测 |
| Debug UART | 可读取启动日志 | 待测 |
| RTC | 断电后重新上电时间保持 | 待测 |
| 风扇 PWM | 可调速 | 待测 |
| 风扇 TACH | 可读取转速 | 待测 |
| IO 输出 | 可驱动声光报警/继电器/PLC 输入 | 待测 |
| IO 默认态 | 上电不误触发 | 待测 |
| CSI 预留 | FPC 座、电源、I2C、reset、MCLK 连通性确认 | 待测 |
| 温升 | 长时间 AI 推理和视频流运行不降频 | 待测 |
| 掉电恢复 | 断电重启后后端自动运行 | 待测 |
| 量产测试点 | 工装可接触关键测试点 | 待测 |

---

## 19. 给硬件商的简化需求描述

请按 Jetson Orin Nano / Orin Nano Super 产品化载板设计一块最小功能板。客户侧只需外露电源、LAN、报警 IO 和状态灯；工厂/售后侧隐藏保留 USB-C Recovery、Recovery/Reset/Power/GND、Debug UART 和关键测试点。

板内必须包含：NVMe M.2 Key-M、内置 USB 摄像头接口、预留 CSI FPC 底座、RTC 电池、4pin 5V PWM 风扇接口、工业 IO 隔离驱动。PCB 布局和走线必须按 NVIDIA Orin Nano/NX 相关设计指南和 P3768 参考载板约束执行，尤其注意 USB、CSI、PCIe/NVMe、LAN 的高速差分线控阻抗、连续参考地、少过孔、远离电源开关噪声。

硬件交付必须同步给出 pinmux、GPIO 映射、ODMDATA、设备树、刷机配置和量产测试方案，不能只交 PCB。

---

## 20. 参考资料

1. NVIDIA Jetson Orin Nano Developer Kit User Guide - Hardware Layout  
   https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/hardware_layout.html

2. NVIDIA Jetson Orin Nano Developer Kit User Guide - How-to Guides / Force Recovery / Power Mode / CSI Camera  
   https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/howto.html

3. NVIDIA Jetson Orin Nano Developer Kit User Guide - BSP Setup / Flash to NVMe  
   https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_bsp.html

4. NVIDIA Jetson Orin Nano Developer Kit Carrier Board Specification SP-11324-001  
   https://developer.nvidia.com/downloads/assets/embedded/secure/jetson/orin_nano/docs/jetson_orin_nano_devkit_carrier_board_specification_sp.pdf

5. NVIDIA Jetson Linux Developer Guide - Jetson Orin NX and Nano Series, Module Adaptation and Bring-Up  
   https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/HR/JetsonModuleAdaptationAndBringUp/JetsonOrinNxNanoSeries.html

