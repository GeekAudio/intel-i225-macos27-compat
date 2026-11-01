# 下一阶段的适配条件

本项目的目标芯片是 I225-V `8086:15f3`，基线是旧 Apple I210 2.3.1。
每个阶段分别记录来源、输入哈希、检查命令、检查结果及未解决项，不把前一阶段通过写成后一阶段成功。

## 1. 固定目标系统

使用 `apple_installer.py discover` 从 Apple 的公开正式版清单选择目标，再下载完整安装包。
保存 macOS 版本、build、产品编号、Apple URL、目录摘要、本地 SHA-256 和包签名结果。
目标 build 更新后重新检查，不能直接继承旧 build 的结论。

## 2. 先解决目标架构

对于 Z690 / i7-12700K 这类 Intel 平台，需要实际可运行的 x86_64 目标内核、启动链及系统组件。
Apple 提供的 ARM 系统内核不能通过修改 OpenCore 的 SMBIOS、驱动 `Arch` 或 `MinKernel / MaxKernel` 变成 x86_64。

如果之后提供第三方移植的 Intel 系统，应单独记录该系统的来源和修改内容，再扫描其真实内核和网络组件。
那会是另一组输入，不能使用当前 Apple ARM 载荷的结果替代。

对于 Apple 芯片平台，需要真实可枚举的 I225 PCIe 设备及该平台的加载条件。
基线驱动存在 arm64e slice，只能证明有该架构的机器码；它不能证明可加载、能绑定 I225 或能够稳定传输。

## 3. 核对依赖与接口

从目标系统或目标内核集合中查找这些依赖的实际版本、架构、导出符号和相关类接口：

- `com.apple.driver.mDNSOffloadUserClient`
- `com.apple.iokit.IOEthernetAVBController`
- `com.apple.iokit.IONetworkingFamily`
- `com.apple.iokit.IOPCIFamily`
- `com.apple.kpi.bsd / iokit / libkern / mach`

候选的具体最低版本和全部未定义符号见 `evidence/2026-11-01/candidate.json`。
某个符号名存在，也不能证明 C++ vtable、对象布局、调用约定和生命周期仍兼容。
如果输入是压缩内核，先用 `unpack_kernel.py` 解封装，再用目标架构的静态工具检查。
如果内容加密、无法解码或不在扫描范围内，保留未解决项，不将其认定为缺失。

现有仓库没有 Apple 驱动的实现源码。发生 ABI 不兼容时，不能假设只改 Info.plist 就能修复。
需要先得到可核验的故障和具体接口差异，再选择可获得源码的驱动实现或新的驱动开发路线。

## 4. 运行验收

只有目标系统能够启动且具备目标网卡后，才进行以下验证：

1. 确认实际绑定的驱动、版本、PCI ID 和网络接口，排除同一卡的多驱动竞争。
2. 检查 IPv4 / IPv6、DHCP、DNS、默认路由和实际联网。
3. 记录协商速率，并独立进行局域网持续双向传输与完整性检查。
4. 验证拔插网线、重新协商、重启及多次睡眠唤醒。
5. 检查 panic、驱动退出、内存异常和链路恢复；保留可复现的日志与回退路径。

这些运行项本次均未执行。Tahoe 上的 1000baseT 记录不证明 27 上的速率、吞吐或长期稳定性。
