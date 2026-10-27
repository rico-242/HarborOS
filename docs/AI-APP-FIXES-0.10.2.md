# OpenClaw and AnythingLLM startup fixes

AnythingLLM runs as UID/GID 1000 in the pinned official image. Harbour's restrictive service umask created its storage bind directory as root-owned mode 0700. Prisma could not open its SQLite database, so the container restarted repeatedly. Install and Start now prepare only AnythingLLM's dedicated storage root for UID/GID 1000, retaining owner-only access. Existing files are not deleted or recursively reassigned, and shared folders or symlinked storage cannot be taken over.

OpenClaw uses a one-shot setup service before its gateway. That helper exits successfully by design. Harbour previously required every project container to be running and therefore labelled the healthy gateway as stopped. App status now recognizes successful service_completed_successfully dependencies, keeps failed helpers and stopped daemons visible, ignores ad-hoc one-off containers and reports restart loops explicitly.

The physical NAS diagnosis confirmed SQLite permission errors for AnythingLLM, while OpenClaw's gateway was already running and serving its dashboard. Correcting AnythingLLM's directory owner restored HTTP 200. OpenClaw's normal gateway-token sign-in remains enabled. Provider keys and OpenClaw authentication settings were not changed.
