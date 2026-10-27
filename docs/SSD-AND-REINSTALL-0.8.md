# System SSD files, sharper visuals and fresh installation — 0.8.0

## System SSD

Open **Files → Storage → System SSD**. Create folders or import files immediately. The dedicated data directory is `/srv/harbor/system-data/shares/Files`; operating-system files are not exposed. It is owner-only in the web interface and is not automatically exported over SMB. Your data pool remains a separate location. Browser back/forward and the recycle bin retain the selected drive. Copy/move stays within one drive; download/import to transfer between drives.

The SSD is not protected by your data-pool RAID. Harbour reserves 5% of the system filesystem, bounded between 2 and 16 GiB, for OS operation. Imports and copies check available space before writing. A fresh system installation erases these SSD files along with accounts, applications and settings.

The visual refinement uses native system text rendering, clearer label sizes and weights, stronger secondary-text contrast, and more defined vector icons in both themes. Green accents and the existing desktop layout are retained.

## Reinstall without a USB installer

A fresh OS image is required, but Harbour downloads and stages it internally: you do not need to manually download an ISO, make a USB stick, or boot external media.

1. Back up anything you want to keep, including System SSD files. Have a monitor and keyboard connected to the NAS, or equivalent remote KVM access.
2. Open **Settings → Reinstall → Download & prepare**. Harbour downloads the signed recovery manifest and image for its installed version, verifies the Ed25519 signature, size and SHA-256, then stages a recovery entry. The current system keeps running. This does not erase a disk or select recovery for the next boot yet.
3. Choose **Boot recovery**, acknowledge local screen access and type `BOOT RECOVERY`. Harbour rechecks the staged image, selects a one-time GRUB entry and restarts. Apps, networking services and SMB are interrupted by the restart.
4. The full live installer is copied into RAM, releasing the system SSD. On the NAS's local graphical screen, select the system SSD and confirm its erase. The installer also checks that its recovery source is on tmpfs before it can erase a disk.
5. After installation, create a new owner account on the graphical setup screen. Use **Storage → Create storage** to create your new pool, selecting its disks and confirming `ERASE <pool name>` separately. Creating a new pool destroys the previous contents of those selected disks. Existing pool disks are not erased merely by preparing or booting recovery, or by installing onto a different system disk.

If you cancel before installation, reboot normally to return to the existing OS. The recovery selection is used once. Standard Harbour ext4 installations with `/boot` on the root filesystem are supported. Patch 0.8.1 also recognizes the earlier ZimaOS-to-Harbour conversion with `/harbor/rootfs` and its EFI boot configuration; it retains the existing Harbour/Zima default and fallback policy and uses a separate one-time recovery flag. A fresh whole-system-SSD install also removes the previous ZimaOS installation on that SSD. Encryption, separate/custom boot layouts and insufficient RAM require another installation method. Harbour requires RAM of at least twice the compressed ISO size plus 2 GiB. A failed system disk still needs external recovery media.

## Release signing and validation

`tools/sign-recovery.py` signs `harbour-recovery.json` locally using the existing release key, after the ISO's BIOS/UEFI test report is published. Attach that signed metadata to the same release. The private key is never uploaded to GitHub or included in an image. Recovery preparation stays unavailable until this asset exists and verifies.

The disposable VM test staged a signed 0.7.0 prototype image, booted it from the system disk entirely into RAM with no attached ISO/USB, reinstalled the virtual system disk, and verified a fresh graphical owner-setup boot and unchanged separate pool data hash. Recovery staging and boot selection ran under the management service's security restrictions. The 0.8.0 ISO includes the same recovery path and an additional RAM-source guard. See `recovery-validation-0.8.0.json`; the release ISO is separately boot-tested in BIOS and UEFI.

Automated tests cover signature tampering, download-host/size limits, repeated boot-entry generation, explicit boot confirmation, SSD namespace confinement, member-access denial and OS-space reservation. Browser tests verified actual SSD folder creation and uploaded bytes in both themes. Physical pool disks were not changed, and the physical NAS was not rebooted or reinstalled during development.

References: [Debian live-boot](https://manpages.debian.org/trixie/live-boot-doc/live-boot.7.en.html), [GRUB one-time boot](https://www.gnu.org/software/grub/manual/grub/html_node/next_005fentry.html).
