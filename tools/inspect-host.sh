set -eu
printf '\n--- Operating system ---\n'
uname -a
cat /etc/os-release
id
printf '\n--- Hardware ---\n'
lscpu
free -h
printf '\n--- Disks and mounts ---\n'
lsblk -b -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,TRAN,RO
findmnt /
df -h
printf '\n--- Runtime ---\n'
command -v docker || true
command -v python3 || true
command -v qemu-system-x86_64 || true
test ! -e /dev/kvm || ls -l /dev/kvm
docker version 2>/dev/null || true
docker ps --format '{{.Names}} {{.Image}} {{.Ports}}' 2>/dev/null || true
printf '\n--- Boot ---\n'
test ! -d /sys/firmware/efi || echo UEFI
cat /proc/cmdline
printf '\n--- Network ---\n'
ip -brief address
