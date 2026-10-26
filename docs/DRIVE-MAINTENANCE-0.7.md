# Drive maintenance and browser imports — 0.7.0

Open **Storage → Pool members**. Only the owner can manage disks.

- **Repair pool** finds the first missing/detached member. Connect an unused replacement, review its model/serial/capacity, and type the confirmation. The replacement is erased. Surviving members stay connected.
- **Replace drive** copies/rebuilds onto a spare before releasing a connected member. Wait for completion before unplugging the old drive.
- **Remove drive** evacuates a native Btrfs RAID1 member only when the remaining disks retain every existing replication profile and sufficient working capacity. A two-disk mirror cannot shrink to one; use Replace drive instead. For MD/Hybrid it deliberately detaches a healthy member for replacement, reducing protection until repair; it does not permanently shrink or reshape the array.
- MD RAID1/5/6/10 and managed Harbour Hybrid1/2 use kernel RAID rebuilds. Each Hybrid tier is repaired and its exact member slot checked before updating the saved layout. When multiple disks are absent, repair the first missing member in the protected group before the next one.
- If a saved Btrfs pool could not mount after a missing-disk boot, **Repair pool → Open existing pool** attempts a confirmed degraded mount. The kernel refuses a mount without enough surviving copies. This does not format disks, force arrays, or make degraded mounting the normal boot policy.
- **Resume repair** verifies the recorded pool/replacement identity and continues an interrupted member operation. Prepared MD targets are retained, not reformatted. Interruption during GPT preparation needs manual inspection. Creation/expansion journals still need manual review. Keep all disks attached and retain `/var/lib/harbor/storage-operation.json` when Harbour reports an error.

Replacement sizing uses the original Btrfs device record even when the missing row reports zero size. Stable disk IDs, SMART checks, unused-disk checks, pool UUIDs and current membership are revalidated immediately before writes. The original RAID level is retained. RAID0, JBOD and Basic cannot reconstruct lost data. This is experimental storage-management software; independent backups remain necessary.

Open **Files**, choose a writable shared folder, then **Import** or drag files into it. A floating progress panel shows the current file, queue count, actual browser bytes sent, total bytes, and average transfer speed. It shows **Saving to drive** until the server returns after its file flush and final move. Only then does it show 100% and **Import complete**. It stays visible across Harbour navigation. Leaving/reloading the browser while importing triggers a warning. Duplicate names are refused; files are not overwritten. Completed files are retained if a later queued file fails. Maximum size remains 1 GiB per file; use SMB for larger transfers. Uploads are not resumable after the browser closes.

## Validation

Disposable KVM disks, with no physical block devices passed through, exercised connected and cold-missing native mirror replacement, safe native evacuation, rejection of a two-member shrink, mixed-tier Hybrid1 replacement/detach/repair, Hybrid2 copy-first replacement and two simultaneous missing members, RAID slot ordering, journal resume, and standard MD mirror replacement/detach/repair. File hashes and scrub results were checked under the service's filesystem/security restrictions. See `drive-validation-0.7.0.json`.

A throttled local browser import transferred a 128 MiB test file through the actual upload endpoint. The visible progress advanced before completion and the stored SHA-256 matched. UI checks covered dark/light layouts and the no-spare state. Physical pool members were not modified during development.

The signed update installs in place; a clean-install ISO is also published for this release. The ISO build verifies both BIOS and UEFI live boot. These tests do not certify every controller, hot-swap bay, disk firmware or every failure mode. Shut down before physically changing drives unless the hardware supports hot swapping.

References: [Btrfs replacement](https://btrfs.readthedocs.io/en/latest/btrfs-replace.html), [Btrfs device removal](https://btrfs.readthedocs.io/en/latest/btrfs-device.html), [mdadm management](https://man7.org/linux/man-pages/man8/mdadm.8.html).
