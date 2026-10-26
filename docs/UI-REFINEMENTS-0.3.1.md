# Harbour OS 0.3.1 — desktop and progress notes

## App installation and drive setup

App installs, start/stop operations, and confirmed storage creation now open a dedicated progress window. It shows the job name, real backend stage, stage history, elapsed time, completion or failure, and the actual error when an operation stops. It does not invent download percentages. App steps cover configuration validation, image download/extraction and container startup. Drive setup covers disk identity/health checks, preparing the confirmed disks, creating RAID/filesystem, mounting storage and saving boot configuration.

**Run in background** minimizes the window without canceling the operation. The enlarged top-bar task button shows a running-task count and reopens task details, including after a browser refresh. Completed and failed jobs remain available while the management service keeps its in-memory history. The progress window updates only when job details change, so polling does not continually replace its buttons. Time elapsed updates independently.

Storage completion means the storage creation job has finished. RAID initialization can continue in the background; the completion message directs the user to Storage for its actual state. The existing disk-erasure confirmation, protected-device checks and member permissions remain enforced. No cancellation or automatic retry is offered for partially completed disk operations.

## Widgets and navigation

- Shared spacing, rounded dark surfaces, consistent outline icons and quieter borders keep the black/white/green theme.
- CPU gauges have clearer percentage typography and temperature details. RAM now shows used and total memory.
- Storage shows the volume name, health, used percentage, free space and total capacity. An unconfigured data volume no longer presents system-disk usage as configured NAS storage. Degraded health and drive advisories are distinguished from healthy state.
- Network labels separate Download and Upload, with clear rates, recent-history traces and the current chart scale.
- Top navigation uses larger SVG icons and 38–42 px controls, grouped Home/Settings navigation, a task indicator, and a proper account menu with separate Settings and Sign out actions.
- Responsive layouts and reduced-motion settings are preserved.

## Verification and delivery

All 23 automated tests pass, including running/completed/failed job stages, timestamp fields, error retention, new static assets, authentication, access controls and existing storage protections. A real Excalidraw install in the disposable VM produced Preparing → Checking application → Validating configuration → Downloading images → Starting containers → Complete, with timing fields. The recorded result is `ui-refinements-validation.json`.

Visual checks cover the refined dashboard, progress details, task picker, background/reopen behavior and the account menu. The NAS deployment checks for active jobs before restarting its web service, saves the previous application, and preserves existing accounts, storage and TLS identity. It does not recreate a RAID array or reboot the physical NAS.

The updated source archive and `harbour-0.3.1-amd64.iso` contain these changes. The ISO booted from a raw USB device in the disposable BIOS VM; its graphical management/installer services, fresh owner state, new assets and Linux executable headers were checked. See `ui-refinements-iso-validation.json`. The underlying installation flow and disk commands are unchanged from 0.3.0; a complete new disk installation was not repeated for this UI patch.

The 0.3.0 ISO remains available as the previous build. Follow `INSTALL-0.3.md` for the same graphical installation procedure; use the 0.3.1 filename/checksum. Existing ZimaOS parity limits in `RELEASE-0.3.md` still apply.
