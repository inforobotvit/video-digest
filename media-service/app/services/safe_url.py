"""Outbound URL guard (SSRF): the service fetches whatever address a user points it at, so every
address it opens must be public. Applied before yt-dlp sees a URL, on every redirect of the
direct-file lookup, and to the final URL that ffprobe reads (decision of 2026-09-17).

Rejected: schemes other than http/https; hosts that resolve to loopback, private, link-local
(169.254.0.0/16, the cloud metadata address included), multicast, reserved or unspecified
addresses, on any of the addresses a name resolves to; IPv4-mapped IPv6 forms of the same.
"""

import ipaddress
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

from app.config import Settings
from app.errors import ApiError

log = logging.getLogger(__name__)

MAX_REDIRECTS = 5
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")


def resolve_host(host: str) -> list[str]:
    """Every address the name resolves to; tests replace this to stay off the network."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ApiError("unsupported_url", f"host {host!r} does not resolve", 400) from exc
    return sorted({info[4][0] for info in infos})


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    # is_global covers the IANA special-purpose registries (private, loopback, link-local,
    # reserved, shared address space 100.64/10, documentation); multicast is excluded explicitly.
    return ip.is_global and not ip.is_multicast


def check_public_url(url: str) -> urllib.parse.SplitResult:
    """Raise unsupported_url (400) unless the URL is http(s) to a public address."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ApiError("unsupported_url", "only http and https links are accepted", 400)
    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ApiError("unsupported_url", "link has no host", 400)
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        raise ApiError("unsupported_url", "link points to a local address", 400)
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(a) for a in resolve_host(host)]
    for ip in addresses:
        if not _is_public(ip):
            log.warning("blocked non-public url", extra={"host": host, "address": str(ip)})
            raise ApiError("unsupported_url", "link points to a private or local address", 400)
    return parts


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _head(url: str, timeout: float) -> tuple[int, dict[str, str], str]:
    """One request without following redirects: (status, headers, final url of this hop)."""
    opener = urllib.request.build_opener(_NoRedirect)
    for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        req = urllib.request.Request(
            url, method=method, headers={"User-Agent": "video-digest", **extra}
        )
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.geturl()
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                return exc.code, {k.lower(): v for k, v in exc.headers.items()}, url
            if exc.code in (405, 501) and method == "HEAD":
                continue  # servers that refuse HEAD: retry with a one-byte GET
            raise ApiError("unsupported_url", f"link answered HTTP {exc.code}", 400) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError("unsupported_url", f"link is unreachable: {exc}", 400) from exc
    raise ApiError("unsupported_url", "link refuses HEAD and ranged GET", 400)


def resolve_direct(url: str, settings: Settings) -> tuple[str, int | None]:
    """Follow redirects by hand, checking every hop, and return (final url, content length).

    Sizes above UPLOAD_MAX_MB are refused before anything is downloaded; the request itself is
    bounded by DIRECT_HEAD_TIMEOUT_SEC.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        check_public_url(current)
        status, headers, _ = _head(current, settings.direct_head_timeout_sec)
        if 300 <= status < 400:
            location = headers.get("location")
            if not location:
                raise ApiError("unsupported_url", "redirect without location", 400)
            current = urllib.parse.urljoin(current, location)
            continue
        length = headers.get("content-length")
        size = int(length) if length and length.isdigit() else None
        if size is not None and size > settings.upload_max_mb * 1024 * 1024:
            raise ApiError(
                "file_too_large", f"file exceeds UPLOAD_MAX_MB={settings.upload_max_mb}", 413
            )
        return current, size
    raise ApiError("unsupported_url", f"more than {MAX_REDIRECTS} redirects", 400)
