# Deployment target

Inspected through authenticated SSH at 192.168.1.97 on 2026-10-25.

- Existing OS: ZimaOS 1.8.0, Linux 6.18.9, x86-64, UEFI boot.
- CPU: Intel Core i5-12500, 6 cores / 12 threads.
- RAM: approximately 12 GB installed, 11 GiB reported usable.
- Boot SSD: 1 TB SPCC SATA SSD, SMART overall assessment passed.
- Data drives: four 1 TB SATA hard drives.
- Existing array: MD RAID5 with Btrfs, degraded (3 of 4 members active) and recovering.
- WD-WCC3F0YAV0YU (then `/dev/sdd`) reported repeated unrecoverable media errors and was removed from the running kernel to stop stalled I/O.
- WD-WCC3F0RSA3AX (then `/dev/sde`) reported an offline uncorrectable sector and historical uncorrectable errors. It is also excluded.
- Docker 27.5.1 and QEMU 10.2.0 with `/dev/kvm` are available.

The user has confirmed that none of the existing NAS data needs to be retained.

## Deployment layout

Build workspace: `/DATA/harbor` on the boot SSD. The bare-metal installation uses a root directory at `/DATA/harbor/rootfs` with a custom initramfs hook, preserving the original boot files as a recovery option.

The broken MD array was removed after the user declared its data disposable. ST1000DM010 ZN16ST2R and WD-WCC3F2UPCNDD now form a two-device Btrfs RAID1 volume, with mirrored data and metadata and about 930.5 GiB available. The filesystem UUID is `0b36d0af-b975-4408-8f7b-a45fd6a1b7d1`.

The assessment used SMART attributes and kernel error reports; no complete surface burn-in test has been performed.

The independent disk image uses a conventional GPT layout with BIOS boot, EFI system, and ext4 root partitions. It does not require the directory-root hook.

The NAS password must never be added to source, documentation, image build logs, or Git history. Personalized account provisioning receives it through an SSH channel on stdin. The app stores only a salted scrypt hash.
