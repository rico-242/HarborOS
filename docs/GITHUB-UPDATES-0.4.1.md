# GitHub updates — Harbour OS 0.4.1

The public repository is **rico-242/HarborOS**. The Updates page can check private releases, download and verify a bundle, and install it with owner confirmation. No ISO reinstall is needed. Debian/kernel package checks remain separate on the same page; no unattended installation is enabled.

## Public repository: no sign-in needed

The repository and release assets are public. Harbour defaults to `rico-242/HarborOS`, with experimental releases included because current Harbour versions are prereleases. Open **Settings → Updates → Check for updates**. If you have a saved source, use **Manage GitHub access**, enter `rico-242/HarborOS`, select **Public access / remove saved token**, enable **Include experimental releases**, and save.

Anyone can download the signed bundle or installer baseline from [GitHub Releases](https://github.com/rico-242/HarborOS/releases) without authenticating. Public download access does not change NAS owner sign-in or signature verification.

## Optional private repository

A different private repository can use a fine-grained GitHub token. Select only that repository and grant **Contents: read-only**, choose an expiration, then enter it directly into the NAS's **Manage GitHub access → Add or replace token** password field. Do not paste it into chat, source files, or issues. GitHub may require password/2FA verification or organization approval. The public HarborOS repository does not need this setup, and the NAS never receives your publishing credential.

## Future upgrades

Select **Check for updates → Download & verify → Review & install**. These actions are also available as each Background task completes. Read the notes and type `UPDATE <version>` to install. The web service briefly restarts; sign in again when it returns. If its health check fails, the independent updater restores the previous application. Existing account, application and storage data remain outside the signed payload.

The first 100 published releases are checked. Stable mode excludes prereleases and drafts; experimental mode includes prereleases but still excludes drafts. The highest numeric release tag with a matching amd64 bundle is offered. A repository with no matching stable release returns an explanation rather than an authentication error. Release metadata alone never authorizes installation: the pinned signature, hashes, architecture, Debian base, minimum version, and signed version are checked before installation.

## Token handling

The token is write-only in the UI and API. It lives at `/var/lib/harbor/release-updates/github-credential.json` with owner-only file mode `0600`, inside a `0700` directory. It is stored as a protected local secret, not encrypted independently of the operating system: root access to the NAS can read it. It is never part of a signed bundle, source archive, Git history, release notes or job result.

Authorization is sent only to `api.github.com`. Private assets use GitHub's asset API with an octet-stream request. Redirects are limited to GitHub's known HTTPS asset hosts, and authentication headers are removed before following them. Downloads have bounded size, exact-length checks, optional GitHub digest checks, and mandatory Harbour signature verification.

Use **Manage GitHub access** to replace an expired/revoked token, remove it for public access, or leave the repository blank to disconnect. Changing repositories removes the previous token unless a new one is supplied. Source/token/channel changes clear cached update results and cannot run while another task is active. Revoke the token in GitHub as well if it is no longer needed. A 401/403/404 or rate-limit response produces an actionable message without exposing the token.

## Publishing the next release

Build and sign bundles on the development computer using the protected private signing key. Publish a GitHub release tagged `v<version>` with `harbour-<version>-amd64.harbour-update` and its SHA-256 file attached. Experimental builds should remain prereleases. Never upload the private key or a GitHub token. The current 0.3.1 ISO is a separately labeled baseline; 0.4.1 is an in-place update, not a newly tested ISO.

GitHub's primary documentation: [fine-grained tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens), [release permissions](https://docs.github.com/en/rest/releases/releases), [private asset downloads](https://docs.github.com/en/rest/releases/assets).
