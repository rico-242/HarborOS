# Jellyfin installation fix (0.5.1)

The pinned official Jellyfin container definition includes optional Raspberry Pi OpenMAX libraries (`/opt/vc/lib`) and video devices alongside `/dev/dri`. Docker refused to create the container on amd64 hardware when the Pi library directory was absent.

The Harbour adapter now omits missing entries only from the standard Jellyfin definition's explicit optional-hardware allowlist. It keeps available hardware, including the NAS's Intel GPU, and does not fabricate empty library directories or omit arbitrary required host mounts. The catalog snapshot remains unchanged. The app dialog lists compatibility adjustments separately from access approvals.

Regression tests cover absent hardware, an available GPU, all optional hardware present, catalog immutability, and preservation of unknown mounts and devices. The full suite passes 52 tests. Signed upgrades continue to preserve owner, storage and network configuration. The NAS installation was retried and Jellyfin's health endpoint returned HTTP 200.

Jellyfin is served at the catalog's published HTTP port, 8097. Complete Jellyfin's own first-run setup after installation. Hardware passthrough availability does not itself configure or validate media transcoding; choose the appropriate acceleration settings inside Jellyfin if needed.

Upstream image documentation: https://docs.linuxserver.io/images/docker-jellyfin/
