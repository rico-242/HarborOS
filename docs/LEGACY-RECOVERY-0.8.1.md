# Legacy boot compatibility — 0.8.1

This patch supports the earlier ZimaOS-to-Harbour migration layout: an ext4 root under `/harbor/rootfs` and GRUB configuration/environment on the mounted EFI partition. It checks this known layout, preserves the existing Harbour/ZimaOS default and fallback policy, and adds a separate one-time recovery flag. The recovery kernel and `findiso` path use the physical filesystem's subdirectory prefix.

Preparation does not select recovery or reboot. The flag is set only after the owner confirms **Boot recovery**, and GRUB clears it when used. Missing boot configuration, an unmounted EFI partition, or an unknown filesystem-root layout is rejected before download. A prepared image is tied to its root UUID and boot layout.

A disposable VM booted the subdirectory recovery path into RAM, released its system disk, and verified that the one-time flag cleared. The generated configuration also passed GRUB's parser against the physical NAS's actual migration layout without altering its active configuration during validation. 93 automated tests passed. See `legacy-recovery-validation-0.8.1.json` and [the reinstall guide](SSD-AND-REINSTALL-0.8.md).

A clean install onto this system SSD erases the previous ZimaOS installation too. Preparation and booting recovery do not erase it; the graphical installer requires separate destination/erase confirmation.
