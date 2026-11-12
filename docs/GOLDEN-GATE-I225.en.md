# Intel I225-V Ethernet on macOS 27.2 Golden Gate

[简体中文](GOLDEN-GATE-I225.zh-CN.md) | [English](GOLDEN-GATE-I225.en.md)

On an i7-12700K / Z690 host, Intel I225-V (PCI `8086:15f3`) has run on Golden Gate with AppleIntelI210Ethernet 2.3.1. On two boots, the NIC was detected, negotiated a 1000baseT full-duplex link, and reached the gateway. A packet capture on the second boot recorded a DHCP Request and ACK in the same transaction; the user also confirmed that internet access worked.

| Item | Tested scope |
| --- | --- |
| System | Liberator Beta 1 / Golden Gate, macOS 27.2 `26B123`, Darwin `27.2.0`, x86_64 |
| Bootloader | OpenCore 1.0.8; macOS 26 and 27 share one active EFI |
| NIC | Intel I225-V `8086:15f3`, using the existing I210 device properties |
| Driver | x86_64 slice of AppleIntelI210Ethernet 2.3.1 |
| Runtime evidence | The IOService tree on both boots showed `AppleIntelI210 → en0`; the record includes a gigabit link, default route, and gateway response. The second boot captured the DHCP Request / ACK for the renewed address. |
| Not yet tested | A separately collected external-connectivity probe for 27, sustained throughput, sleep/wake, 2.5GbE, and other motherboards or I226 |

Golden Gate uses an Intel kernel collection built from the KDK for the same system build. This guide assumes that the target already boots to the desktop. Research notes about Apple's original arm64e installer payload apply to a different set of inputs. [Liberator Beta 1](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v3.0.0-beta.1)

## 1. Back up the EFI and existing driver

Check the GPT partition UUID of the boot partition. Back up the current `EFI/OC/config.plist`, the original I210 kext, and the existing `EFI/OC-26`, or keep an independent, bootable macOS 26 medium. If E1000 was manually modified on 27, back up the 27 DEXT as well. Prepare and validate the changes on an EFI copy.

The universal binary was confirmed to contain `x86_64` and `arm64e`; this procedure uses only x86_64. The source binary's SHA-256 is:

```text
c2639077ffe5f491e5624782bd59fbc916730fb0c4515b2b5cee004073a40841
```

The source and release package were both verified at the kext path `Contents/MacOS/AppleIntelI210Ethernet`. [macOS 26 I210 baseline release](https://github.com/GeekAudio/intel-i210-i225-ethernet/releases/tag/v1.0.2)

## 2. Prepare a kext for 27 only

Extract the [v0.1.2 release package](https://github.com/GeekAudio/intel-i225-macos27-compat/releases/tag/v0.1.2) and use `Kexts/AppleIntelI210Ethernet-27.kext` from it. Alternatively, generate it from the original driver at the root of this repository; point `--kext` to the original kext in the Tahoe v1.0.2 release package.

```sh
mkdir -p work/kexts
python3 tools/prepare_i210_27.py \
  --kext /path/to/AppleIntelI210Ethernet.kext --output-dir work/kexts
```

The target 27 x86_64 kernel collection lacks the older `IOEthernetAVBController` bundle. I210 does not directly reference that controller class, and the relevant `IOEthernetController` methods it needs remain in the collection. Keep the other dependencies. Editing `Info.plist` changes a resource covered by Apple's original signature; this procedure uses the OpenCore injection path already present in Golden Gate. The I210 machine code, C++ symbols, and vtable were not changed in this work.

## 3. Configure OpenCore

Place the prepared kext in `OC/Kexts` in the EFI copy. Add the dictionary from [`Kernel-Add-27.plist`](../opencore/Kernel-Add-27.plist) under `Kernel → Add`. If an I210 entry for macOS 26 already exists, keep it, set its `MaxKernel` to `26.99.99` if it is empty or higher than `26.99.99`, and place the 27 entry after it.

| Field | Value |
| --- | --- |
| `BundlePath` | `AppleIntelI210Ethernet-27.kext` |
| `ExecutablePath` | `Contents/MacOS/AppleIntelI210Ethernet` |
| `PlistPath` | `Contents/Info.plist` |
| `Arch` | `x86_64` |
| `Enabled` | `true` |
| `MinKernel` | `27.2.0` |
| `MaxKernel` | `27.2.0` |

Merge the two properties from [`I225-DeviceProperties.plist`](../opencore/I225-DeviceProperties.plist) into the I225 node under `DeviceProperties → Add`. The measured values are Data type `device-id = 33150000` (little-endian `0x1533`) and `built-in = 01`. The PCI path varies by motherboard and firmware.

Compare the PCI parent chain for the I225 in the original EFI or IORegistryExplorer to confirm the path. The measured host used `PciRoot(0x0)/Pci(0x1C,0x2)/Pci(0x0,0x0)`; this value is for comparison only.

In `NVRAM → Add → 7C436110-AB2A-4BBB-A880-FE41995C9F82 → boot-args`, preserve the existing arguments and ensure that `e1000` appears exactly once as `e1000=0`. Keep the other entries in the array under `NVRAM → Delete → 7C436110-AB2A-4BBB-A880-FE41995C9F82` and add `boot-args`. OpenCore deletes the old variable first, then writes the complete new value. [OpenCore 1.0.8 configuration documentation](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Docs/Configuration.tex)

If the original EFI also configures AppleIGC or another driver for this card, limit those entries' Darwin version range so they skip 27.2.0. If another system using the shared boot setup depends on E1000, use a separate boot configuration for 27. A machine whose E1000 probe has not been modified can proceed directly to boot verification.

### If E1000 was modified to ignore `e1000=0`

First restore the probe check from a verified backup made from the same build and target volume. If the current file is the project's previously tested x86_64 EEE-off version (SHA-256 `ed2f60274dc16a8078532e22ff06df7285e55c1e4269014248a3e4ad6190d9ee`), the release package's `tools/restore_e1000_probe.py` can reproduce the tested fix on a DEXT copy. The tool stops for any other hash.

```sh
SYS='/Volumes/macOS 27' # First confirm the target by volume UUID and SystemVersion.plist
NAME=com.apple.DriverKit-AppleEthernetE1000
WORK=$(mktemp -d)
cp -RX "$SYS/System/Library/DriverExtensions/$NAME.dext" "$WORK/"
python3 tools/restore_e1000_probe.py \
  --input "$WORK/$NAME.dext/$NAME" --output "$WORK/$NAME.restored" &&
  mv "$WORK/$NAME.restored" "$WORK/$NAME.dext/$NAME" &&
  codesign --verify --strict "$WORK/$NAME.dext"
```

After signature verification succeeds, back up the original binary on 27 and replace only the restored executable on the confirmed 27 volume. Preserve `root:wheel`, `0755`, `restricted`, and the original `Info.plist`. Remount it as before and recheck the signature and SHA-256 `62e312646fe8d59682be94fb3bbf9a8019ac421db5c9718205efc2d9bbc02c38`.

## 4. Verify, boot, and roll back

1. Check the EFI copy with `ocvalidate` from the same version. Review the configuration diff and every referenced file. Confirm that the original macOS 26 entry still applies and that 27 selects only the new I210 entry.
2. OpenCore 1.0.8's `ProcessKernel` was run offline against two real BootKCs. The 27 output contained the added I210 fileset; 26 still injected the old I210 and skipped the new entry according to its Darwin version. The tool does not support `Kernel → Force`, so that array was cleared only in test copies; retain the existing `Force` in the deployment. [OpenCore 1.0.8 ProcessKernel source](https://github.com/acidanthera/OpenCorePkg/blob/1.0.8/Utilities/TestProcessKernel/ProcessKernel.c)
3. After confirming that the backup is usable, write the validated configuration and new kext to the target ESP. Sync, unmount, remount read-only, and compare SHA-256. Boot 27 and use the commands below to check the driver, link, lease, and connectivity separately. The example interface is `en0`; use the actual interface on your machine.

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

In the I/O Registry, confirm that the target Ethernet interface is beneath `AppleIntelI210`. Seeing the driver in the `kmutil` list only means that it loaded. To determine whether DHCP occurred during this boot, use `tcpdump` to compare the transaction ID in the Request and ACK; do not mistake a cached lease for a new response. Turning off EEE, switching to software checksums, and reducing the E1000 link to 100 Mbps did not restore networking on this machine.

To roll back, boot macOS 26 from a known-good boot option, restore the active EFI configuration from before the change, and then remove the added `AppleIntelI210Ethernet-27.kext`. If E1000 on 27 was modified for this procedure, restore the corresponding file on the 27 volume from the backup. Remount, verify, and then boot the target system.
