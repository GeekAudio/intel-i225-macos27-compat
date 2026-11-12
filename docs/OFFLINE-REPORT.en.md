# macOS 27.2 / I225-V offline inspection

[简体中文](OFFLINE-REPORT.zh-CN.md) | [English](OFFLINE-REPORT.en.md)

> This document preserves the offline research record from 2026-11-01. For the Golden Gate x86_64 method and tested scope recorded on 2026-11-12, see the [I225-V guide](GOLDEN-GATE-I225.en.md).

Date: 2026-11-01. Target: Apple's public production release of macOS 27.2, build `26B123`, Software Update product `142-50055`.
Candidate: AppleIntelI210Ethernet 2.3.1 from the original Tahoe project; target hardware ID `8086:15f3`.

## Conclusion

This inspection completed a full installer download, independent integrity checks, architecture checks of 14 actual kernels, and dependency and symbol checks for one boot collection.
**The current Apple installer payload contains no x86_64 kernel, so this Intel Hackintosh cannot be upgraded to that system by changing NIC configuration alone.**
The I210 arm64e route also has not passed its static prerequisites and cannot be released as a compatible driver.

| Check | Actual result |
| --- | --- |
| Full installer package | 17,807,147,403 bytes, retained locally |
| Catalog `Digest` / whole-package SHA-1 | Do not match; discrepancy recorded |
| Apple CNKL chunks | SHA-256 matched for all 1699 / 1699 chunks; method-2 trailer SHA-256 matched |
| Apple package signature | `pkgutil` exited 0, status `signed Apple Software` |
| Installer applications | InstallAssistant and springboard are arm64 only |
| Actual kernels | All 14 were unpacked and identified; 13 arm64e, 1 arm64, none x86_64 |
| Kernel version string | Every inspected kernel reported `Darwin Kernel Version 27.2.0` |
| Candidate arm64e imported names | 463 total; 461 names found in the inspected collection, 2 not found |
| Candidate declared dependencies | 7 of 8 listed in the inspected collection; 1 not confirmed |
| Inspection tools | 31 synthetic-input tests passed; loopback HTTP and read-only image-mount tests passed |
| Real-machine boot, driver loading, and networking | Not performed |

## Installer integrity discrepancy

The catalog's `Digest` is `33d474b5f2819530c7c730f881cd1089b027b913`.
The local whole-package SHA-1 is `62b59f9382927e2b3a15079dbec7c6b58468c49c`.
Recomputing from the merged file and from the original download segments produced the same whole-file digest; all 1699 Apple chunks then matched, with no bad chunk requiring a re-download.

Local whole-package SHA-256:

```text
26bee623af06bf6c78a57e62ea6f188e678b841d9d30f25415fe73cf8444183a
```

The signature chain was `Software Update → Apple Software Update Certification Authority → Apple Root CA`.
The integrity basis used Apple's CNKL SHA-256 chunks pinned over HTTPS and independent verification of the system Apple package signature, while retaining the catalog SHA-1 mismatch.
The specific cause of this field's mismatch was not determined in this inspection. The [ipsw author's download documentation](https://blacktop.github.io/ipsw/docs/guides/download/) has also recorded cases where an installer catalog SHA-1 was incorrect; that historical note is not a substitute for the measurements in this inspection.

The CNKL method-2 trailer is an unkeyed SHA-256 checksum; it must not be described as a certificate signature.
This CNKL was obtained over Apple HTTPS and its SHA-256 was pinned; Apple's package-certificate trust was checked separately with `pkgutil`.
Pinned source, measured digests, and complete signature output are in [target.json](../evidence/2026-11-01/target.json), [chunk results](../evidence/2026-11-01/chunk-validation.json), and [signature record](../evidence/2026-11-01/package-signature.txt).

## Actual architecture

The SharedSupport byte range was served read-only from the verified XAR installer package and mounted with the system DiskImages tooling, avoiding a second copy of the large image.
The parent installer package had passed chunk and signature verification; `-noverify` was used for the mount, so a second full UDIF verification was not performed and is not recorded as passed.
No installer application or package script was executed.

Within the MobileAsset ZIP, the actual `AssetData/boot/SystemVersion.plist` was checked for `27.2 / 26B123`, then all 14 kernelcache entries were read.
ZIP members were CRC-checked by the standard library, IM4P was unpacked, LZFSE was decompressed, and the Mach-O headers were identified; CPU type was not inferred from filenames.
`mac18g` was arm64 and the other 13 were arm64e; there was no x86_64 entry.

These results describe the payload actually inspected and do not establish the architecture of any future third-party port.
See the [kernel record](../evidence/2026-11-01/kernel-architectures.json) for detailed input and output hashes and Darwin version strings.

## Candidate driver and specific blockers

The candidate binary's SHA-256 is `c2639077ffe5f491e5624782bd59fbc916730fb0c4515b2b5cee004073a40841`, matching the fixed source from the original project.
It contains x86_64 and arm64e slices; `Info.plist` already has a `pci8086,15f3` match entry.
This does not prove hardware binding or link speed on 27, nor does it prove that the PCI match table needs modification.

The static collection check used the actual `kernelcache.release.mac14j`, explicitly excluding the host System / Aux collections.
`kmutil inspect` listed 374 bundles in that target collection; `nm` read 166,211 defined global names.

Two of the I210 arm64e slice's 463 imported names were not found in that collection:

```text
__ZN19IONetworkController29_RESERVEDIONetworkController6Ev
__ZN19IONetworkController29_RESERVEDIONetworkController7Ev
```

`com.apple.iokit.IOEthernetAVBController >= 1.0.3b2` was also not listed in that collection's prelink manifest.
The other 7 declared dependencies were visible in the collection, and their listed versions met the candidate's minimum versions.

This result covers only the mac14j boot collection. The other collections in the complete target system and all loadable drivers were not fully expanded, so “not found here” must not be reported as “definitely absent from the entire system.”
The 461 matching symbol names also do not prove that they are linkable by a new kext, or that the C++ vtable, class layout, and lifecycle are compatible.
The status for this inspection was `STATIC_INCOMPLETE`; no stub functions were fabricated and no dependencies were deleted merely to make the checker report a pass.

The original candidate inventory is in [candidate.json](../evidence/2026-11-01/candidate.json); reproducible collection results are in [collection-audit.json](../evidence/2026-11-01/collection-audit.json).

## Next steps

The Intel route first requires a runnable x86_64 target system; this Apple ARM installer cannot provide one.
If a new target-system input becomes available, inspect its architecture, kernel version, collections, and system components again instead of inheriting this report's conclusions.

The ARM route needs further investigation of the interface changes behind the two imported names above, plus the complete system provider for IOEthernetAVBController and ABI compatibility.
The existing Apple driver has no implementation source. A same-named stub function or a plist-only change would not demonstrate a valid fix.
Only after the target system boots and has I225 hardware should you test loading, binding, DHCP, transfer integrity, cable unplug/reconnect, reboot, and sleep/wake.

This inspection did not modify the active EFI, system drivers, security settings, or the original Tahoe repository.
The installer and kernel payload remain local; GitHub contains only original tools, documentation, and derived inspection records.
