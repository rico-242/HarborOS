import hashlib
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import test_server as fixtures
import test_maintenance as bundles
from github_releases import GitHubRedirect, github_open, github_json

TOKEN = 'unit_test_read_only_token_1234567890'
REPOSITORY = 'rico-242/HarborOS'


class GitHubTransportTests(unittest.TestCase):
    def test_token_only_sent_to_api_and_never_copied_to_cdn(self):
        class Opener:
            def open(inner, request, timeout):
                self.assertEqual(request.get_header('Authorization'), 'Bearer ' + TOKEN)
                self.assertNotIn('Authorization', request.headers)
                self.assertEqual(request.get_header('Accept'), 'application/octet-stream')
                redirected = GitHubRedirect(True).redirect_request(request, None, 302, '', {}, 'https://release-assets.githubusercontent.com/example?signature=opaque')
                self.assertIsNone(redirected.get_header('Authorization'))
                self.assertEqual(redirected.get_header('Accept'), 'application/octet-stream')
                return io.BytesIO(b'asset')
        with patch('github_releases.urllib.request.build_opener', return_value=Opener()):
            self.assertEqual(github_open('https://api.github.com/repos/a/b/releases/assets/1', TOKEN, True).read(), b'asset')
        with self.assertRaises(ValueError):
            github_open('https://github.com/a/b/releases/download/v1/file', TOKEN, True)

    def test_unsafe_urls_and_redirects_are_rejected_before_credentials_leave(self):
        request = urllib.request.Request('https://api.github.com/repos/a/b/releases/assets/1')
        for url in ('https://evil.example/file', 'http://release-assets.githubusercontent.com/file',
                    'https://release-assets.githubusercontent.com:443/file', 'https://api.github.com/other',
                    'https://user@objects.githubusercontent.com/file', 'https://objects.githubusercontent.com/file#fragment'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                GitHubRedirect(True).redirect_request(request, None, 302, '', {}, url)
        with self.assertRaises(ValueError):
            GitHubRedirect().redirect_request(request, None, 302, '', {}, 'https://api.github.com/repos/new/name')
        for url in ('http://api.github.com/repos/a/b', 'https://api.github.com:8443/a', 'https://api.github.com@evil.example/a'):
            with self.assertRaises(ValueError):
                github_open(url, TOKEN)

    def test_errors_and_rate_limit_never_expose_token_or_response_body(self):
        for code in (401, 403, 404, 429, 500):
            error = urllib.error.HTTPError('https://api.github.com/?secret=' + TOKEN, code, TOKEN, {}, io.BytesIO(TOKEN.encode()))
            with patch('github_releases.urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(ValueError) as result:
                    github_open('https://api.github.com/repos/a/b/releases', TOKEN)
                self.assertNotIn(TOKEN, str(result.exception))
                self.assertNotIn('secret=', str(result.exception))

    def test_metadata_is_bounded_and_invalid_json_is_rejected(self):
        for data in (b'x' * (2 * 1024**2 + 1), b'not JSON'):
            with patch('github_releases.github_open', return_value=io.BytesIO(data)), self.assertRaises(ValueError):
                github_json('https://api.github.com/repos/a/b/releases', TOKEN)


class PrivateUpdateTests(unittest.TestCase):
    setUp = fixtures.ServiceTests.setUp
    tearDown = fixtures.ServiceTests.tearDown
    request = fixtures.ServiceTests.request
    setup_admin = fixtures.ServiceTests.setup_admin

    def owner(self):
        self.setup_admin()
        self.app.demo = False
        return self.app.releases

    def configure(self, **extra):
        data = {'action': 'source', 'repository': REPOSITORY, 'token_action': 'set', 'token': TOKEN}
        data.update(extra)
        status, value, _ = self.request('/api/os-updates/action', data)
        self.assertEqual(status, 202, value)
        return value

    def finish(self, job):
        for _ in range(150):
            result = self.app.jobs[job['id']]
            if result['state'] not in ('queued', 'running'):
                return result
            time.sleep(.01)
        self.fail('Job timed out')

    def release(self, target, prerelease=False, ident=17, size=20):
        return {'tag_name': 'v' + target, 'draft': False, 'prerelease': prerelease,
                'assets': [{'name': 'harbour-' + target + '-amd64.harbour-update', 'id': ident, 'size': size, 'state': 'uploaded'}]}

    def test_token_is_write_only_kept_removed_and_not_in_source_config(self):
        releases = self.owner()
        result = self.configure()
        self.assertTrue(result['token_configured'])
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn(TOKEN, releases.config.read_text())
        self.assertNotIn(TOKEN, json.dumps(self.request('/api/os-updates')[1]))
        self.assertNotIn(TOKEN, json.dumps(self.app.events))
        if os.name == 'posix':
            self.assertEqual(releases.credential.stat().st_mode & 0o777, 0o600)
            self.assertEqual(releases.root.stat().st_mode & 0o777, 0o700)
        self.configure(token_action='keep', token='', include_prereleases=True)
        self.assertEqual(releases.source()[1], TOKEN)
        self.configure(token_action='remove', token='')
        self.assertFalse(releases.credential.exists())
        self.assertFalse(releases.info()['token_configured'])

    def test_repository_change_and_disconnect_clear_old_token_and_check(self):
        releases = self.owner()
        self.configure()
        fixtures.module.atomic_json(releases.check_file, {'available': True})
        self.configure(repository='another/repo', token_action='keep', token='')
        self.assertIsNone(releases.source()[1])
        self.assertFalse(releases.check_file.exists())
        self.configure(repository='', token_action='remove', token='')
        self.assertFalse(releases.info()['repository'])

    def test_invalid_tokens_repositories_and_channels_leave_saved_settings_intact(self):
        releases = self.owner()
        self.configure()
        before = releases.credential.read_bytes()
        for change in ({'token': TOKEN + '\r\nInjected: yes'}, {'repository': 'https://github.com/a/b'},
                       {'include_prereleases': 'false'}, {'token_action': 'wrong'}, {'token_action': 'keep'}):
            data = {'action': 'source', 'repository': REPOSITORY, 'token_action': 'set', 'token': TOKEN}
            data.update(change)
            self.assertEqual(self.request('/api/os-updates/action', data)[0], 400)
            self.assertEqual(releases.credential.read_bytes(), before)

    def test_member_and_missing_csrf_cannot_read_or_replace_token(self):
        releases = self.owner()
        self.configure()
        self.assertEqual(self.request('/api/os-updates/action', {'action': 'source', 'repository': ''}, headers={'X-Harbor-CSRF': ''})[0], 403)
        self.app.demo = True
        self.request('/api/members', {'username': 'member', 'password': 'member-test-password'})
        self.app.demo = False
        _, value, headers = self.request('/api/login', {'username': 'member', 'password': 'member-test-password'})
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = value['csrf']
        self.assertEqual(self.request('/api/os-updates')[0], 403)
        self.assertEqual(self.request('/api/os-updates/action', {'action': 'source', 'repository': ''})[0], 403)
        for path in ('/github-credential.json', '/release-updates/github-credential.json', '/api/download?path=../../release-updates/github-credential.json'):
            self.assertGreaterEqual(self.request(path)[0], 400)
        self.assertTrue(releases.credential.exists())

    def test_stable_and_experimental_selection_use_highest_valid_version(self):
        releases = self.owner()
        self.configure()
        records = [self.release('0.4.2'), self.release('0.5.0', True), self.release('0.4.9'), self.release('0.5.1', True)]
        records += [dict(self.release('9.0.0'), draft=True), {'tag_name': 'vfoo', 'assets': []}]
        with patch('github_source.github_json', return_value=records) as fetch:
            result = self.finish(releases.action({'action': 'check'}))
            self.assertEqual(result['result']['version'], '0.4.9')
            fetch.assert_called_once_with('https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=100', TOKEN)
        self.configure(include_prereleases=True)
        with patch('github_source.github_json', return_value=records):
            self.assertEqual(self.finish(releases.action({'action': 'check'}))['result']['version'], '0.5.1')

    def test_no_stable_releases_is_successful_and_token_rotation_invalidates_download(self):
        releases = self.owner()
        self.configure()
        with patch('github_source.github_json', return_value=[self.release('0.5.0', True)]):
            result = self.finish(releases.action({'action': 'check'}))
            self.assertEqual(result['state'], 'completed')
            self.assertIsNone(result['result']['version'])
            self.assertFalse(result['result']['available'])
        self.configure(token=TOKEN + 'changed')
        self.assertFalse(releases.check_file.exists())
        with self.assertRaises(Exception):
            releases.action({'action': 'download'})

    def test_source_cannot_change_during_running_job(self):
        releases = self.owner()
        self.configure()
        self.app.jobs['active'] = {'state': 'running'}
        status, _, _ = self.request('/api/os-updates/action', {'action': 'source', 'repository': ''})
        self.assertEqual(status, 409)
        self.assertEqual(releases.source()[1], TOKEN)
        self.app.jobs['active']['state'] = 'completed'

    def test_download_uses_asset_api_and_still_requires_valid_signature(self):
        releases = self.owner()
        self.configure(include_prereleases=True)
        signed = bundles.SignedBundleTests()
        signed.setUp()
        self.addCleanup(signed.tearDown)
        content = signed.bundle().read_bytes()
        releases.key = signed.public
        releases.current = '0.3.1'
        record = self.release('0.4.0', True, size=len(content))
        record['assets'][0]['digest'] = 'sha256:' + hashlib.sha256(content).hexdigest()
        with patch('github_source.github_json', return_value=[record]):
            self.assertEqual(self.finish(releases.action({'action': 'check'}))['state'], 'completed')
        with patch('github_source.github_open', return_value=io.BytesIO(content)) as fetch:
            result = self.finish(releases.action({'action': 'download'}))
            self.assertEqual(result['state'], 'completed', result)
            self.assertTrue(result['result']['verified'])
            fetch.assert_called_once_with('https://api.github.com/repos/' + REPOSITORY + '/releases/assets/17', TOKEN, asset=True)
        self.assertNotIn(TOKEN, json.dumps(releases.info()))
        self.assertNotIn(TOKEN, json.dumps(self.app.jobs))
        releases.current = '0.4.1'
        self.assertEqual(releases.info()['candidates'], [])
        self.assertTrue(list((releases.root / 'candidates').glob('*.json')))

    def test_unsigned_incomplete_and_mismatched_releases_never_become_candidates(self):
        releases = self.owner()
        self.configure()
        signed = bundles.SignedBundleTests()
        signed.setUp()
        self.addCleanup(signed.tearDown)
        releases.key = signed.public
        releases.current = '0.3.1'
        good = signed.bundle().read_bytes()
        cases = [(b'unsigned', '0.4.0', len(b'unsigned')), (good[:-5], '0.4.0', len(good)), (good, '0.4.1', len(good))]
        for content, target, size in cases:
            with patch('github_source.github_json', return_value=[self.release(target, size=size)]):
                self.finish(releases.action({'action': 'check'}))
            with patch('github_source.github_open', return_value=io.BytesIO(content)):
                result = self.finish(releases.action({'action': 'download'}))
                self.assertEqual(result['state'], 'failed', result)
            self.assertEqual(list((releases.root / 'candidates').glob('*.json')), [])
            self.assertEqual(list((releases.root / 'incoming').glob('*.bundle')), [])
