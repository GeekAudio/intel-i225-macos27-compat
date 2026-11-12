# macOS 27.2 Golden Gate 的 Intel I225-V 驱动方法

适用于已经能启动的 **macOS 27.2 `26B123` Golden Gate（x86_64）** 和 Intel I225-V（`8086:15f3`）。

## 下载

下载 [驱动包 ZIP](https://github.com/GeekAudio/intel-i225-macos27-compat/releases/download/v0.1.2/I225-V-GoldenGate-26B123-v0.1.2.zip) 和 [SHA-256 校验文件](https://github.com/GeekAudio/intel-i225-macos27-compat/releases/download/v0.1.2/I225-V-GoldenGate-26B123-v0.1.2.zip.sha256)，在同一目录校验并解压。

```sh
shasum -a 256 -c I225-V-GoldenGate-26B123-v0.1.2.zip.sha256 &&
  unzip I225-V-GoldenGate-26B123-v0.1.2.zip
```

## 配置 OpenCore

1. 备份 `EFI/OC/config.plist` 和原驱动。双系统保留 `EFI/OC-26` 或独立的 macOS 26 引导。
2. 把下载包里的 `Kexts/AppleIntelI210Ethernet-27.kext` 放入 `EFI/OC/Kexts`。把 [Kernel-Add-27.plist](opencore/Kernel-Add-27.plist) 的字典作为新条目加到 `Kernel → Add`，其 `MinKernel` 和 `MaxKernel` 都为 `27.2.0`。若已有 macOS 26 的 I210 条目，保留该条目，并把为空或高于 `26.99.99` 的 `MaxKernel` 设为 `26.99.99`。
3. 在 `DeviceProperties → Add` 找到**本机 I225 的 PCI 路径**，合并 [I225-DeviceProperties.plist](opencore/I225-DeviceProperties.plist) 的两个 Data 值，即 `device-id = 33150000` 和 `built-in = 01`。
4. 在 `NVRAM → Add → 7C436110-AB2A-4BBB-A880-FE41995C9F82 → boot-args` 中保留现有参数，把 `e1000` 设为 `e1000=0`，并在 `NVRAM → Delete` 的同一 GUID 数组中列出 `boot-args`，让新值覆盖旧值。确保给同一块卡用的 AppleIGC 等驱动在 27.2 不加载。共用 EFI 中若有其他系统依赖 E1000，为 27 使用独立引导配置。若曾改过 27 的 E1000 probe 使它忽略该参数，先按指南恢复检查。 [E1000 恢复步骤](docs/GOLDEN-GATE-I225.zh-CN.md)
5. 用同版本 `ocvalidate` 校验配置。确认配置引用和 kext 路径一致后写入目标 EFI，同步、只读重挂并回读校验。

## 启动验证与回退

进入 27 后运行下列命令。若以太网接口不是 `en0`，将它替换为本机实际接口。

```sh
networksetup -listallhardwareports
sysctl -n kern.bootargs | tr ' ' '\n' | grep -Fx 'e1000=0'
kmutil showloaded --list-only | grep AppleIntelI210Ethernet
ioreg -r -c AppleIntelI210 -d 2
ifconfig en0
ipconfig getpacket en0
gateway=$(ipconfig getoption en0 router)
test -n "$gateway" && ping -n -b en0 -c 3 "$gateway"
curl --noproxy '*' --interface en0 --connect-timeout 5 --max-time 10 -I https://example.com/
```

回退时从可启动的引导进入 26，恢复备份的活动 EFI 配置，再移除 `AppleIntelI210Ethernet-27.kext`。若修改过 27 的 E1000，按备份还原其原二进制。

从原版 I210 重新生成 kext 的命令和完整操作见 [驱动指南](docs/GOLDEN-GATE-I225.zh-CN.md)。
