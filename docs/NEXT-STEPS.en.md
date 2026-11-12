# Requirements for the next adaptation stage

[简体中文](NEXT-STEPS.zh-CN.md) | [English](NEXT-STEPS.en.md)

> This document preserves the offline research record from 2026-11-01. For the Golden Gate x86_64 method and tested scope recorded on 2026-11-12, see the [I225-V guide](GOLDEN-GATE-I225.en.md).

The target chip for this project is I225-V `8086:15f3`, using the older Apple I210 2.3.1 driver as its baseline.
For each stage, record the source, input hashes, inspection commands, results, and unresolved items. Do not treat a pass at one stage as proof of success at a later stage.

## 1. Pin down the target system

Use `apple_installer.py discover` to select a target from Apple's public production-release catalog, then download the complete installer package.
Record the macOS version, build, product ID, Apple URL, catalog digest, local SHA-256, and package-signature result.
When the target build changes, inspect it again; do not carry forward conclusions from the previous build.

## 2. Resolve the target architecture first

Intel platforms such as Z690 / i7-12700K need an x86_64 target kernel, boot chain, and system components that can actually run.
An Apple ARM system kernel cannot be turned into x86_64 by changing the OpenCore SMBIOS, the driver's `Arch`, or `MinKernel / MaxKernel`.

If a third-party port of an Intel system becomes available, record that system's source and modifications separately, then inspect its actual kernel and networking components.
That would be a different set of inputs; results from the current Apple ARM payload cannot stand in for it.

On Apple silicon, there must be a real, enumerable I225 PCIe device and platform-specific conditions for loading the driver.
An arm64e slice in the baseline driver proves only that machine code for that architecture exists. It does not prove that the driver can load, bind to I225, or transfer data reliably.

## 3. Check dependencies and interfaces

From the target system or target kernel collection, inspect the actual versions, architectures, exported symbols, and relevant class interfaces for these dependencies:

- `com.apple.driver.mDNSOffloadUserClient`
- `com.apple.iokit.IOEthernetAVBController`
- `com.apple.iokit.IONetworkingFamily`
- `com.apple.iokit.IOPCIFamily`
- `com.apple.kpi.bsd / iokit / libkern / mach`

The candidate's specific minimum versions and all undefined symbols are listed in `evidence/2026-11-01/candidate.json`.
The existence of a symbol with a matching name does not prove that the C++ vtable, object layout, calling convention, or lifecycle remains compatible.
If the input is a compressed kernel, unpack it with `unpack_kernel.py`, then inspect it with static tools for the target architecture.
If content is encrypted, cannot be decoded, or is outside the scan scope, leave it unresolved; do not classify it as missing.

This repository does not contain the implementation source for Apple's driver. If there is an ABI incompatibility, do not assume that changing only `Info.plist` will fix it.
First obtain a verifiable failure and the specific interface difference, then choose an implementation whose source is available or a new driver-development approach.

## 4. Runtime acceptance

Only after the target system boots and has the target NIC should you perform these checks:

1. Confirm the driver actually bound, its version, PCI ID, and network interface; rule out multiple drivers competing for the same card.
2. Check IPv4 / IPv6, DHCP, DNS, the default route, and actual internet connectivity.
3. Record the negotiated speed, then separately test sustained bidirectional LAN transfers and data integrity.
4. Test unplugging and reconnecting the cable, link renegotiation, reboot, and multiple sleep/wake cycles.
5. Check for panics, driver exits, memory anomalies, and link recovery; preserve reproducible logs and a rollback path.

These runtime checks were not performed as part of the 2026-11-01 offline research recorded here. The earlier Tahoe 1000baseT record did not establish macOS 27 speed, throughput, or long-term stability. See the later guide above for the limited Golden Gate boot and link results.
