"""Owner-managed GitHub source, write-only credentials and signed downloads."""
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from github_releases import REPO, github_open, github_json
from release_bundle import LIMIT, version


class GitHubSource:
    def source(self):
        with self.app.lock:
            config = json.loads(self.config.read_text()) if self.config.exists() else {'repository': 'rico-242/HarborOS', 'include_prereleases': True, 'id': 'harbour-public-v1'}
            credential = json.loads(self.credential.read_text()) if self.credential.exists() else {}
            token = credential.get('token') if credential.get('repository', '').lower() == config.get('repository', '').lower() else None
            return config, token

    def save_source(self, data):
        repo = data.get('repository', '')
        channel = data.get('include_prereleases', False)
        operation = data.get('token_action', 'keep')
        token = data.get('token', '')
        if not isinstance(repo, str) or repo.strip() and not REPO.fullmatch(repo.strip()):
            raise self.error('Use a GitHub owner/repository name.')
        repo = repo.strip()
        if not repo:
            operation, token = 'remove', ''
        if type(channel) is not bool or operation not in ('keep', 'set', 'remove'):
            raise self.error('Choose a valid release channel and token action.')
        if operation == 'set' and (not repo or not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_]{20,255}', token)):
            raise self.error('Enter a valid access token without spaces or line breaks, and choose its repository.')
        if operation != 'set' and token:
            raise self.error('Choose Replace token when supplying a new token.')
        with self.app.lock:
            self.app.system_settings.external_status()
            if any(j.get('state') in ('queued', 'running') for j in self.app.jobs.values()):
                raise self.error('Let the current task finish before changing the update source.', 409)
            previous, _ = self.source()
            if operation == 'set':
                self.atomic(self.credential, {'repository': repo, 'token': token})
                self.credential.chmod(0o600)
            elif operation == 'remove' or previous.get('repository', '').lower() != repo.lower() or not repo:
                self.credential.unlink(missing_ok=True)
            config = {'repository': repo, 'include_prereleases': channel, 'id': secrets.token_hex(16)}
            self.atomic(self.config, config)
            self.check_file.unlink(missing_ok=True)
            if os.name == 'posix':
                descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            return {'repository': repo, 'include_prereleases': channel, 'token_configured': bool(self.source()[1])}

    def check_github(self, config, token):
        repo = config['repository']
        experimental = config.get('include_prereleases', False)
        self.app.job_progress('Checking GitHub', 'Reading published releases using the configured repository access.')
        releases = github_json('https://api.github.com/repos/' + repo + '/releases?per_page=100', token)
        if not isinstance(releases, list):
            raise self.error('GitHub returned invalid release metadata.')
        choices = []
        for release in releases:
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease') and not experimental:
                continue
            tag = release.get('tag_name', '')
            if not isinstance(tag, str):
                continue
            tag = tag.removeprefix('v')
            try:
                target = version(tag)
            except ValueError:
                continue
            assets = release.get('assets', [])
            if not isinstance(assets, list):
                continue
            matches = [a for a in assets if isinstance(a, dict) and a.get('name') == 'harbour-' + tag + '-amd64.harbour-update']
            if len(matches) != 1:
                continue
            asset = matches[0]
            ident, size, digest = asset.get('id'), asset.get('size'), asset.get('digest')
            if type(ident) is not int or ident <= 0 or type(size) is not int or not 0 < size <= LIMIT or asset.get('state') != 'uploaded':
                continue
            if digest is not None and (not isinstance(digest, str) or not re.fullmatch('sha256:[a-f0-9]{64}', digest)):
                continue
            choices.append((target, {'version': tag, 'asset_id': ident, 'bytes': size, 'digest': digest,
                                    'prerelease': bool(release.get('prerelease')), 'notes': str(release.get('body') or '')[:16000]}))
        value = max(choices, key=lambda item: item[0])[1] if choices else {'version': None, 'notes': ''}
        value.update(repository=repo, source_id=config.get('id'), include_prereleases=experimental,
                     checked=datetime.now(timezone.utc).isoformat())
        value['available'] = bool(value['version'] and version(value['version']) > version(self.current))
        self.atomic(self.check_file, value)
        return value

    def download_github(self, checked, token):
        ident = secrets.token_hex(16)
        path = self.root / 'incoming' / (ident + '.bundle')
        self.app.job_progress('Downloading release', 'Fetching the release bundle through GitHub’s authenticated asset API.')
        try:
            asset_url = 'https://api.github.com/repos/' + checked['repository'] + '/releases/assets/' + str(checked['asset_id'])
            with github_open(asset_url, token, asset=True) as response, path.open('xb') as output:
                count = 0
                digest = hashlib.sha256()
                while chunk := response.read(1024**2):
                    count += len(chunk)
                    if count > LIMIT or count > checked['bytes']:
                        raise self.error('The release download exceeds its expected size.')
                    output.write(chunk)
                    digest.update(chunk)
                    self.app.job_progress('Downloading release', str(count // 1024) + ' / ' + str(checked['bytes'] // 1024) + ' KiB received.')
                output.flush()
                os.fsync(output.fileno())
            if count != checked['bytes']:
                raise self.error('The release download was incomplete. Check for updates and try again.')
            if checked.get('digest') and checked['digest'] != 'sha256:' + digest.hexdigest():
                raise self.error('The GitHub release asset checksum changed. Check for updates again.')
            self.app.job_progress('Verifying signature', 'Checking the pinned signing key and payload checksums.')
            candidate = self.stage(path, ident)
            if candidate['version'] != checked['version']:
                (self.root / 'candidates' / (ident + '.json')).unlink(missing_ok=True)
                raise self.error('The signed bundle version differs from the checked GitHub release.')
            return candidate
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def github_action(self, action, data):
        if action == 'source':
            return self.save_source(data)
        # Snapshot source and enqueue while locked: a new token/source cannot race an active job.
        with self.app.lock:
            config, token = self.source()
            repo = config.get('repository', '')
            if not REPO.fullmatch(repo):
                raise self.error('Choose a GitHub repository first, or upload a signed update bundle.', 409)
            if action == 'check':
                self.check_file.unlink(missing_ok=True)
                return self.app.job('Check Harbour releases', lambda: self.check_github(config, token), kind='release')
            if not self.key.exists():
                raise self.error('No trusted release key is installed.', 409)
            checked = json.loads(self.check_file.read_text()) if self.check_file.exists() else None
            if (not checked or not checked.get('available') or checked.get('source_id') != config.get('id')
                    or checked.get('repository') != repo or checked.get('include_prereleases') != config.get('include_prereleases', False)):
                raise self.error('Check for an available release from the current source first.', 409)
            return self.app.job('Download Harbour update', lambda: self.download_github(checked, token), kind='release')
