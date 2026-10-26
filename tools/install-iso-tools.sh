set -eu
resolvectl dns eth0 192.168.1.254
resolvectl flush-caches
getent ahostsv4 deb.debian.org | head -2
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils ovmf xorriso squashfs-tools grub-pc-bin grub-efi-amd64-bin grub2-common mtools live-boot live-boot-initramfs-tools python3-yaml docker-compose zstd
