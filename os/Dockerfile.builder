FROM debian:trixie-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends debootstrap ca-certificates rsync e2fsprogs dosfstools fdisk parted grub-efi-amd64-bin grub-pc-bin grub2-common xorriso mtools zstd && rm -rf /var/lib/apt/lists/*
COPY os/build-rootfs.sh /build-rootfs.sh
ENTRYPOINT ["/bin/bash", "/build-rootfs.sh"]
