# Drive health warnings — Harbour OS 0.11.1

SMART failures and bad-sector reports are advisory when creating, expanding, or repairing a pool. Review the warning and the existing typed confirmation to proceed. This applies to both clean installations and signed updates. No drives are automatically added, wiped, detached, or replaced by this update.

The disk list, selection screen, and pool-member list show **Failing**, the drive serial number, and the SMART reasons. Reported problems include overall SMART failure, reallocated/pending/offline uncorrectable sectors, reported uncorrectable errors, NVMe critical warnings/media errors, and exhausted NVMe rated endurance. A SMART pass is not a guarantee against future failure. Wiping a disk does not repair hardware.

A failing member marks its pool **At risk — failing drive**, with affected serial numbers in Storage and the desktop widget. SMART deterioration is distinct from a degraded RAID: Harbour continues to report the actual RAID protection and missing-member state independently. Failing spare disks do not mark the current pool degraded.

SMART reads run in a background worker, refresh on active appliance requests at most once per minute, and are cached by stable identifier plus disk identity. The Storage page updates visible health labels every ten seconds. New or unreadable assessments show Checking health or Health unknown. This is request-driven monitoring, not an email/push alert service.

Operating-system disks, mounted filesystems, active arrays, current pool members, read-only disks, disk-identity changes, interrupted operations, and unsafe RAID topology remain protected. A disk still held by another active RAID array must first be released using the appropriate drive workflow; a SMART warning alone never makes an otherwise eligible disk unavailable.

Validation: 142 Python regression tests, JavaScript syntax checks, and signed-update verification. Physical NAS verification reads actual SMART counters and reviews an expansion plan without executing it. Existing accounts, pool configuration, and application containers are preserved. Release ISO automation separately validates BIOS and UEFI boot.
