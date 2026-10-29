# Virtual machines in Harbour 0.17

Open **Settings → Virtual machines** as the owner. Install virtualization support if prompted; hardware virtualization must be enabled in firmware.

1. Choose **Upload ISO** and upload your operating system installer.
2. Choose **Create VM**. Select the ISO, CPU cores, memory in MiB, virtual disk size in GiB and private NAT networking.
3. Follow creation in the application progress window.
4. Choose **Open console**. The browser console supports keyboard, mouse, full screen, reconnect and Ctrl Alt Del.
5. Install the guest OS onto its virtual disk. After installation, shut down the guest, choose **Eject installer ISO**, then **Boot from disk** and **Start**.

Boot-order changes apply on the next full power-on. Restart sends a graceful reboot to the guest. Force off requires typing `STOP <name>` because unsaved guest changes can be lost. Delete removes the VM definition and retains the disk image; it requires `DELETE <name>`.

VM disk images default to `/var/lib/libvirt/images/harbour`; ISOs default to `/var/lib/libvirt/boot/harbour`, both on the system SSD. File upload is limited to 16 GiB per ISO. NAT gives guests outbound network access; the guest's private address is not directly reachable from other LAN computers. Bridged networking, UEFI/Secure Boot and PCI passthrough are not included in this wizard. Windows guests may require VirtIO network drivers.

Console connections use the same origin and owner session as Harbour, including WSS over HTTPS. VNC listens only on loopback. No public VNC port, separate console password or externally hosted scripts are used. Signing out or session expiry closes the console.

## Validation

On the physical NAS, a checksum-verified Alpine Linux installer was uploaded using Harbour's API. Harbour created a 2-core, 1 GiB RAM, 8 GiB virtual-disk guest. Chromium connected to noVNC and sent keyboard input to log in and install Alpine. After ejecting the ISO and selecting disk-first boot, the guest booted from its ext4 virtual disk, accepted login and acquired a DHCP address on the NAT network. The Settings panel and populated creation wizard were checked in Chromium. Both HTTP WebSocket and HTTPS WSS RFB handshakes passed; unauthenticated and foreign-origin requests were rejected.

The bundled browser client is noVNC 1.6.0 (MPL-2.0); source and license notices are under `harbor/web/vendor/novnc`.
