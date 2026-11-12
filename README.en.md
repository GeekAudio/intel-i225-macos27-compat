# Intel I225-V networking on macOS 27.2 Golden Gate

[简体中文](README.md) | [English](README.en.md)

This guide applies to an **already bootable macOS 27.2 `26B123` Golden Gate (x86_64)** system with an Intel I225-V (`8086:15f3`).

## Download

Download the [driver ZIP](https://github.com/GeekAudio/intel-i225-macos27-compat/releases/download/v0.1.2/I225-V-GoldenGate-26B123-v0.1.2.zip) and its [SHA-256 checksum file](https://github.com/GeekAudio/intel-i225-macos27-compat/releases/download/v0.1.2/I225-V-GoldenGate-26B123-v0.1.2.zip.sha256). Verify and extract them in the same directory.

```sh
shasum -a 256 -c I225-V-GoldenGate-26B123-v0.1.2.zip.sha256 &&
  unzip I225-V-GoldenGate-26B123-v0.1.2.zip
```

## Configure OpenCore

1. Back up `EFI/OC/config.plist` and the existing driver. For a dual-boot setup, keep `EFI/OC-26` or an independent boot option for macOS 26.
2. Copy `Kexts/AppleIntelI210Ethernet-27.kext` from the downloaded archive to `EFI/OC/Kexts`. Add the dictionary from [Kernel-Add-27.plist](opencore/Kernel-Add-27.plist) as a new entry under `Kernel → Add`; set both `MinKernel` and `MaxKernel` to `27.2.0`. If an I210 entry for macOS 26 already exists, keep it and set its `MaxKernel` to `26.99.99` if it is empty or higher than `26.99.99`.
3. Under `DeviceProperties → Add`, find the **PCI path of the I225 in your machine** and merge the two Data values from [I225-DeviceProperties.plist](opencore/I225-DeviceProperties.plist): `device-id = 33150000` and `built-in = 01`.
4. In `NVRAM → Add → 7C436110-AB2A-4BBB-A880-FE41995C9F82 → boot-args`, keep the existing arguments and set `e1000` to `e1000=0`. List `boot-args` in the same GUID array under `NVRAM → Delete` so the new value replaces the old one. Make sure drivers such as AppleIGC for the same card do not load on 27.2. If another OS in a shared EFI depends on E1000, use a separate boot configuration for 27. If you previously modified the 27 E1000 probe so it ignores this argument, restore and check it first. See [the E1000 restoration steps](docs/GOLDEN-GATE-I225.en.md).
5. Validate the configuration with `ocvalidate` from the same OpenCore version. After confirming that the configuration references and kext paths match, write it to the target EFI, sync, remount read-only, and read it back for verification.

## Boot verification and rollback

After booting into 27, run the commands below. If the Ethernet interface is not `en0`, replace it with the interface used on your machine.

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

To roll back, boot macOS 26 from a known-good boot option, restore the backed-up active EFI configuration, and then remove `AppleIntelI210Ethernet-27.kext`. If you modified E1000 on 27, restore its original binary from the backup.

For the commands to generate a kext from the original I210 driver and the full procedure, see the [driver guide](docs/GOLDEN-GATE-I225.en.md).

## Documentation

- [Golden Gate I225-V guide](docs/GOLDEN-GATE-I225.en.md)
- [Next-stage adaptation criteria](docs/NEXT-STEPS.en.md)
- [Offline inspection report](docs/OFFLINE-REPORT.en.md)
