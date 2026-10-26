# Harbor OS 0.2.0 validation

Release artifact: `dist/harbor-0.2.0-amd64.iso`.

SHA-256: `1e4444a2070f2cd3e22b4579c7496a9c539ace466672380c5f87f8f4a4db56be`.

- 17 Python tests pass: authentication, authorization, CSRF, path confinement, file transfer, persistence, hardware metrics, catalog constraints, RAID disk counts, typed erasure confirmation, disk identity revalidation, SMART rejection, and secondary Btrfs member protection.
- JavaScript syntax checks pass. The deployed App Store, search, app-details/settings dialog, RAID selection, and protected-disk display were checked in the browser. The Harbor service is active with no failed system services.
- All 181 pinned official app definitions pass Docker Compose configuration validation. This validates configuration structure, not every application's behavior on every computer.
- QEMU/KVM: live ISO boot under UEFI; interactive offline installation to a new 24 GiB virtual system disk; installed disk boots under BIOS and UEFI with the ISO removed.
- Two 2 GiB virtual disks: RAID1 creation through the authenticated API, private shared-folder creation, and persistence after reboot.
- Two additional 2 GiB virtual disks: JBOD creation with Btrfs single-data profile, combined capacity, system-managed mount, and shared-folder creation.
- The official Syncthing definition installs, stops, starts, and serves its web interface with HTTP 200 after reboot.
- The final hybrid ISO boots as a read-only virtual USB storage device under legacy BIOS without any destination disks attached.

The release contains fixes discovered in VM testing: storage mounts are created by systemd so Docker can see them, and initramfs generation runs in a dedicated system service with access to kernel module files. JBOD uses Btrfs single-data because this kernel omits the obsolete MD linear module.

RAID 0, 5, 6, and 10 use standard MD creation arguments and have configuration and disk-count validation; this test run exercised RAID1 and JBOD end to end. No real disks were reformatted during this release's tests. The existing physical NAS data mirror remains mounted and protected.

See [INSTALL-0.2.md](INSTALL-0.2.md) for installation steps and supported hardware requirements. The machine-readable VM results are stored in `release-0.2-validation.json`.
