# Intel I225-V · macOS 27 兼容研究

在一台 i7-12700K / Z690 主机上，AppleIntelI210Ethernet 2.3.1 已在 **macOS 27.2 `26B123` Golden Gate（x86_64）** 接管 I225-V。两次开机验证了千兆链路和网关连通，第二次抓到新的 DHCP ACK，使用者确认可以上网。操作方法、双系统配置和回退步骤见 [Golden Gate I225-V 指南](docs/GOLDEN-GATE-I225.zh-CN.md)。

仓库也保存了 2026-11-01 对 Apple 官方 ARM 安装载荷的离线检查。该检查与上述 x86_64 实机采用不同输入。旧 I210 的 arm64e 候选在所查集合中有两个未匹配的导入符号，旧 AVB 依赖也未列出。 [历史离线报告](docs/OFFLINE-REPORT.zh-CN.md)

macOS 26 的基线来自 [intel-i225-tahoe-fix](https://github.com/GeekAudio/intel-i225-tahoe-fix)，固定提交 [3813bdac](https://github.com/GeekAudio/intel-i225-tahoe-fix/commit/3813bdac651822de56191f7e39c221f71a32478e)。

## 当前边界

Apple 将 Tahoe 定为最后支持 Intel Mac 的大版本；[macOS 27 官方支持列表](https://support.apple.com/en-ca/127255)全部是 Apple 芯片机型。
Intel 黑苹果需要先有经过验证的目标系统启动路径，才能进入网卡运行适配。

离线工作分为四层：安装载荷完整性、实际二进制架构、网络驱动依赖与符号、目标硬件实测。
前三层可以提前检查；离线扫描不能替代最后一层，也不能证明 C++ ABI、DMA、中断或睡眠恢复正确。

## 工具

需要 Python 3.9 或更新版本。下载和通用扫描使用 Python 标准库；安装器解包及符号检查使用 macOS 自带的 `pkgutil`、`aa`、`nm`。
工具写入指定输出目录；不修改 EFI、不加载驱动、不运行安装器。

### 获取最新正式版并固定来源

```sh
python3 tools/apple_installer.py discover --output work/target.json
python3 tools/apple_installer.py download --manifest work/target.json --destination downloads
```

发现流程同时核对 Apple 软件更新目录和 `gdmf.apple.com` 的公开正式版 build，防止把测试版或其他系统当作目标。
下载支持续传，先核对目录中的字节数及 SHA-1，再记录本地 SHA-256。
之后以该固定清单复验；重新运行 `discover` 可能选择更新的正式版。

**本次完整性例外：** 实际整包 SHA-1 与目录 `Digest` 不一致；Apple CNKL 的 **1699 个 SHA-256 分块全部匹配**，
且 `pkgutil` 返回 `signed Apple Software`。报告保留这项差异，没有把 SHA-1 检查记为通过。
安装包本地 SHA-256 为 `26bee623af06bf6c78a57e62ea6f188e678b841d9d30f25415fe73cf8444183a`。

下载工具遇到目录 SHA-1 不符会保留文件并停止。可使用已从 Apple HTTPS 固定摘要的 CNKL，再独立验证分块与 Apple 包签名：

```sh
python3 tools/verify_integrity.py \
  --package downloads/InstallAssistant-27.2-26B123.pkg.partial \
  --manifest work/target.json --chunklist work/target.integrityDataV1 \
  --output work/verified-target.json
```

独立验证通过后，后续工具使用该验证清单，`--package` 指向实际文件。
CNKL method 2 的末尾是无密钥 SHA-256 校验值；其来源认证依靠 Apple HTTPS 固定摘要，包签名由系统另行验证。

### 解包而不安装

```sh
python3 tools/prepare_installer.py \
  --package downloads/InstallAssistant-27.2-26B123.pkg \
  --manifest work/target.json --output work/prepared
```

先核对包 SHA-256 和 Apple 包签名，再校验并提取 XAR 中的 Payload 与 SharedSupport。
需要完整安装包之外的额外暂存空间；脚本不会执行安装包脚本。

暂存空间有限时，可以使用本机回环地址只读提供包内的 SharedSupport 镜像，省去第二份镜像副本：

```sh
python3 tools/serve_shared_support.py \
  --package downloads/InstallAssistant-27.2-26B123.pkg \
  --manifest work/target.json --port 8765 --ready-file work/image-server.json
```

在另一终端运行：

```sh
mkdir -p work/mnt/shared
hdiutil attach http://127.0.0.1:8765/SharedSupport.dmg \
  -insecurehttp -readonly -nobrowse -noautoopen -mountpoint "$PWD/work/mnt/shared"
```

服务只监听 `127.0.0.1`，只提供该镜像的读取，不提供目录或写入。
挂载服务本身不重新核验整包摘要，使用前先完成下载工具的校验；检查结束后用 `hdiutil detach` 卸载，再停止服务。

### 解封装内核并检查集合

```sh
python3 tools/inspect_kernel_archive.py \
  --archive /path/to/mounted/MacSoftwareUpdate/asset.zip \
  --target-manifest work/verified-target.json \
  --output work/kernel-architectures.json --keep-directory work/kernels

python3 tools/inspect_collection.py \
  --collection work/kernels/kernelcache.release.mac14j.kc \
  --candidate-report evidence/2026-11-01/candidate.json --arch arm64e \
  --output work/collection-audit.json
```

前者核对 ZIP 内真实 `SystemVersion.plist`，解封装 IM4P / LZFSE 后读取 Mach-O 头。
后者显式限定一份离线集合，核对依赖版本及定义符号名，不混用当前运行系统的集合。
本次集合检查返回 `STATIC_INCOMPLETE`；找到同名符号也不等于链接许可、vtable 或运行 ABI 正确。

### 检查候选驱动与离线系统

驱动沿用上述基线仓库，本仓库不重复存放 Apple 二进制。

```sh
python3 tools/inspect_candidate.py --kext /path/to/AppleIntelI210Ethernet.kext \
  --output work/candidate.json

python3 tools/offline_audit.py --root /Volumes/OfflineSystem \
  --kext /path/to/AppleIntelI210Ethernet.kext \
  --arch x86_64 --scope system --version 27.2 --build 26B123 \
  --output work/audit.json
```

`--root` 必须是明确提供的离线系统根目录；`--scope recovery` 只检查恢复系统，结果不能代表完整 OS。
压缩、加密或无法识别的内核会保留为未知，需要先解封装，不能按“缺少某架构”处理。
依赖若只存在于内核集合中、未被当前扫描解析，也会保留为未解决。

| 退出码 | 含义 |
| --- | --- |
| `0` | 本次静态前提检查通过，运行验证仍为 `NOT_RUN` |
| `1` | 静态证据不足，有待解析的依赖或内核 |
| `2` | 输入、版本、下载或文件读取错误 |
| `3` | 本次静态检查发现明确阻碍，例如所检查的内核架构不符 |

`MinKernel / MaxKernel` 使用 Darwin 版本；原项目这两个字段本来就为空。
修改版本范围、设备显示名称或启动参数，不能替代内核架构和 ABI 适配。

## 证据与后续工作

2026-11-01 的固定来源、候选驱动清单和离线结果保存在 [evidence/2026-11-01](evidence/2026-11-01)。
Apple 安装器和解包载荷保留在本地，仓库保存工具及可复核的派生记录。

当前实测范围和剩余测试见 [Golden Gate I225-V 指南](docs/GOLDEN-GATE-I225.zh-CN.md)。其他系统、架构和硬件可参考 [适配清单](docs/NEXT-STEPS.zh-CN.md)。

后续工作以具体 macOS build 为单位：复核目标内核与网络组件；检查依赖和符号；如目标系统能够启动，再做驱动绑定、DHCP、局域网持续传输、拔插网线、重启和多次睡眠唤醒测试。
记录测试链路速率和吞吐，不能将 Tahoe 的千兆结果或驱动包含 `arm64e` 当作 27 的兼容结论。

测试工具：

```sh
python3 -m unittest discover -s tests -v
```

测试使用合成的小型输入验证检查器的判定边界，与真实 macOS 镜像证据分开保存。
原创工具及说明采用 MIT 许可；Apple 软件保留原权利归属。
