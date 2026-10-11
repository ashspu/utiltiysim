"""Authenticated private producer readiness probe; never prints credentials."""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(origin, token, timeout=5):
    parsed = urlsplit(origin)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('Readiness requires a fixed TLS or loopback origin.')
    if not isinstance(token, str) or len(token) < 32 or '\r' in token or '\n' in token:
        raise ValueError('Private gateway credential is required.')
    request = Request(origin.rstrip('/') + '/hosted/health', headers={'Authorization': 'Bearer ' + token})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(16385)
        if response.status != 200 or len(raw) > 16384:
            raise ValueError('Producer did not return bounded readiness.')
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get('status') != 'ready':
            raise ValueError('Producer is not ready.')
        return {'status': 'ready'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='http://127.0.0.1:8080')
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--timeout', type=float, default=5)
    args = parser.parse_args()
    try:
        configured_file = os.getenv('UTILITYSIM_RUNTIME_TOKEN_FILE')
        configured_value = os.getenv('UTILITYSIM_RUNTIME_TOKEN')
        if args.token_file is not None:
            token = args.token_file.read_text(encoding='utf-8').strip()
        elif configured_file:
            if configured_value:
                raise ValueError('Use exactly one credential source.')
            token = Path(configured_file).read_text(encoding='utf-8').strip()
        else:
            token = configured_value
        if not 0 < args.timeout <= 30:
            raise ValueError('Readiness timeout must be bounded.')
        print(json.dumps(probe(args.origin, token, args.timeout)))
    except (OSError, ValueError):
        print('Producer readiness unavailable.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
