#!/bin/bash
set -euo pipefail
root=/DATA/harbor/hybrid-test
mkdir -p "$root"
test ! -e "$root/guest.pid"
if ! test -e "$root/system.qcow2"; then qemu-img create -f qcow2 -F qcow2 -b /DATA/harbor/graphical-test/final-system.qcow2 "$root/system.qcow2"; fi
firmware=()
if [ "${HARBOR_TEST_UEFI:-0}" = 1 ]; then
 if ! test -f "$root/remote-vars.fd"; then cp /usr/share/OVMF/OVMF_VARS_4M.fd "$root/remote-vars.fd"; fi
 firmware=(-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd -drive "if=pflash,format=raw,file=$root/remote-vars.fd")
fi
network=user,id=net0
if [ "${HARBOR_TEST_FORWARD_SSH:-0}" = 1 ]; then network=user,id=net0,hostfwd=tcp:127.0.0.1:19022-:22; fi
args=()
for i in $(seq 1 10); do
 if [ "${HARBOR_TEST_EXCLUDE:-}" = "$i" ]; then continue; fi
 size=1G; if [ "$i" -ge 3 ] && [ "$i" -le 6 ]; then size=2G; fi
 if ! test -f "$root/data$i.qcow2"; then qemu-img create -f qcow2 "$root/data$i.qcow2" "$size"; fi
 args+=(-drive "file=$root/data$i.qcow2,if=none,id=h$i,format=qcow2" -device "virtio-blk-pci,id=devh$i,drive=h$i,serial=HARBOUR_HYBRID_$i")
done
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 6144 -smp 2 -display none \
 -drive file="$root/system.qcow2",if=none,id=system,format=qcow2 -device virtio-blk-pci,drive=system,serial=HARBOUR_HYBRID_SYSTEM \
 "${args[@]}" "${firmware[@]}" -netdev "$network" -device virtio-net-pci,netdev=net0 \
 -device virtio-serial-pci -chardev socket,path="$root/agent.sock",server=on,wait=off,id=agent0 -device virtserialport,chardev=agent0,name=org.qemu.guest_agent.0 \
 -serial file:"$root/serial.log" -qmp unix:"$root/qmp.sock",server=on,wait=off -daemonize -pidfile "$root/guest.pid"
echo 'Disposable hybrid VM started with ten file-backed disks. No physical drives attached.'
