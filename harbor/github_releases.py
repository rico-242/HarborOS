"""Bounded GitHub release requests; credentials never follow asset redirects."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z')
ASSET_HOSTS = ('release-assets.githubusercontent.com', 'objects.githubusercontent.com')


def official_url(url, hosts):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.netloc != parsed.hostname
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError('Use an official GitHub HTTPS release URL.')
    return parsed


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, asset=False):
        self.asset = asset
        super().__init__()

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not self.asset:
            raise ValueError('The GitHub repository moved. Update its owner/repository setting.')
        official_url(newurl, ASSET_HOSTS)
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is not None:
            for name in ('Authorization', 'Cookie', 'Proxy-Authorization', 'X-GitHub-Api-Version'):
                redirected.remove_header(name)
            redirected.add_header('Accept', 'application/octet-stream')
        return redirected


def github_open(url, token=None, asset=False):
    parsed = official_url(url, ('api.github.com', 'github.com'))
    if token and parsed.hostname != 'api.github.com':
        raise ValueError('GitHub credentials can only be sent to its API.')
    headers = {'Accept': 'application/octet-stream' if asset else 'application/vnd.github+json',
               'User-Agent': 'Harbour-OS-Updater', 'X-GitHub-Api-Version': '2022-11-28'}
    request = urllib.request.Request(url, headers=headers)
    if token:
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_]{20,255}', token):
            raise ValueError('Enter a valid GitHub access token without spaces or line breaks.')
        request.add_unredirected_header('Authorization', 'Bearer ' + token)
    try:
        return urllib.request.build_opener(GitHubRedirect(asset)).open(request, timeout=30)
    except urllib.error.HTTPError as error:
        code = error.code
        limited = error.headers.get('X-RateLimit-Remaining') == '0' or code == 429
        error.close()
        if limited:
            message = 'GitHub rate limit reached. Wait before checking again.'
        elif code == 401:
            message = 'GitHub rejected the saved token. Replace it if expired or revoked.'
        elif code == 403:
            message = 'GitHub denied access. Grant this repository Contents: read access and any required organization approval.'
        elif code == 404:
            message = 'GitHub could not find this repository or asset. Check its name and the token’s access to the private repository.'
        else:
            message = 'GitHub could not complete the request (HTTP ' + str(code) + '). Try again later.'
        raise ValueError(message) from None
    except (urllib.error.URLError, OSError):
        raise ValueError('Unable to reach GitHub securely. Check the NAS internet connection, clock and DNS, then try again.') from None


def github_json(url, token=None):
    with github_open(url, token) as response:
        raw = response.read(2 * 1024**2 + 1)
    if len(raw) > 2 * 1024**2:
        raise ValueError('The GitHub release metadata exceeds 2 MiB.')
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('GitHub returned invalid release metadata.') from None
