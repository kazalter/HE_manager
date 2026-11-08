"""Open build downloads with fresh GitHub redirects and bounded HTTP retries.

Callers must still verify their pinned checksum before using the downloaded file.
"""
import time
import urllib.error
import urllib.parse
import urllib.request


def open_download(url, timeout=90):
    parsed = urllib.parse.urlsplit(url)
    github_asset = parsed.hostname == 'github.com' and '/releases/download/' in parsed.path
    for attempt in range(3):
        request_url = url
        if github_asset:
            query = dict(urllib.parse.parse_qsl(parsed.query))
            query['download'] = '1'
            if attempt:
                query['retry'] = str(time.time_ns())
            request_url = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))
        request = urllib.request.Request(request_url, headers={'User-Agent': 'HE-Manager-Build'})
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
