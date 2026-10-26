# Harbor OS 0.2.0 live installer

Use `dist/harbor-0.2.0-amd64.iso` on an x86-64 PC with at least 4 GB RAM, wired Ethernet, and a system disk of at least 16 GiB. Keep data disks separate from the system disk. UEFI and legacy BIOS are supported. This unsigned development ISO requires Secure Boot to be disabled.

1. Verify the ISO against its adjacent SHA-256 file.
2. Write the ISO to a USB stick using a raw/DD image-writing mode, or attach it as a virtual CD in a VM. Writing the USB erases that USB stick.
3. Boot the USB. Choose **Try Harbor OS** to preview in RAM, or **Install Harbor OS** to start the guided console installer.
4. Review the destination model, serial number, capacity, and stable disk ID. The installer excludes mounted disks, its live medium, and disks smaller than 16 GiB. It erases only the selected destination after you type `ERASE <serial>`.
5. When installation completes, shut down, remove the USB, and boot the installed disk. Installation works offline.
6. The local console displays an HTTPS address, setup code, TLS certificate fingerprint, and SSH host-key fingerprint. Open the displayed HTTPS address from another computer. Verify the certificate against the local console before trusting the browser's certificate warning.
7. Create your administrator account using the setup code. No administrator password is embedded in the ISO. Live-preview accounts and credentials are not copied to the installed system.
8. Open **Settings → Storage → Create storage**. Choose **Combine** for RAID/JBOD or **Enable** for one disk, select disks, name the storage space, and review the final erasure confirmation.

The storage wizard creates a primary Btrfs data filesystem. RAID 0, 1, 5, 6, and 10 use Linux MD beneath Btrfs. JBOD combines capacity using Btrfs's single-data profile because this kernel no longer has the MD linear driver. Existing primary storage, operating-system disks, mounted filesystems, active array members, and failing SMART disks are protected. A second primary pool, migration, online expansion, disk replacement, and RAID repair are not implemented in this release. RAID initialization can continue in the background; keep a separate backup.

The App Store contains a pinned snapshot of the official ZimaOS app definitions. It has featured apps, search, category and installed filters, descriptions, environment settings, and install/start/stop controls. App images download from their upstream registries, so application installation needs internet access. Apps may require additional hardware, their own account setup, or changed settings; catalog validation does not establish that every app works on every computer.

Live preview does not automatically install Harbor, mount a data pool, or format disks. Persistent app installation and pool creation are enabled after installation. The live rescue shell is available only on the local live console; installed systems do not retain root autologin.

This is an experimental NAS distribution. Test with disposable disks before storing important data.
