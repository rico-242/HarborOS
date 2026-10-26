# App uninstall (0.5.2)

Owners can uninstall from Settings → Apps, the App Store's installed entries, or an installed app's details. Each action opens a confirmation dialog requiring `UNINSTALL app-id`, then shows progress. Members cannot manage applications.

Compose apps use `down` without volume or image deletion flags. Legacy single-container installations use `docker rm --force` without removing volumes. App files, shared media, Docker volumes and images are retained. The last Compose definition is saved as `compose.uninstalled.json`; it can contain app environment secrets and stays in the protected state directory, not in a public export. Successful removal clears the installed state and the app is available to reinstall. Failed removal retains configuration and installation metadata for retry.

Keeping data does not replace backup. Reinstalling with the same app paths and named volumes can reuse their data; anonymous volumes are preserved but are not automatically reattached by Compose. Uninstall does not offer permanent data or image cleanup in this version.

Validation: 56 unit/integration tests, JavaScript syntax checks, and a disposable real Docker project checking container removal, preserved bind/named-volume data, retained image/configuration and updated app state. Existing user apps remain in place. Signed upgrades preserve owner, storage and network configuration.

Docker behavior: https://docs.docker.com/reference/cli/docker/compose/down/
