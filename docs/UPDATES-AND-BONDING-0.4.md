# Harbour OS 0.4.0: in-place updates and Ethernet bonding

## Updating without an ISO

Use **Settings → Updates → Upload signed update**. Choose a `.harbour-update` file, review the verified version and release notes, then type `UPDATE <version>` to install. The web console restarts; sign in again when it returns. Its durable update job remains in Background tasks.

Harbour validates the pinned Ed25519 signing key, signed manifest, payload/file hashes, version, architecture and supported Debian base. It stages application files, backs up the previous application/helper files, switches the application directory, and checks the new web service. A failed health check restores the previous release. **Restore previous release** provides an explicit rollback. Interrupted activation recovery runs before the web service and before network recovery at boot. Accounts, shared folders, snapshots, container data and the data volume are outside the update payload.

The same page retains **Debian & kernel packages**, using Debian's signed repositories. Some Debian/kernel changes require restarting the appliance; they do not require reinstalling an ISO. Harbour rollback restores Harbour application/helper files, not Debian packages, the kernel, network choices already confirmed, or user data. This is a versioned application/helper updater with recovery, not an atomic A/B disk-image system. Major Debian-base migrations are not automated in this release.

Installations made with the older 0.3.1 ISO need a **one-time updater bridge** because those images did not contain the verifier or a trusted release key. This has been installed on the existing NAS over its authenticated SSH connection. Other older installations can use the source archive's `os/install-maintenance.sh` and `tools/bootstrap-maintenance-nas.sh` through an owner-controlled SSH session; inspect the script and version guard first. The bootstrap script is intended for the known 0.3.1 layout and requires the source staged under `/DATA/harbor/source`, not a generic third-party Linux system. No disk reinstall is involved. New images built from the current source install the updater directly.

The public key is `os/release-public.pem`; the appliance pins it at `/etc/harbor/update-public.pem`. Its SHA-256 fingerprint is:

`1020c7c04258cdd7ba422f68a0bc5d40bd396beb31cd01673f8564a2891fb12c`

For another **0.3.1** installation, copy the source archive to `/tmp/harbor-source.tar.gz` over its authenticated SSH connection, then run on that appliance:

```sh
sudo mkdir -p /DATA/harbor/source
sudo tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
sudo sh /DATA/harbor/source/tools/bootstrap-maintenance-nas.sh
```

The bridge prompts privately for the existing Harbour owner password, checks the 0.3.1 baseline and active jobs, saves the old application, and pins the public key. It leaves the running release labeled 0.3.1 until you upload/install the signed 0.4.0 bundle from Settings → Updates. Compare the public-key fingerprint above before trusting copied source. Do not run the 0.3.1 bootstrap again on an appliance already using signed releases.

The private signing key stays on the development PC under `.local/signing/harbour-release-private.pem`, excluded from source/update archives. Keep a protected backup: it is needed to sign future releases. Never commit it or attach it to a public release. Update bundles cannot replace the trusted key. Key rotation requires a separate trusted local/SSH maintenance step.

To build a future update, change `VERSION` in `harbor/server.py`, then run:

```sh
python -m pip install -r tools/requirements.txt
python tools/build-update.py --version 0.4.1 --key /protected/path/harbour-release-private.pem --notes "Release notes"
```

The builder requires the private key matching the source's public key. It refuses to overwrite an existing key or include one from published source directories. The `--generate-key` option is only for the initial release identity, not each update.

## GitHub later

Local signed updates work without GitHub. Per the chosen setup, no repository or token is configured and nothing has been published remotely.

When ready, create a public GitHub repository, publish a stable release tagged `v<version>`, and attach `harbour-<version>-amd64.harbour-update` plus its `.sha256` file. Enter `owner/repository` in **Settings → Updates → GitHub Releases**. **Check Harbour releases** discovers the latest stable release; **Download & verify** stages its bundle, and installation still requires owner confirmation. Only official GitHub HTTPS/API/asset hosts are accepted, and a GitHub account or checksum alone cannot bypass the pinned signature.

Private GitHub repositories and unattended installation are not implemented. The public-repository client is prepared; an end-to-end published-repository test awaits your repository choice. The design follows [GitHub's Releases API](https://docs.github.com/en/rest/releases/releases) and [OpenSSL Ed25519 verification](https://docs.openssl.org/3.0/man1/openssl-pkeyutl/).

## Link aggregation / NIC teaming

Use **Settings → Network → Create network bond**. Two to eight available Ethernet adapters are required. Docker bridges, wireless adapters and interfaces already attached to another master are excluded. Hardware identity is checked again just before changes apply.

- **Active / backup:** one active adapter, another ready for failover; no special switch aggregation setup is required.
- **LACP (802.3ad):** configure the switch ports as the same LACP group first. Adapters must use matching speeds and full duplex. LACP balances traffic across connections; one connection generally remains limited to one member's speed. See the [Linux bonding documentation](https://www.kernel.org/doc/html/latest/networking/bonding.html).

Choose the primary adapter and either DHCP or a static IPv4 address/gateway/DNS. DHCP uses the primary adapter's MAC on `bond0`, but the router may still assign a different IP. Changes briefly interrupt traffic. Reconnect and select **Keep this connection** within the approximately two-minute window. Otherwise the independent rollback timer restores the previous configuration. An unconfirmed change is also restored before networking starts after a reboot. **Revert now** performs immediate restoration. Removing a bond uses the same guarded confirmation process.

The current NAS has one physical Ethernet adapter, so its bonding button remains disabled until another adapter is connected. Its existing IP and NIC configuration were preserved. Active/backup creation, DHCP, member failover, confirmed removal, persistence over reboot, timed rollback and boot recovery were tested using two NICs in the disposable VM. The kernel LACP mode and timeout rollback were tested; there is no managed LACP switch in that test, so switch negotiation and aggregate throughput are not claimed.

Updates and network changes share a maintenance guard. A pending network change must be confirmed or reverted before another system job can start. The graphical local console remains available if LAN access changes.

## Validation

The recorded VM results include successful signed upgrade, explicit rollback and re-upgrade, preserved owner/storage, recovery from an intentionally unhealthy signed release, confirmed bond persistence and recovery of unconfirmed network changes at boot. A simulated interrupted-update journal also exercised the recovery handler and stale-job cleanup. Test-only unhealthy bundles were kept outside release artifacts and were never installed on the NAS. See `maintenance-validation.json` and `maintenance-nas-validation.json` for the final results.
