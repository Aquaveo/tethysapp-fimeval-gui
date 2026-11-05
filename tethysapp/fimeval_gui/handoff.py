"""FIMEVAL-BE52: receive the "Run in FIMeval" handoff from FIMbench.

FIMbench links to ``/handoff/fimeval-gui/run-evaluation/?benchmark_url=…&benchmark_name=…``
(Tethys Handoff API; query params only, no file bodies). FIMbench serves its
benchmarks from the public SDML S3 bucket while FIMeval keeps its own object
store, so the handler copies the benchmark server-side: stream it down, check
it, and put it at the usual upload prefix as ``benchmark.tif`` so the submit
endpoint and the worker find it exactly as if the browser had uploaded it.

The handler returns a URL; Tethys's HandoffManager issues the redirect. Every
failure becomes a redirect into the SPA with ``?from=fimbench&error=<code>``
rather than a 500, so the user lands in FIMeval with a message (FIMEVAL-FE65).
"""
import json
import logging
import os
import tempfile
import uuid
from urllib.parse import unquote, urlencode, urlsplit

import requests
from botocore.exceptions import BotoCoreError, ClientError
from django.urls import reverse

from tethysapp.fimeval_gui.app import App
from tethysapp.fimeval_gui.controllers import (
    MAX_UPLOAD_BYTES, RASTER_EXT, _get_storage, _upload_prefix,
)

logger = logging.getLogger(__name__)

# Where FIMbench's benchmark rasters live. Overridable per deployment through the
# ``handoff_allowed_hosts`` custom setting (comma-separated host names).
DEFAULT_ALLOWED_HOSTS = ('sdmlab.s3.amazonaws.com',)

_TIFF_MAGIC = (b'II*\x00', b'MM\x00*')
_CHUNK = 1 << 20  # 1 MiB


class _HandoffError(Exception):
    """Carries the short error code that ends up in the redirect URL."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _allowed_hosts():
    try:
        raw = App.get_custom_setting('handoff_allowed_hosts')
    except Exception:  # setting missing on an older portal config
        raw = None
    hosts = [h.strip().lower() for h in (raw or '').split(',') if h.strip()]
    return set(hosts) if hosts else set(DEFAULT_ALLOWED_HOSTS)


def _spa_url(**params):
    return reverse('fimeval_gui:home') + '?' + urlencode(params)


def _check_url(benchmark_url):
    parts = urlsplit(benchmark_url or '')
    if parts.scheme not in ('https', 'http') or not parts.netloc:
        raise _HandoffError('bad_url')
    if os.path.splitext(parts.path)[1].lower() not in RASTER_EXT:
        raise _HandoffError('bad_url')
    if parts.hostname.lower() not in _allowed_hosts():
        raise _HandoffError('not_allowed_host')
    return parts


def _download(benchmark_url, dest):
    """Stream ``benchmark_url`` into the open file ``dest`` with a size cap and a
    TIFF magic check on the first bytes. Raises _HandoffError on any problem."""
    try:
        with requests.get(benchmark_url, stream=True, timeout=(10, 60)) as resp:
            resp.raise_for_status()
            declared = resp.headers.get('Content-Length')
            if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
                raise _HandoffError('too_large')
            total = 0
            first = True
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                if not chunk:
                    continue
                if first:
                    if chunk[:4] not in _TIFF_MAGIC:
                        raise _HandoffError('not_a_tiff')
                    first = False
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise _HandoffError('too_large')
                dest.write(chunk)
            if first:  # empty body
                raise _HandoffError('not_a_tiff')
    except _HandoffError:
        raise
    except requests.RequestException as exc:
        logger.warning('handoff: could not fetch %s: %s', benchmark_url, exc)
        raise _HandoffError('unreachable') from exc
    dest.flush()
    dest.seek(0)


def run_evaluation(request, benchmark_url=None, benchmark_name=None, **_ignored):
    """Handoff handler: stage ``benchmark_url`` as a new upload for ``request.user``
    and return the SPA URL to open (``?upload_id=…&from=fimbench&benchmark_name=…``)."""
    if not benchmark_url:
        # Tethys turns a TypeError from the handler into HTTP 400.
        raise TypeError('benchmark_url is required')
    try:
        parts = _check_url(benchmark_url)
        # Name the benchmark from the .tif itself (e.g. ``AI_…_BM.tif``), never
        # from ``benchmark_name``: FIMbench sends its site ID there, which has no
        # "BM" token and would fail the BE37 benchmark-name check.
        display_name = unquote(os.path.basename(parts.path))
        upload_id = str(uuid.uuid4())
        prefix = _upload_prefix(str(request.user.id), upload_id)
        with tempfile.TemporaryFile() as tmp:
            _download(benchmark_url, tmp)
            try:
                storage = _get_storage()
                storage.upload_fileobj(tmp, f'{prefix}benchmark.tif')
                # Same shape the presign endpoint writes, so the submit-time BM
                # check and the worker's input labels work unchanged (BE37/BE30).
                storage.upload_bytes(
                    json.dumps({
                        'names': {'benchmark.tif': display_name},
                        'source': 'fimbench',
                        'benchmark_url': benchmark_url,
                    }).encode('utf-8'),
                    f'{prefix}manifest.json',
                )
            except (ClientError, BotoCoreError) as exc:
                logger.error('handoff: storage write failed for %s: %s', upload_id, exc)
                raise _HandoffError('storage') from exc
    except _HandoffError as exc:
        return _spa_url(**{'from': 'fimbench', 'error': exc.code})
    return _spa_url(upload_id=upload_id, **{'from': 'fimbench'}, benchmark_name=display_name)
