# macOS 27.2 / I225-V 离线检查

[简体中文](OFFLINE-REPORT.zh-CN.md) | [English](OFFLINE-REPORT.en.md)

> 本文保留 2026-11-01 的离线研究记录。2026-11-12 的 Golden Gate x86_64 实机方法及验证范围见 [I225-V 指南](GOLDEN-GATE-I225.zh-CN.md)。

日期：2026-11-01。目标：Apple 公开正式版 macOS 27.2，build `26B123`，软件更新产品 `142-50055`。
候选：原 Tahoe 项目的 AppleIntelI210Ethernet 2.3.1，目标硬件 ID `8086:15f3`。

## 结论

本次完成了完整安装器下载、独立完整性检查、14 份实际内核的架构检查，以及一份 boot collection 的依赖和符号检查。
**当前 Apple 安装载荷没有 x86_64 内核，因此这套 Intel 黑苹果无法通过网卡配置改动直接升级到该系统。**
I210 的 arm64e 路线也尚未通过静态前提检查，不能作为已兼容驱动发布。

| 检查 | 实际结果 |
| --- | --- |
| 完整安装包 | 17,807,147,403 字节，已保留本地 |
| 目录 `Digest` / 整包 SHA-1 | 不一致，保留记录 |
| Apple CNKL 分块 | 1699 / 1699 个 SHA-256 匹配；method-2 trailer SHA-256 匹配 |
| Apple 包签名 | `pkgutil` 退出 0，状态 `signed Apple Software` |
| 安装器程序 | InstallAssistant 和 springboard 均只有 arm64 |
| 实际内核 | 14 份全部解封装并识别；13 份 arm64e、1 份 arm64，无 x86_64 |
| 内核版本字串 | 所查内核均为 `Darwin Kernel Version 27.2.0` |
| 候选 arm64e 导入名 | 463 个；461 个名字见于所查集合，2 个未找到 |
| 候选声明的依赖 | 8 项中 7 项列于所查集合；1 项尚未确认 |
| 检查工具 | 31 项合成输入测试通过；回环 HTTP 只读镜像挂载测试通过 |
| 实机启动、驱动加载与联网 | 未执行 |

## 安装包完整性差异

目录中的 `Digest` 为 `33d474b5f2819530c7c730f881cd1089b027b913`。
本地整包 SHA-1 为 `62b59f9382927e2b3a15079dbec7c6b58468c49c`。
直接读取合并文件和按原下载分段重算，得到相同的完整文件摘要；随后 Apple 的 1699 个分块全部匹配，没有发现需重下的坏块。

本地整包 SHA-256：

```text
26bee623af06bf6c78a57e62ea6f188e678b841d9d30f25415fe73cf8444183a
```

签名链为 `Software Update → Apple Software Update Certification Authority → Apple Root CA`。
完整性判据采用 Apple HTTPS 固定的 CNKL SHA-256 分块和独立的系统 Apple 包签名验证，同时保留目录 SHA-1 不一致。
本次未确定该字段不一致的具体原因。[ipsw 作者的下载文档](https://blacktop.github.io/ipsw/docs/guides/download/)也记录过部分安装器目录 SHA-1 不正确的情况；该历史说明不能代替本次实测。

CNKL method 2 的末尾是无密钥 SHA-256 校验值，不能将其称为证书签名。
本次 CNKL 经 Apple HTTPS 取得并固定 SHA-256；Apple 包证书信任由 `pkgutil` 独立检查。
固定来源、实际摘要及完整签名输出见 [target.json](../evidence/2026-11-01/target.json)、[分块结果](../evidence/2026-11-01/chunk-validation.json)和[签名记录](../evidence/2026-11-01/package-signature.txt)。

## 实际架构

从验证后的 XAR 安装包只读提供 SharedSupport 的字节范围，再用系统 DiskImages 挂载，避免复制第二份大镜像。
父安装包已完成分块与签名验证；挂载时使用 `-noverify`，未重复执行 UDIF 整盘校验，不将该项写为通过。
没有执行安装器或安装包脚本。

在内部 MobileAsset ZIP 中核对真实 `AssetData/boot/SystemVersion.plist` 为 `27.2 / 26B123`，随后读取全部 14 个 kernelcache entry。
ZIP 成员经标准库 CRC 检查，IM4P 解封装、LZFSE 解压后再识别 Mach-O 头，不以文件名推断 CPU。
`mac18g` 为 arm64，其余 13 份为 arm64e；没有 x86_64 entry。

这些是本次实际载荷的结果，不代表未来第三方移植系统的架构。
详细的输入、输出哈希及 Darwin 字串见 [内核记录](../evidence/2026-11-01/kernel-architectures.json)。

## 候选驱动与具体阻碍

候选二进制 SHA-256 为 `c2639077ffe5f491e5624782bd59fbc916730fb0c4515b2b5cee004073a40841`，与原项目固定来源一致。
包含 x86_64 和 arm64e；`Info.plist` 已有 `pci8086,15f3` 匹配项。
这没有证明 27 上的硬件绑定或速率，也没有证明需要改动 PCI 匹配表。

静态集合检查选用实际 `kernelcache.release.mac14j`，显式排除主机 System / Aux collections。
`kmutil inspect` 列出该目标集合的 374 个 bundle；`nm` 读出 166,211 个定义的全局名字。

I210 arm64e 的 463 个导入名中，有两个在该集合中未找到：

```text
__ZN19IONetworkController29_RESERVEDIONetworkController6Ev
__ZN19IONetworkController29_RESERVEDIONetworkController7Ev
```

`com.apple.iokit.IOEthernetAVBController >= 1.0.3b2` 也未在该集合的 prelink 清单中列出。
其余 7 项声明依赖在该集合中可见，所列版本满足候选最低版本。

这份结果只覆盖 mac14j boot collection。完整目标系统的其他集合和可加载驱动尚未全部展开，不能把“此处未找到”写成“整个系统绝对不存在”。
461 个同名定义也不能证明它们可供新 kext 链接，更不能证明 C++ vtable、类布局和生命周期兼容。
本次状态为 `STATIC_INCOMPLETE`，未编造空壳函数或删除依赖来让检查器显示通过。

原始候选清单见 [candidate.json](../evidence/2026-11-01/candidate.json)，可复跑的集合结果见 [collection-audit.json](../evidence/2026-11-01/collection-audit.json)。

## 后续工作

Intel 路线首先需要可运行的 x86_64 目标系统；当前这份 Apple ARM 安装器不能提供它。
之后若有新的目标系统输入，应重新检查其架构、内核版本、集合和系统组件，而不是继承本报告。

ARM 路线需继续定位上述两个导入名的接口变化，核对 IOEthernetAVBController 的完整系统提供者及 ABI。
现有 Apple 驱动没有实现源码；同名占位函数或单纯修改 plist 不能证明修复成立。
目标系统能够启动并具备 I225 硬件后，再验证加载、绑定、DHCP、传输完整性、网线拔插、重启和睡眠恢复。

本次未改动正在使用的 EFI、系统驱动、安全设置或原 Tahoe 仓库。
安装器及内核载荷保留本地；GitHub 仅保存原创工具、说明和派生检查记录。
