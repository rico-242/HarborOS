# Remote clean installation (experimental, 0.9.0)

Harbour can boot its signed recovery ISO from the installed system SSD, copy the live OS into RAM and reinstall the entire system disk without USB media or a local monitor. A clean install erases all accounts, applications, system SSD files and legacy ZimaOS partitions. It is distinct from a signed in-place update.

Prepare the matching recovery image in Settings first. An existing root/sudo SSH administrator then runs `tools/remote-reinstall.py stage --host ADDRESS --user ADMIN`. The client uses the existing known SSH host key. Dependencies are Python, Paramiko and cryptography. On Windows, its temporary key directory is restricted to the current user and SYSTEM.

Staging binds the plan to the system disk's stable ID, serial, size and original filesystem UUID. The current physical wired adapter's MAC, IPv4 address, prefix, gateway and DNS are retained as a static configuration so the machine returns at the same address. Reserve that address in your router. Bonded, wireless and unusual routed configurations currently require another recovery method.

`boot --confirmation "BOOT REMOTE RECOVERY"` restarts into RAM recovery. `status` checks the pinned recovery SSH identity. `install --confirmation "ERASE SYSTEM-SERIAL"` erases the planned system disk and reboots into the new graphical first-owner setup. EFI variable writes are checked before erasure. Installation cannot proceed unless the live image is running from RAM and all disk identities still match. A started-operation marker prevents blind retries.

An optional, separately authorized `stage --pool hybrid1` plan can reset a healthy existing two-disk native Btrfs mirror into Harbour Hybrid1. The client additionally requires `--pool-confirmation "ERASE POOL Main-Storage"` before beginning installation. After the new OS boots, it revalidates both data disks and the old pool UUID, checks health and creates the pool before owner setup. Other disks are excluded. This option erases that old pool; normal installation does not reset data disks.

Run `setup --host ADDRESS` to open the graphical setup through `http://127.0.0.1:17080/`. Choose the new owner credentials yourself. The temporary SSH key permits only status, the planned installation/pool operation, the post-install reboot and forwarding to the local setup server. It grants no arbitrary shell or other forwarded ports. First-owner creation automatically deletes the temporary authorized key and private host key, then reloads SSH with the new system's ordinary host keys.

The recovery bootstrap and its private host key exist only on the administrator's machine/NAS and are never included in release ISOs or source archives. Do not share the private `.local/remote-reinstall` directory. Do not blindly retry an interrupted destructive operation: inspect its marker, disk layout and journal first.

Validation: a disposable EFI VM completed RAM recovery, a full fresh system install, reboot, an explicitly planned two-disk Hybrid1 reset, restricted SSH/port tests, graphical first-owner setup via the SSH tunnel and automatic access cleanup. An unrelated virtual data array retained its probe checksum. See [validation](remote-install-validation-0.9.0.json). Physical hardware validation is a separate step.
