# macOS 27.2 Golden Gate 的 Intel I225-V 有线网卡

在一台 i7-12700K / Z690 主机上，Intel I225-V（PCI `8086:15f3`）已用 AppleIntelI210Ethernet 2.3.1 在 Golden Gate 上运行。两次开机均识别网卡、协商到 1000baseT 全双工并能访问网关。第二次抓包记录了同一事务的 DHCP Request 和 ACK，使用者也确认能正常上网。

| 项目 | 实测范围 |
| --- | --- |
| 系统 | Liberator Beta 1 / Golden Gate，macOS 27.2 `26B123`，Darwin `27.2.0`，x86_64 |
| 引导 | OpenCore 1.0.8，macOS 26 与 27 共用一份活动 EFI |
| 网卡 | Intel I225-V `8086:15f3`，使用现有 I210 设备属性 |
| 驱动 | AppleIntelI210Ethernet 2.3.1 的 x86_64 slice |
| 运行证据 | 两次开机确认驱动绑定、千兆链路、默认路由与网关应答。第二次完整捕获 DHCP 续用地址的 Request / ACK |
| 待测 | 独立采集 27 的外网探测结果、持续吞吐、睡眠恢复、2.5GbE 和其他主板或 I226 |

Golden Gate 使用从同版本 KDK 构建的 Intel 内核集合。本文假定目标已经能启动到桌面。Apple 原版 arm64e 安装载荷的研究记录适用于另一组输入。 [Liberator Beta 1](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v3.0.0-beta.1)

## 1. 备份 EFI 和已有驱动

核对启动分区的 GPT 分区 UUID。备份当前 `EFI/OC/config.plist`、原 I210 kext 和已有的 `EFI/OC-26`，或保留独立可启动的 26 引导介质。如果 27 上曾经手工改过 E1000，同时备份 27 的 DEXT。以下步骤在 EFI 副本上准备和验证。

从自己的可用配置取出 AppleIntelI210Ethernet 2.3.1。实测通用二进制包含 `x86_64` 和 `arm64e`，本次只用 x86_64。以下是实测源二进制的 SHA-256。

```text
c2639077ffe5f491e5624782bd59fbc916730fb0c4515b2b5cee004073a40841
```

校验路径为 `AppleIntelI210Ethernet.kext/Contents/MacOS/AppleIntelI210Ethernet`。发行资产只包含本文及其校验文件。 [macOS 26 I210 基线](https://github.com/GeekAudio/intel-i225-tahoe-fix)

## 2. 创建一份仅供 27 使用的 kext

在活动 EFI 的副本中执行，`OC_COPY` 指向副本的 `OC` 目录。保留原 kext 和它的现有条目。给 27 新增独立的文件夹，保留 Apple 的 `CFBundleIdentifier` 与可执行文件，只从副本的依赖列表中删除旧 AVB 组件。

```sh
OC_COPY=/path/to/copied/EFI/OC
source_kext="$OC_COPY/Kexts/AppleIntelI210Ethernet.kext"
target_kext="$OC_COPY/Kexts/AppleIntelI210Ethernet-27.kext"
test ! -e "$target_kext" &&
  ditto "$source_kext" "$target_kext" &&
  /usr/libexec/PlistBuddy -c 'Delete :OSBundleLibraries:com.apple.iokit.IOEthernetAVBController' \
    "$target_kext/Contents/Info.plist" &&
  plutil -lint "$target_kext/Contents/Info.plist"
```

目标 27 的 x86_64 内核集合缺少旧的 `IOEthernetAVBController` bundle。I210 未直接引用该控制器类，所需的相关 `IOEthernetController` 方法仍在集合中。保留其他依赖。编辑 `Info.plist` 会改变 Apple 原签名所覆盖的资源，本方法使用 Golden Gate 已有的 OpenCore 注入路径。此次没有改 I210 机器码、C++ 符号或虚表。

## 3. 配置 OpenCore

在 `Kernel → Add` 中保留 macOS 26 的 I210 条目。实测原条目的 `MaxKernel` 是 `26.99.99`，确保旧条目不会同时进入 Darwin 27。若原条目没有上限，给原条目加 `26.99.99`，同时保留原下限和启用状态。紧接其后加入以下条目。

| 字段 | 值 |
| --- | --- |
| `BundlePath` | `AppleIntelI210Ethernet-27.kext` |
| `ExecutablePath` | `Contents/MacOS/AppleIntelI210Ethernet` |
| `PlistPath` | `Contents/Info.plist` |
| `Arch` | `x86_64` |
| `Enabled` | `true` |
| `MinKernel` | `27.2.0` |
| `MaxKernel` | `27.2.0` |

保留原来可用的 I225 PCI 路径和设备属性。实测在 `DeviceProperties → Add` 的 I225 节点使用 Data 类型的 `device-id = 33150000`（小端 `0x1533`）与 `built-in = 01`。PCI 路径随主板和固件变化。

实测配置原本就带 `e1000=0`。在本机，27 的 E1000 曾被手工修改为忽略该参数，因此切换时恢复了 27 DEXT 的原有 probe 检查。已有这类改动的机器，应从同 build 的备份恢复对应检查，再验证 E1000 没有接管这块卡。若共用引导下的其他系统依赖 E1000，使用独立的 27 引导配置。本文方案使用 I210，AppleIGC 不参与。

## 4. 验证、启动和回退

1. 用同版本的 `ocvalidate` 检查副本。核对配置差异和所有引用文件，确认原 26 条目依然适用、27 只选中新的 I210 条目。
2. 实测用 OpenCore 1.0.8 的 `ProcessKernel` 离线跑了两份真实 BootKC。27 的输出含新增 I210 fileset，26 仍注入旧 I210，并按 Darwin 版本跳过新条目。该工具不支持 `Kernel → Force`，因此仅在测试用副本中清空该数组，实际部署保留原有的 `Force`。 [OpenCore 1.0.8 ProcessKernel 源码](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Utilities/TestProcessKernel/ProcessKernel.c)
3. 确认备份可用后，把验证过的配置和新增 kext 写到目标 ESP。同步、卸载、只读重挂并比对 SHA-256。启动 27，按下列命令分别核对驱动、链路、租约和出口。示例接口是 `en0`，应以本机实际接口为准。

```sh
networksetup -listallhardwareports
kmutil showloaded --list-only | grep AppleIntelI210Ethernet
ioreg -r -c AppleIntelI210 -d 2
ifconfig en0
ipconfig getpacket en0
route -n get default
gateway=$(ipconfig getoption en0 router)
test -n "$gateway" && ping -n -b en0 -c 3 "$gateway"
curl --noproxy '*' --interface en0 --connect-timeout 5 --max-time 10 -I https://example.com/
```

判断 DHCP 是否来自本次启动时，用 `tcpdump` 比对 Request 和 ACK 的事务 ID，避免把缓存租约当成新应答。关闭 EEE、改用软件校验和以及降到 100 Mbps 的 E1000 实验均未在这台机器恢复联网。

回退时从已知可启动的引导进入 26，恢复修改前的活动 EFI 配置，再移除新增的 `AppleIntelI210Ethernet-27.kext`。如果本次修改过 27 的 E1000，按备份还原 27 卷上的对应文件。重挂校验后再启动目标系统。
