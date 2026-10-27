# Wipe a non-pool drive

Storage → Disks → Wipe drive offers a quick metadata wipe, independently of SMART health. The owner reviews the model, size, serial and any unused old RAID array that will be stopped, then enters `WIPE SERIAL` and acknowledges data loss. No physical drive is wiped merely by installing this update.

Current pool members, the system disk, mounted filesystems, swap, read-only disks, unknown device layers and ambiguous Btrfs membership remain protected. A mounted external volume must be unmounted first. Old unmounted MD arrays, including inactive zero-capacity arrays, may be stopped after review. Their identity is verified using array details and member superblocks; only the selected disk loses its signatures. Other members retain their metadata.

The operation revalidates the stable disk ID, serial, size, partitions, old array UUIDs and mount topology before detaching and before writing. It serializes against other storage operations and records a recovery journal before any destructive step. Failures retain that journal for inspection and are never silently retried.

Progress shows identity checks, old array detachment, signature wiping and final verification. This removes recognized partition/filesystem/RAID signatures; it is not a secure erase of all file contents. A hardware failure can prevent completion. Wiping does not repair health, and adding a disk to a pool still requires the usual health checks.
