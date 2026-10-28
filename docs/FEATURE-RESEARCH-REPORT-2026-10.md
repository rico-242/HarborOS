# Harbour OS feature research and app-catalog report

**Date:** 2026-10-27  
**Scope:** Feature ideas for a simple, green-accent NAS experience; app-catalog strategy; implementation priorities. This is a research report, not an authorization to install apps or alter storage.

## Executive summary

Harbour already has the right foundation: a graphical storage manager, Hybrid pools, SMART warnings, remote updates, signed releases, app settings, external-disk access, and a Zima-like file/app experience. The strongest next step is not copying every feature from a larger NAS. It is adding the safety and discoverability layers that make those features trustworthy: tested app metadata, backup/snapshot workflows, notifications, recovery, and a catalog that can be updated without shipping a full OS image.

## What the reference platforms show

### ZimaOS / CasaOS

ZimaOS documents RAID 0/1/5/6, optional ZFS, SMB access, per-user permissions, and selective backup to Google Drive, Dropbox, or OneDrive. This is a useful target for Harbour's simple storage flow and cloud-copy wizard. [ZimaOS feature documentation](https://www.zimaspace.com/docs/zimaos/features)

The official ZimaOS store source is public as `IceWhaleTech/CasaOS-AppStore`. Its v2 format is a static HTTPS catalog with `store-config.json`, language metadata, one Compose manifest per app, icons/screenshots, stable IDs, categories, versions, release notes, and links to documentation/support. This is a strong fit for Harbour because catalog refreshes can be signed and delivered independently from the OS. [Official store source](https://github.com/IceWhaleTech/CasaOS-AppStore) · [v2 store format](https://github.com/IceWhaleTech/CasaOS-AppStore/blob/main/docs/quick-start/overview.md)

### TrueNAS SCALE

TrueNAS separates the catalog from the management UI and exposes app support level, documentation, permissions, categories, and update information. Its current catalog prominently includes Jellyfin, Plex, Immich, Nextcloud, Tailscale, Sonarr, Radarr, qBittorrent, Nginx Proxy Manager, and Syncthing, then extends into home automation, backup, developer tools, AI, games, and niche services. [TrueNAS Apps](https://apps.truenas.com/)

The lesson for Harbour is a tiered catalog: **Harbour verified**, **community reviewed**, and **unverified/custom**, with explicit permissions and health checks instead of presenting every Compose file as equally safe.

### OpenMediaVault

OpenMediaVault emphasizes modular plugins, Debian package updates, scheduled jobs, certificates, DNS-SD, link aggregation, Wake-on-LAN, SMB/NFS/rsync, quotas, ACLs, Btrfs snapshots/scrubs, SMART, email notifications, UPS, antivirus, cloud sync, and a web SSH console. [OMV feature list](https://www.openmediavault.org/?page_id=1562) · [OMV plugins](https://www.openmediavault.org/features.html)

The lesson is to make operational features composable and optional. Harbour should keep the default install small, then offer first-party modules for backup, notifications, UPS, and network services.

### Unraid and community catalogs

Unraid demonstrates the value of a very large community catalog: thousands of applications are searchable and installable from one place. [Unraid Community Apps](https://unraid.net/community/apps)

The trade-off is catalog quality and maintenance. Harbour should support community catalogs, but isolate them, show maintainer/update age, require explicit permissions, and run preflight validation before installation.

## App-catalog findings

The most reusable catalog model is the Zima v2 model: static JSON plus Compose manifests and assets served over HTTPS. Harbour can consume that format while adding its own signed Harbour manifest fields:

| Field | Purpose |
|---|---|
| Stable app ID and semantic version | Safe identity and update comparison |
| Architectures | Prevent installing an incompatible image |
| Maintainer, source, docs, support | Accountability and troubleshooting |
| Permissions/capabilities | Show host paths, devices, ports, network, and privileged access before install |
| Storage profile | Keep config/database on the OS SSD by default and data on an explicitly selected pool/share |
| Health checks | Detect startup failures such as missing paths or failed dependencies |
| Backup/restore metadata | Tell Harbour what must be captured before an update |
| Release notes and update age | Help users choose whether to update |
| Signature and content hash | Prevent catalog or Compose tampering |

Recommended initial categories: **Files & Cloud**, **Media**, **Photos**, **Backup & Sync**, **Networking**, **Security**, **Home Automation**, **Development**, **Databases**, **Monitoring**, **AI**, and **Games**.

Recommended first-party/verified set, subject to image licensing and maintenance checks: Jellyfin, Plex, Immich, Nextcloud, Syncthing, Tailscale, Pi-hole/AdGuard Home, qBittorrent, Transmission, Nginx Proxy Manager, Home Assistant, Paperless-ngx, Vaultwarden, Gitea/Forgejo, Uptime Kuma, Restic/Resticprofile, MinIO, Portainer, and a lightweight dashboard. OpenClaw and AnythingLLM should remain verified only while their storage and startup health checks pass.

## Proposed Harbour roadmap

### Tier 1 — high value, low-to-medium risk

1. **Signed catalog refresh and app lifecycle UI**: add catalog source management, verified/community labels, stale-catalog warnings, app update previews, bulk updates, rollback, and “why this permission is needed.”
2. **Backup center**: scheduled local backup, USB backup, rsync, S3-compatible targets, and optional Google Drive/Dropbox/OneDrive connectors. Include restore browsing and a dry-run preview.
3. **Snapshots and scrub center**: Btrfs snapshots, retention policies, scheduled scrubs, usage estimates, and one-click restore of a folder. Clearly distinguish snapshots from backups.
4. **Notifications**: in-app inbox plus email, webhook, and optional ntfy/ gotify channels for failing drives, degraded pools, failed app updates, failed backups, low space, and certificate expiry.
5. **App diagnostics**: per-app logs, dependency graph, health status, restart history, container resource usage, and a redacted “copy diagnostics” bundle.
6. **Network services polish**: VLAN-aware bonding UI, static DHCP/reservation hints, Wake-on-LAN, DNS-SD discovery, and a connection-test wizard.

### Tier 2 — high value, higher engineering cost

7. **UPS and safe shutdown** through NUT, with battery/runtime status and owner-confirmed shutdown policy.
8. **GPU/transcoding controls**: explicit device permission, hardware capability detection, and per-app GPU assignment.
9. **Search and indexing**: opt-in file index with exclusions, duplicate finder, and media/document search. Keep indexing disabled by default on small systems.
10. **Remote access broker**: a Harbour-managed WireGuard/Tailscale-style path with MFA, device approval, and no inbound port-forward requirement.
11. **Virtual machines**: optional KVM/libvirt module with resource limits and snapshots; do not place this in the default install.
12. **Pool migration/expansion assistant**: explain which RAID layouts can expand, show the exact estimated capacity and risk, and provide a tested rollback/repair plan.

### Tier 3 — defer until demand is proven

13. ZFS-specific administration, deduplication, clustered storage, Kubernetes, mail hosting, and full antivirus scanning. These add substantial operational complexity and can conflict with Harbour's simplified UX.

## Guardrails for implementation

- Keep app configs/databases on the Harbour system SSD by default, with a visible per-app relocation control and free-space warning.
- Treat catalog manifests and update bundles as signed supply-chain inputs; pin image digests where possible.
- Keep destructive storage actions behind typed confirmations, show affected stable device IDs, and never let SMART warnings silently block an intentional user choice.
- Make backups and restore tests first-class. A backup that has never been restored should be marked “unverified.”
- Expose only the minimum host paths/devices requested by an app; show a permission diff on updates.
- Preserve the current light/dark green theme and reuse the existing process-window pattern for installs, updates, backups, scrubs, and restores.

## Recommended decision set

For the next Harbour milestone, implement **Tier 1 items 1–5**, plus the UPS module from Tier 2 if the target hardware has a UPS. In parallel, create a Harbour-compatible catalog repository using the Zima v2 manifest shape, add signing and CI validation, and initially publish a small verified catalog rather than importing the entire community catalog. This delivers the largest reliability improvement without turning Harbour into a Kubernetes distribution.

## Sources

- [ZimaOS features](https://www.zimaspace.com/docs/zimaos/features)
- [ZimaOS/CasaOS official app-store repository](https://github.com/IceWhaleTech/CasaOS-AppStore)
- [Zima/CasaOS v2 store quick start](https://github.com/IceWhaleTech/CasaOS-AppStore/blob/main/docs/quick-start/overview.md)
- [TrueNAS Apps Market](https://apps.truenas.com/)
- [OpenMediaVault feature list](https://www.openmediavault.org/?page_id=1562)
- [OpenMediaVault plugins](https://www.openmediavault.org/features.html)
- [Unraid Community Apps](https://unraid.net/community/apps)
