# macOS 27.2 Golden Gate 的 Intel I225-V 有线网卡

[简体中文](GOLDEN-GATE-I225.zh-CN.md) | [English](GOLDEN-GATE-I225.en.md)

在一台 i7-12700K / Z690 主机上，Intel I225-V（PCI `8086:15f3`）已用 AppleIntelI210Ethernet 2.3.1 在 Golden Gate 上运行。两次开机均识别网卡、协商到 1000baseT 全双工并能访问网关。第二次抓包记录了同一事务的 DHCP Request 和 ACK，使用者也确认能正常上网。

| 项目 | 实测范围 |
| --- | --- |
| 系统 | Liberator Beta 1 / Golden Gate，macOS 27.2 `26B123`，Darwin `27.2.0`，x86_64 |
| 引导 | OpenCore 1.0.8，macOS 26 与 27 共用一份活动 EFI |
| 网卡 | Intel I225-V `8086:15f3`，使用现有 I210 设备属性 |
| 驱动 | AppleIntelI210Ethernet 2.3.1 的 x86_64 slice |
| 运行证据 | 两次开机的 IOService 树均为 `AppleIntelI210 → en0`，记录了千兆链路、默认路由与网关应答。第二次完整捕获 DHCP 续用地址的 Request / ACK |
| 待测 | 独立采集 27 的外网探测结果、持续吞吐、睡眠恢复、2.5GbE 和其他主板或 I226 |

Golden Gate 使用从同版本 KDK 构建的 Intel 内核集合。本文假定目标已经能启动到桌面。Apple 原版 arm64e 安装载荷的研究记录适用于另一组输入。 [Liberator Beta 1](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v3.0.0-beta.1)

## 1. 备份 EFI 和已有驱动

核对启动分区的 GPT 分区 UUID。备份当前 `EFI/OC/config.plist`、原 I210 kext 和已有的 `EFI/OC-26`，或保留独立可启动的 26 引导介质。如果 27 上曾经手工改过 E1000，同时备份 27 的 DEXT。以下步骤在 EFI 副本上准备和验证。

实测通用二进制包含 `x86_64` 和 `arm64e`，本次只用 x86_64。以下是源二进制的 SHA-256。

```text
c2639077ffe5f491e5624782bd59fbc916730fb0c4515b2b5cee004073a40841
```

源和发布包的校验路径均为 kext 内的 `Contents/MacOS/AppleIntelI210Ethernet`。 [macOS 26 I210 基线发布包](https://github.com/GeekAudio/intel-i210-i225-ethernet/releases/tag/v1.0.2)

## 2. 准备仅供 27 使用的 kext

解压 [v0.1.2 发布包](https://github.com/GeekAudio/intel-i225-macos27-compat/releases/tag/v0.1.2)，取其中的 `Kexts/AppleIntelI210Ethernet-27.kext`。也可在本仓库根目录从原版驱动生成，`--kext` 指向 Tahoe v1.0.2 发布包内的原 kext。

```sh
mkdir -p work/kexts
python3 tools/prepare_i210_27.py \
  --kext /path/to/AppleIntelI210Ethernet.kext --output-dir work/kexts
```

目标 27 的 x86_64 内核集合缺少旧的 `IOEthernetAVBController` bundle。I210 未直接引用该控制器类，所需的相关 `IOEthernetController` 方法仍在集合中。保留其他依赖。编辑 `Info.plist` 会改变 Apple 原签名所覆盖的资源，本方法使用 Golden Gate 已有的 OpenCore 注入路径。此次没有改 I210 机器码、C++ 符号或虚表。

## 3. 配置 OpenCore

把准备好的 kext 放入 EFI 副本的 `OC/Kexts`。把 [`Kernel-Add-27.plist`](../opencore/Kernel-Add-27.plist) 的字典加入 `Kernel → Add`。若已有 macOS 26 的 I210 条目，保留原条目，将为空或高于 `26.99.99` 的 `MaxKernel` 设为 `26.99.99`，并把 27 的条目放在它后面。

| 字段 | 值 |
| --- | --- |
| `BundlePath` | `AppleIntelI210Ethernet-27.kext` |
| `ExecutablePath` | `Contents/MacOS/AppleIntelI210Ethernet` |
| `PlistPath` | `Contents/Info.plist` |
| `Arch` | `x86_64` |
| `Enabled` | `true` |
| `MinKernel` | `27.2.0` |
| `MaxKernel` | `27.2.0` |

把 [`I225-DeviceProperties.plist`](../opencore/I225-DeviceProperties.plist) 的两个属性合并到 `DeviceProperties → Add` 的 I225 节点。实测值为 Data 类型的 `device-id = 33150000`（小端 `0x1533`）与 `built-in = 01`。PCI 路径随主板和固件变化。

对照原 EFI 或 IORegistryExplorer 中 I225 的 PCI 父链确认路径。实测主机的路径为 `PciRoot(0x0)/Pci(0x1C,0x2)/Pci(0x0,0x0)`，此值仅供对照。

在 `NVRAM → Add → 7C436110-AB2A-4BBB-A880-FE41995C9F82 → boot-args` 中保留原参数，并确保 `e1000` 只有一个值 `e1000=0`。在 `NVRAM → Delete → 7C436110-AB2A-4BBB-A880-FE41995C9F82` 数组里保留其他条目并列出 `boot-args`。OpenCore 先删除这个旧变量，再写入完整的新值。 [OpenCore 1.0.8 配置文档](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex)

若原 EFI 也为此卡配置了 AppleIGC 等驱动，限定这些条目的 Darwin 版本，使其跳过 27.2.0。若共用引导下的其他系统依赖 E1000，使用独立的 27 引导配置。未改过 E1000 probe 的机器可直接进入启动验收。

### 曾修改 E1000 忽略 `e1000=0`

优先使用同一 build、同一目标卷的已验证备份还原 probe 检查。如果当前文件是本项目先前测试的 x86_64 EEE-off 版本（SHA-256 `ed2f60274dc16a8078532e22ff06df7285e55c1e4269014248a3e4ad6190d9ee`），可在 DEXT 副本中用发布包的 `tools/restore_e1000_probe.py` 重现实测修复。工具对其他哈希会停止。

```sh
SYS='/Volumes/macOS 27' # 先按卷 UUID 和 SystemVersion.plist 核对目标
NAME=com.apple.DriverKit-AppleEthernetE1000
WORK=$(mktemp -d)
cp -RX "$SYS/System/Library/DriverExtensions/$NAME.dext" "$WORK/"
python3 tools/restore_e1000_probe.py \
  --input "$WORK/$NAME.dext/$NAME" --output "$WORK/$NAME.restored" &&
  mv "$WORK/$NAME.restored" "$WORK/$NAME.dext/$NAME" &&
  codesign --verify --strict "$WORK/$NAME.dext"
```

通过签名校验后，备份 27 上的原二进制，只将恢复后的可执行文件替换到已确认的 27 卷，保留 `root:wheel`、`0755`、`restricted` 和原 `Info.plist`。按原挂载方式重挂并再次验证签名及 SHA-256 `62e312646fe8d59682be94fb3bbf9a8019ac421db5c9718205efc2d9bbc02c38`。

## 4. 验证、启动和回退

1. 用同版本的 `ocvalidate` 检查副本。核对配置差异和所有引用文件，确认原 26 条目依然适用、27 只选中新的 I210 条目。
2. 实测用 OpenCore 1.0.8 的 `ProcessKernel` 离线跑了两份真实 BootKC。27 的输出含新增 I210 fileset，26 仍注入旧 I210，并按 Darwin 版本跳过新条目。该工具不支持 `Kernel → Force`，因此仅在测试用副本中清空该数组，实际部署保留原有的 `Force`。 [OpenCore 1.0.8 ProcessKernel 源码](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Utilities/TestProcessKernel/ProcessKernel.c)
3. 确认备份可用后，把验证过的配置和新增 kext 写到目标 ESP。同步、卸载、只读重挂并比对 SHA-256。启动 27，按下列命令分别核对驱动、链路、租约和出口。示例接口是 `en0`，应以本机实际接口为准。

```sh
networksetup -listallhardwareports
sysctl -n kern.bootargs | tr ' ' '\n' | grep -Fx 'e1000=0'
kmutil showloaded --list-only | grep AppleIntelI210Ethernet
ioreg -r -c AppleIntelI210 -d 2
ifconfig en0
ipconfig getpacket en0
route -n get default
gateway=$(ipconfig getoption en0 router)
test -n "$gateway" && ping -n -b en0 -c 3 "$gateway"
curl --noproxy '*' --interface en0 --connect-timeout 5 --max-time 10 -I https://example.com/
```

在 I/O Registry 中确认 `AppleIntelI210` 下挂的是目标以太网接口，驱动出现在 `kmutil` 列表里只代表它已加载。判断 DHCP 是否来自本次启动时，用 `tcpdump` 比对 Request 和 ACK 的事务 ID，避免把缓存租约当成新应答。关闭 EEE、改用软件校验和以及降到 100 Mbps 的 E1000 实验均未在这台机器恢复联网。

回退时从已知可启动的引导进入 26，恢复修改前的活动 EFI 配置，再移除新增的 `AppleIntelI210Ethernet-27.kext`。如果本次修改过 27 的 E1000，按备份还原 27 卷上的对应文件。重挂校验后再启动目标系统。
