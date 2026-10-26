set -eu
root=/DATA/harbor/rootfs
esp=/mnt/boot/EFI/BOOT
test "$(readlink -f /dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694)" = /dev/sda
test -f "$root/boot/harbor-vmlinuz"
test -f "$root/boot/harbor-initrd"
test -f "$root/var/lib/harbor/admin.json"
test -f "$root/etc/ssh/ssh_host_ed25519_key"
cp /etc/machine-id "$root/etc/machine-id"
if [ ! -e "$root/DATA" ] && [ ! -L "$root/DATA" ]; then ln -s /mnt/harbor-host "$root/DATA"; fi
data_uuid=$(blkid -s UUID -o value /dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694-part8)
test "$data_uuid" = 4fc77cd8-8c54-4a6a-b6c6-c3d2c51e84e2
if [ ! -f "$esp/grub-zima.cfg" ]; then cp -p "$esp/grub.cfg" "$esp/grub-zima.cfg"; fi
cat > /DATA/harbor/artifacts/grub-harbor.cfg <<'EOF'
set timeout=5
load_env
set default=1
set fallback=1
set harbor_trial="harbor.trial=1"
if [ "$harbor_default" = "1" ]; then
    set default=0
    set harbor_trial=""
elif [ "$harbor_once" = "1" ]; then
    set default=0
fi
set harbor_once=0
save_env harbor_once

menuentry 'Harbor OS 0.1.0' --id harbor {
    regexp --set 1:boothd (.+),.+ ${root}
    set harborroot=${boothd},gpt8
    linux ($harborroot)/harbor/rootfs/boot/harbor-vmlinuz root=UUID=4fc77cd8-8c54-4a6a-b6c6-c3d2c51e84e2 rw rootwait harbor.subdir=harbor/rootfs $harbor_trial panic=30 net.ifnames=0 biosdevname=0 console=tty1
    initrd ($harborroot)/harbor/rootfs/boot/harbor-initrd
}

menuentry 'ZimaOS (previous system)' --id zima {
    configfile ($root)/EFI/BOOT/grub-zima.cfg
}
EOF
docker run --rm -v /DATA/harbor/artifacts:/artifacts:ro --entrypoint /usr/bin/grub-script-check harbor-image-builder:0.1 /artifacts/grub-harbor.cfg
cp /DATA/harbor/artifacts/grub-harbor.cfg "$esp/grub.cfg"
grub-editenv "$esp/grubenv" set harbor_once=0 harbor_default=0
sync -f "$esp/grub.cfg"
printf 'Harbor entry staged. ZimaOS is still the default.\n'
grub-editenv "$esp/grubenv" list
