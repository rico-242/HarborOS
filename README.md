# Harbour OS

A small home NAS distribution with its own web interface, built on Debian 13. Inspired by the simplicity of ZimaOS and the storage-focused experience of TrueNAS. This is an independent implementation, not a TrueNAS fork.

Version: **0.8.1, experimental**. Install signed Harbour releases in place without reinstalling an ISO. Read the [update and Ethernet bonding guide](docs/UPDATES-AND-BONDING-0.4.md), [desktop refinements](docs/UI-REFINEMENTS-0.3.1.md), and [feature comparison](docs/RELEASE-0.3.md). The current live installer ISO is `harbour-0.8.1-amd64.iso`, available with its SHA-256 checksum on GitHub Releases; older installations need a one-time updater bridge. The current signed bundle is `dist/harbour-0.8.1-amd64.harbour-update`. See [GitHub updates](docs/GITHUB-UPDATES-0.4.1.md) and [GitHub Releases](https://github.com/rico-242/HarborOS/releases). This release does not claim complete ZimaOS feature or pixel parity.

Jellyfin installation now omits unavailable optional acceleration devices and Raspberry Pi libraries, while retaining available GPU access.

Installed apps now have confirmed, owner-only Uninstall controls in Settings and the App Store. App data, volumes and images are kept.

Harbour Hybrid 1/2 support mixed-size new pools, one-/two-drive protection, and growth by adding protected groups. Native Btrfs RAID1 can also expand without recreation. See [hybrid storage and expansion](docs/HYBRID-STORAGE-0.6.md) for limits and recovery.

Pool maintenance now includes Repair pool, copy-first Replace drive, confirmed Remove drive, resumable repair journals, and real browser-import progress. See [drive maintenance and imports](docs/DRIVE-MAINTENANCE-0.7.md).

System SSD files, clearer light/dark visuals and signed RAM-based recovery installation are available in 0.8.1. See [SSD files and reinstalling](docs/SSD-AND-REINSTALL-0.8.md).

## What works

- Reference-based light and dark themes with green accents, redesigned Files/App Store/Settings/RAID screens, saved favorites and navigation history, local featured banners, and inline widget switches. See the [0.5.0 design notes and screenshots](docs/DESIGN-0.5.0.md).

- Signed in-place Harbour releases with health checks and recovery, explicit application rollback, and public/private GitHub release discovery, write-only read tokens and an optional experimental channel. Debian/kernel packages use Debian's signed repositories.
- Active/backup and LACP Ethernet bonds, guarded network changes with timed rollback and boot recovery; two NICs are required.
- App and drive-setup progress windows with real stages, elapsed time, failure details, background/minimize controls and a top-bar task indicator; refined widgets and larger SVG navigation controls.
- Graphical live installer and first-account setup without a setup code, feature tour, and an unprivileged local Chromium session.
- Application-window controls, file list/grid views, current-folder search, multi-selection, copy/move/rename, recoverable deletion and restore, text/image previews, ZIP downloads and uploads up to 1 GiB per file.
- Owner-protected member accounts and per-folder read/write permissions in both the web interface and Samba. New members have no folder access.
- Real timezone changes, service/network status, confirmed reboot/shutdown, and signed Debian package checks/upgrades.
- A black and charcoal desktop following ZimaOS's dashboard layout, with white text, green accents, circular CPU/RAM gauges, storage and network widgets, searchable square app tiles, and saved widget preferences. See docs/DARK-DESKTOP.md.

- HTTPS administrator sign-in, salted scrypt password storage, expiring sessions, CSRF protection, and login throttling.
- Live Linux memory, CPU, CPU temperature, network throughput, uptime, disk, and storage information.
- Private SMB shared folders and browser file browsing, folder creation, upload, and download.
- Btrfs subvolume snapshots and restoration into a new shared folder.
- The official ZimaOS app-definition snapshot: 181 apps, bundled icons, search, categories, app settings, and Compose-based install/start/stop jobs. All 181 normalized definitions pass Docker Compose configuration validation.
- A Zima-style storage wizard: Combine or Enable, RAID selection, stable disk selection, capacity estimate, name, and explicit erasure confirmation. Linux MD provides RAID 0/1/5/6/10 beneath Btrfs; JBOD uses Btrfs's single-data profile.
- Activity history and a settings page.
- A BIOS/UEFI hybrid live installer ISO with offline installation and a fresh first-boot setup, plus the existing directory-root deployment and historical raw disk image.

Snapshots are on the data volume and do not replace an independent backup.

## Project layout

- harbor/: standard-library Python service and local web assets.
- os/: Debian filesystem builder, disk-image packager, systemd units, initramfs hook, and kernel-update hook.
- tools/: SSH deployment utilities and appliance verification scripts.
- tests/: HTTP authentication, authorization, file confinement, transfer, persistence, and configuration tests.
- docs/HARDWARE.md: inspected target hardware and disk findings.

## Development

Run Python 3.12 or newer:

    python harbor/server.py --demo

The development preview binds only to http://127.0.0.1:8088. It uses files under .local/preview and explicitly disables real SMB, disk, snapshot, container and system operations. Create the first account graphically; no setup code is required. HARBOR_DEMO_ROOT can select another isolated preview directory.

Run tests:

    python -m unittest discover -s tests -v
    node --check harbor/web/app.js

The SSH helper uses Paramiko from tools/requirements.txt. Supply HARBOR_SSH_PASSWORD in the process environment; never write it into source or scripts. Host keys are verified against the existing known_hosts file. Private VM keys are pinned through the authenticated host's serial console.

## Building

Use a Linux Docker host. Build os/Dockerfile.builder, then run os/build-rootfs.sh in a privileged builder container with the source at /source and a dedicated output directory at /target. The builder needs privileged mounts and must run only on a trusted development host.

The historical os/build-image.sh recipe writes a sparse GPT bootstrap image with BIOS boot, EFI and ext4 partitions. Use the current ISO workflow below for the graphical release. New installations generate fresh SSH/TLS identities and create the first owner graphically.

Every push to `main` builds and boot-tests an ISO in GitHub Actions; version tags and published releases attach the tested ISO and checksum to GitHub Releases. See [ISO builds and downloads](docs/ISO-BUILDS.md).

The current live-ISO workflow uses os/prepare-live-root.sh, tools/prepare-graphical-root.sh, os/configure-graphical.sh and os/build-iso.sh. It uses a separate filesystem under /DATA/harbor/iso-build, bootstrapped from a clean Debian root, installs Debian live-boot and graphical tools, bundles the current Harbour source, and creates a BIOS/UEFI hybrid ISO with grub-mkrescue. It does not include the NAS's administrator state, host keys, or TLS key. See docs/RELEASE-0.3.md for validation. Older raw-image recipes remain historical bootstrap tools.

The build recipe uses Debian's signed trixie repositories. Package versions are determined by repository state at build time; builds are not bit-for-bit reproducible.

## Current deployment

Target: the existing ZimaOS computer at 192.168.1.97. The user declared the old data disposable. Two suitable 1 TB HDDs now form a Btrfs RAID1 volume; two suspect HDDs are excluded. See docs/HARDWARE.md.

The physical installation lives at /DATA/harbor/rootfs on the existing SSD. Its initramfs mounts that directory as the operating-system root. The boot menu retains a ZimaOS entry and uses a one-shot flag for the trial boot. A userspace recovery guard requests a reboot if a trial is not acknowledged within four minutes; it does not protect against all firmware or early-kernel failures.

The independent release image is stored on the NAS under /DATA/harbor/release/artifacts. It contains no personalized administrator credentials. The physical installation keeps the existing rico account and SSH host identity.

## Limits of 0.3.0

This is an early working release, not a production-certified storage appliance. The web interface creates one primary data pool; extra pools, expansion, drive replacement, native cloud OAuth, scheduled external backups, native VM management and IceWhale's private ZimaClient/P2P service are not implemented. Setup is English only. HTTPS uses a locally generated certificate. App images are pulled from upstream registries and may need hardware, additional settings, or their own account setup. Secure Boot is not supported by this unsigned ISO. The release notes distinguish working integrations from remaining feature differences.

The data volume is mounted by filesystem UUID. Storage writes are refused if it is not mounted. Physical drive operations in deployment scripts are restricted to explicitly verified device identities.

## References

- Debian: https://www.debian.org/releases/trixie/
- Btrfs documentation: https://btrfs.readthedocs.io/
- TrueNAS middleware research: https://github.com/truenas/middleware
- ZimaOS inspiration: https://github.com/IceWhaleTech/ZimaOS

Harbor's interface and storage backend are independent implementations. The official app definitions and icons are bundled from IceWhaleTech/CasaOS-AppStore at revision 7743473daff401172d9a155ce904953cda6145ae under Apache 2.0; see harbor/catalog/NOTICE and UPSTREAM-LICENSE. App names and icons belong to their respective projects. Debian component copyright information is retained in the image's /usr/share/doc directories.
