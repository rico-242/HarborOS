# Harbor OS 0.1.0 verification

Date: 2026-10-25. Target: 192.168.1.97.

## Automated checks

Eight local HTTP integration tests passed, covering initial setup, sign-in, logout, session expiry, throttling, CSRF/origin enforcement, path confinement, uploads/downloads, persistence, static-content headers, and rejection of real appliance operations in preview mode. JavaScript syntax validation passed.

## VM checks on the NAS

- The standalone GPT disk image booted through its BIOS bootloader.
- The directory-root installation booted with the custom initramfs hook.
- A UEFI fixture using the exact original ZimaOS GRUB binary booted the corrected entry. The vendor loader lacks the UUID-search command used in the initial entry; the final entry derives the SSD from the existing GRUB root, as the original ZimaOS configuration does.
- HTTPS was pinned to the certificate fingerprint read through the authenticated host's serial console.
- Initial administrator creation, secure sign-in, real Linux metrics, and Btrfs data mounting passed.
- Uploaded and downloaded contents matched byte for byte.
- Read-only snapshots and restored copies preserved the tested file contents.
- Authenticated SMB uploads and downloads matched byte for byte.
- Jellyfin downloaded, installed, ran, and returned a healthy HTTP response inside the isolated VM.
- Syncthing's official image returned a healthy response in a temporary localhost-only test container, using UID 1000, dropped capabilities, and no-new-privileges. Its upstream entrypoint was checked to select the supported non-root startup mode.

## Physical installation

Harbor OS 0.1.0 booted on the actual NAS with Linux 6.12.113+deb13-amd64. The root is an ext4 directory mount from the SSD's eighth partition. The EFI partition mounts at /boot/efi. The two suitable HDDs mount as a Btrfs RAID1 data volume at /srv/harbor/storage.

Verified on physical hardware:

- Existing SSH host identity and rico login retained.
- HTTPS authentication with certificate validation against the local certificate.
- Private SMB file transfer, with byte-for-byte integrity.
- Browser API file transfer, read-only Btrfs snapshot, and restored file integrity.
- Mounted mirror and Docker app engine.
- Harbor, SSH, Samba, Docker, and network services active; no failed system units.
- Zero Btrfs read, write, flush, corruption, and generation errors on both mirror members.
- Harbor committed as the default boot entry, with ZimaOS retained as a selectable previous system.

Initial shared folders: Documents, Media, Backups, and Harbor-Restore-Check. The latter is the verified restored sample. Documents contains a welcome text file and an SMB test file.

The final reboot returned a new boot ID, `625e2b54-cc82-49b8-804b-0be420a4f8b2`, with Harbor as the persistent default and without the trial flag. HTTPS login, the RAID1 mount, saved shared folders, original files, and restored file contents all passed after reboot. Core services remained active with no failed units.

## Artifacts

The compressed standalone image was copied back to the Windows workspace. Its final SHA-256 checksum is recorded in `dist/harbor-0.1.0-amd64.img.zst.sha256` and is verified against the local file before delivery.

Artifact: dist/harbor-0.1.0-amd64.img.zst, approximately 506 MiB. Decompressed image: 12 GiB. New installations generate their own host keys, certificate, and first-setup code. Personalized credentials are not included in the release image.

## Practical limits

The installed certificate covers harbor.local, harbor, 127.0.0.1, and 192.168.1.97. The numeric address was verified from the Windows PC using the certificate retrieved through the existing verified SSH identity. Its SHA-256 fingerprint is:

    A9:4D:0F:42:0E:6A:E1:F5:0F:4B:23:EC:6D:91:5D:E5:A0:B7:47:3A:6D:F1:C0:D3:62:A4:B8:29:98:79:A0:B4

This is a working experimental release. No complete HDD surface test, extended soak test, production security audit, power-loss test matrix, or independent backup/restore exercise has been completed. Two attached HDDs with read-error findings remain excluded and should be replaced before use in a data pool. Btrfs snapshots on the same mirror do not provide an independent backup.
