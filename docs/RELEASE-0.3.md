# Harbour OS 0.3.0

This release extends the independent Debian 13 NAS implementation with a graphical boot and installation path, a charcoal/white/green desktop, application-window controls, and functional file and member-management tools. It is a development release for testing, not a claim of complete ZimaOS compatibility.

## Delivered

- Graphical live welcome, disk selection, serial/capacity review, erasure acknowledgment, installation progress and completion screens; offline installation to a separate system disk, with BIOS and UEFI bootloaders.
- Graphical first-account setup and feature tour, without a user-entered setup code. A local-only cookie and CSRF session protects provisioning; the LAN listener cannot create the first account.
- An unprivileged Chromium kiosk on LightDM/Openbox and a dark green Plymouth boot theme. No browser sandbox or TLS warning bypass is added.
- Matching dark surfaces and green accents across the desktop, App Store, storage wizard, file manager, dialogs, settings, onboarding and installer. Window entrance, hover and progress animations respect reduced-motion preferences.
- Movable/resizable application windows with minimize/restore, maximize and close controls; a desktop backdrop and saved appearance/widget preferences. The main shell manages one application window at a time.
- File list/grid views, current-folder search, multi-selection, keyboard shortcuts, drag-and-drop uploads up to 1 GiB per file, copy/move/rename, recoverable deletion and restore, text/image preview and streamed ZIP downloads. Existing destination files are never silently overwritten.
- Owner-protected member accounts, reversible disable/enable, and per-folder read/write permissions enforced in both HTTP and Samba. New members have no folder access. Members cannot install apps or change disks/system settings.
- Settings for real timezone changes, service/network status, confirmed restart/shutdown, signed Debian package checks and upgrades. Independent update jobs survive a web-service restart.
- The existing official catalog snapshot of 181 app definitions and icons; Compose app install/start/stop, RAID creation and Btrfs snapshots remain functional.

## Validation

The release was installed on disposable virtual disks. The graphical live session and installed first boot were viewed through the VM's actual framebuffer using noVNC. Chromium ran as `harbour-display`, not root. The installer API completed an offline installation to the explicitly named 24 GiB test system disk. The installed system created its owner through the local console API without a code, protected the system disk, created RAID1 on two disposable data disks, and served a shared folder through Samba.

Actual Samba tests checked no access, read-only write rejection, read/write transfer, disabling and re-enabling a member. ZIP contents round-tripped. Timezone changes and signed Debian package checks/upgrades ran in the VM. Additional boot/persistence checks are recorded in `release-0.3-validation.json`.

The exact final ISO also booted as a raw USB device under legacy BIOS, installed offline to a second fresh virtual disk, and booted that disk under UEFI into the graphical account form. Fresh admin/member state, absence of a setup code, and denial of provisioning on the public HTTPS listener were verified. Its downloaded SHA-256 matches the build manifest. Screenshots include `final-iso-account-0.3.png`, `iso-welcome-0.3.png`, `nas-desktop-0.3.png` and `nas-app-store-0.3.png`.

The local automated suite has 21 passing tests covering setup locality/CSRF, authentication, role boundaries, file confinement, transfer/recycle/restore behavior, archive round trips, catalog adaptation, and storage eligibility/confirmation. All 181 catalog definitions passed Compose normalization/configuration validation in the prior release; that does not imply all apps have been installed or tested on every hardware platform.

The NAS received the current web service and graphical-session packages/configuration. Its existing owner, certificate, storage and ZimaOS fallback entry were preserved. The physical NAS was not rebooted and did not run the package-upgrade control as part of validation.

## Feature comparison and limits

| Area | Harbour 0.3 behavior | Remaining difference |
|---|---|---|
| Visual design | Dark desktop, widget column, square app tiles, window chrome, sidebars, green controls and animations | Independent implementation; exhaustive pixel/animation parity is not established |
| Setup | Graphical local account and tour, no setup code | English only; monitor and keyboard required for first account |
| App Store | Official 181-app snapshot, categories, search, settings, Compose jobs | Pinned snapshot; no guarantee of future Zima catalog/API compatibility |
| RAID | Primary pool creation with RAID0/1/5/6/10, Basic or JBOD and Btrfs | No GUI for extra pools, expansion, disk replacement or migration |
| Files and sharing | Browser file manager, ZIP, recycle bin, SMB and member permissions | No built-in cloud-drive OAuth, document editor, media transcoding or external-drive automount manager |
| Backups | Manual Btrfs snapshots, restore to new folder; backup apps available | No native scheduled off-device backup workflow |
| Remote access | Explicit Tailscale installation from catalog | Does not implement IceWhale's private ZimaClient/P2P account service |
| Transfers/photos | Snapdrop and Immich integrations through catalog | Separate apps with their own setup and accounts |
| Virtual machines | Catalog offers Virtual Machine Manager | No native Zima ZVM service, VM migration or integrated hypervisor lifecycle |
| Updates | Signed Debian package check/upgrade | No signed, atomic Harbour A/B OS update service |
| Hardware | Debian drivers, tested VM boot and current NAS session | Other PC graphics, Wi-Fi and controller combinations need hardware testing; Secure Boot unsupported |

Snapshots and the recycle bin reside on the data volume and do not replace independent backups. ZIP exports are limited to 10,000 files/16 GiB; use SMB for larger transfers. The primary data pool is Btrfs with Linux MD RAID where applicable; this is not a TrueNAS/ZFS fork.

Reference flows came from the [official ZimaOS setup guide](https://www.zimaspace.com/docs/zimaos/get-started) and [feature documentation](https://www.zimaspace.com/docs/zimaos/features). The Apache-2.0 app catalog license, source revision and notices are bundled under `harbor/catalog`.

## Build and artifacts

The `.iso`, `.iso.sha256` and source archive are under `dist/`. Use `INSTALL-0.3.md` for installation. No personalized NAS credentials, TLS private keys, SSH identities or VM acceptance accounts are included in the ISO.

The ISO was assembled from the isolated clean Debian root under `/DATA/harbor/iso-build/root`, using `tools/prepare-graphical-root.sh`, `os/configure-graphical.sh` and `os/build-iso.sh`. The original clean base can be rebuilt with `os/build-rootfs.sh`; the historical bootstrap is documented in `os/prepare-live-root.sh`. Debian package repository state affects binary versions, so builds are not bit-for-bit reproducible. Build scripts require root mounts and must be used only with isolated output directories on a trusted development machine.
