# ISO builds and downloads

Download `harbour-VERSION-amd64.iso` and its `.iso.sha256` file from [GitHub Releases](https://github.com/rico-242/HarborOS/releases). Public release downloads do not require sign-in. Write the ISO to a USB drive in raw/DD mode, then boot using legacy BIOS or UEFI. Secure Boot is not supported. Use at least 4 GB RAM and a separate 16 GiB system disk. Installation requires explicitly confirming erasure of the selected destination.

## Every build

The `Build and publish ISO` workflow runs for every push to main, every `v*` version tag, and every published release. Main builds retain the ISO, checksum, and validation report as Actions artifacts for 14 days. GitHub requires sign-in for Actions artifacts; the release copies remain publicly downloadable without authentication.

Version tags and releases publish the ISO after clean-root construction and successful BIOS and UEFI boot tests. A tag must match `VERSION` in `harbor/server.py`. Keep the installer versions aligned when preparing a new version. A manual workflow run can attach the current version to its existing release. Existing complete ISO asset sets are retained on repeated events, and assets are never silently overwritten.

Each ISO contains a clean Debian 13 root, the graphical installer, the current Harbour application and catalog, and the public key used for signed in-place updates. It contains no owner account, private signing key, personalized SSH identity, or GitHub token. The workflow needs no private signing key. Signed `.harbour-update` releases remain a separate artifact and are still the normal upgrade path for existing installations.

The automated smoke test boots the ISO as read-only USB media, without destination disks, in separate BIOS and UEFI VMs. It checks service and installer versions, fresh owner state, graphical services, new UI assets, and the pinned public update key. This is a boot/readiness check, not a new destructive installation test on physical hardware.

## Local Linux build

On an amd64 Debian/Ubuntu builder install `debootstrap rsync squashfs-tools grub-pc-bin grub-efi-amd64-bin grub2-common xorriso mtools dosfstools qemu-system-x86 ovmf`. In a trusted build environment run:

```sh
sudo env HARBOR_ISO_WORK=/absolute/new/harbour-build HARBOR_ARTIFACTS="$PWD/dist" bash tools/build-release-iso.sh
sudo python3 tools/test-release-iso.py dist/harbour-0.5.0-amd64.iso --output dist/iso-validation.json
(cd dist && sha256sum -c harbour-0.5.0-amd64.iso.sha256)
```

The build directory must be new. Scripts install packages inside the isolated root and temporarily mount pseudo-filesystems there. They do not partition physical disks. A hosted runner or disposable Linux builder is recommended. Debian packages are fetched from signed repositories at build time, so repeated builds need not have identical bytes.
