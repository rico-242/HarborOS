# Install Harbour OS 0.3.0

Use `dist/harbour-0.3.0-amd64.iso` on an x86-64 PC. The ISO supports UEFI and legacy BIOS. Disable Secure Boot for this unsigned development release. Use at least 4 GB RAM (8 GB recommended), a monitor and keyboard for first setup, and a separate system disk of at least 16 GiB. An Ethernet connection with DHCP is recommended.

1. Verify the ISO against its `.sha256` file. Write it to a USB using a raw/DD image-writing mode, or attach it as a VM DVD.
2. Boot the USB. Harbour opens a graphical welcome screen. **Try it first** opens the live desktop; its settings disappear when the live session ends.
3. Choose **Install Harbour OS**. Select the system disk, review its model, serial and size, then acknowledge erasure. **Installation permanently erases the selected system disk.** Mounted devices and the live USB are excluded. Separate data disks are configured later.
4. Wait for the completion screen, shut down, remove the USB and start the computer.
5. On the computer's graphical screen, create the owner username and password, confirm the password and finish the tour. There is no setup code. First account creation is deliberately available only from the local console.
6. From another device, open `https://<computer-IP>:8443/` and sign in with that account. The local console displays the IP and certificate fingerprint on the text console if needed. HTTPS uses a device-generated certificate; review and trust it yourself in your browser.
7. Use **Storage → Create storage** to choose separate data disks and a RAID mode. Read the disk-erasure confirmation carefully. Then create shared folders in Sharing and install apps from App Store. Internet access is required to download app images.

Members start with no folder access. The owner grants Read only or Read and write access per folder in Sharing. SMB uses the same usernames and passwords. Changing a folder's permissions reconnects its active SMB sessions. Disabled members lose both web and SMB access.

The console's Chromium session runs as a locked, unprivileged display account. It does not sign in automatically as the owner. On the live USB only, tty2 and the serial console provide root rescue access. Installed systems remove that live autologin configuration.

Power and package controls are owner-only and ask for explicit confirmation. They interrupt file sharing/apps when used. Package updates use Debian's signed repositories; they are separate from future Harbour application releases.

The existing NAS is available at https://192.168.1.97:8443/ and keeps its existing owner and TLS identity. Do not use the ISO to reinstall that NAS merely to get the updated interface.
