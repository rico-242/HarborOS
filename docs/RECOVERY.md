# Boot and recovery

Harbor has a boot menu entry alongside `ZimaOS (previous system)`. The original ZimaOS configuration is retained as `EFI/BOOT/grub-zima.cfg` on the SSD's EFI partition. A further copy of the original configuration and environment is under `/DATA/harbor/artifacts/zima-boot-backup`.

## Return to ZimaOS

From Harbor, use an authenticated SSH session and run:

    sudo grub-editenv /boot/efi/EFI/BOOT/grubenv set harbor_default=0 harbor_once=0
    sudo reboot

From ZimaOS, the same environment file is at `/mnt/boot/EFI/BOOT/grubenv`.

You can also select the previous system from the physical boot menu. Selecting it loads the preserved original configuration.

## Trial boot guard

A one-shot Harbor boot clears its GRUB one-shot flag before launching Linux. With `harbor.trial=1`, the guard requests a reboot after four minutes unless `/var/lib/harbor/boot-confirmed` exists. An early firmware failure, a kernel hang that prevents reboot, or a power failure may still require physical access. This is not a general unattended rollback mechanism.

## Kernel updates

The initramfs post-update hook keeps `/boot/harbor-vmlinuz` and `/boot/harbor-initrd` pointing to the successfully generated kernel and initramfs. The Harbor boot entries load those stable links. Do not reboot while package or initramfs updates are running.

## HTTPS identity

Harbor generates a local HTTPS certificate at first boot. Its fingerprint is printed on the physical console and can be checked over the existing verified SSH connection:

    sudo openssl x509 -in /var/lib/harbor/tls.crt -noout -fingerprint -sha256

Browsers will require the user to trust this locally generated certificate. The automation does not bypass browser certificate warnings.

## Independent image

The standalone image has its own BIOS and UEFI bootloaders and does not depend on ZimaOS. Its compressed artifact and SHA-256 manifests are under `/DATA/harbor/release/artifacts`. Decompress the `.img.zst` before writing the image to a target drive. Writing the image replaces that target's partition table and filesystems. The image's root partition is 12 GiB minus its boot partitions; extending it is a separate administrative operation.

Its first-setup code is shown on the attached console. Setup creates a Linux/SMB account and the Harbor administrator. New installations generate independent SSH host keys and HTTPS certificates.
