import os
import socket
import logging
import ipaddress
import requests
import requests.adapters
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Security settings from environment
REDMINE_SECURITY_STRICT = os.getenv("REDMINE_SECURITY_STRICT", "true").lower() == "true"
REDMINE_ALLOWED_HOSTS = [
    host.strip().lower()
    for host in os.getenv("REDMINE_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]


class SecurityValidationError(ValueError):
    """Raised when a URL fails security validation checks."""

    pass


def is_ip_private(ip_str: str) -> bool:
    """Check if an IP address string belongs to a forbidden range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return False


def validate_redmine_url(url: str) -> None:
    """Validates a Redmine URL for potential SSRF vulnerabilities.

    Checks:
    1. Scheme (must be http or https)
    2. Hostname resolution (must not resolve to private/loopback IPs in strict mode)
    3. Hostname allowlist (if REDMINE_ALLOWED_HOSTS is configured)

    Raises:
        SecurityValidationError: If the URL is considered dangerous or invalid.
    """
    if not url:
        raise SecurityValidationError("URL is empty.")

    parsed = urlparse(url)

    # 1. Validate Scheme
    if parsed.scheme not in ("http", "https"):
        raise SecurityValidationError(
            f"Invalid URL scheme: {parsed.scheme}. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SecurityValidationError("URL is missing a valid hostname.")

    # 2. Validate Allowlist
    if REDMINE_ALLOWED_HOSTS:
        if hostname.lower() not in REDMINE_ALLOWED_HOSTS:
            raise SecurityValidationError(
                f"Hostname '{hostname}' is not in the allowed hosts list."
            )

    # 3. Validate IPs (SSRF Protection)
    if REDMINE_SECURITY_STRICT:
        try:
            # Resolve hostname to all available IP addresses
            # This handles both IPv4 and IPv6 and prevents DNS rebinding bypasses
            # if checked right before the actual request (though here we check
            # at the middleware level)
            addr_info = socket.getaddrinfo(
                hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
            resolved_ips = {info[4][0] for info in addr_info}

            for ip in resolved_ips:
                if is_ip_private(ip):
                    raise SecurityValidationError(
                        f"URL resolves to a forbidden private or loopback IP: {ip}. "
                        "To allow this for local development, "
                        "set REDMINE_SECURITY_STRICT=false."
                    )
        except socket.gaierror as e:
            # If we can't resolve it, it might be a malformed hostname or internal-only
            # In strict mode, we should generally be cautious.
            logger.debug(f"Could not resolve hostname {hostname}: {e}")
            # If it's literally an IP address and we couldn't resolve it,
            # check it directly
            if is_ip_private(hostname):
                raise SecurityValidationError(
                    f"URL uses a forbidden private IP: {hostname}."
                )


def ssrf_redirect_hook(response, **kwargs):
    """Requests response hook that blocks redirects to private/internal URLs.

    Attach this hook to the requests session used by python-redmine to prevent
    SSRF-via-redirect attacks: an attacker-controlled server responds with a
    302 redirect to an internal endpoint (e.g., http://169.254.169.254/),
    and without this hook the Redmine client would silently follow it.

    Usage (via _build_requests_config):
        requests_config["hooks"] = {"response": [ssrf_redirect_hook]}
    """
    if not REDMINE_SECURITY_STRICT:
        return

    if response.is_redirect:
        location = response.headers.get("Location", "")
        if location:
            try:
                validate_redmine_url(location)
            except SecurityValidationError as e:
                # Raise immediately — requests will propagate this as an exception,
                # stopping the redirect chain before the dangerous request is made.
                raise SecurityValidationError(
                    f"Redirect to '{location}' blocked by SSRF protection: {e}"
                ) from e


class SSRFSafeHTTPAdapter(requests.adapters.HTTPAdapter):
    """A requests HTTPAdapter that pins DNS resolution to prevent TOCTOU rebinding.

    The standard SSRF mitigation of resolving DNS at validation time and then
    making the request separately is vulnerable to DNS rebinding: an attacker
    can swap the DNS record between the validation check and the actual TCP
    connection so that the second resolution returns a private IP.

    This adapter closes that window by:
    1. Resolving the hostname to an IP *inside* send(), just before connecting.
    2. Validating the resolved IP against SSRF rules at that point.
    3. Rewriting the request URL to use the resolved IP directly, so
       urllib3/socket never performs a second independent DNS resolution.
    4. Setting the 'Host' header to the original hostname so TLS SNI and
       virtual-host routing continue to work correctly.

    This guarantees a single, validated DNS resolution per request.
    """

    def send(self, request, **kwargs):
        if not REDMINE_SECURITY_STRICT:
            return super().send(request, **kwargs)

        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(request.url)
        hostname = parsed.hostname
        if not hostname:
            raise SecurityValidationError("Request URL is missing a hostname.")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # --- Single DNS resolution + validation ---
        try:
            addr_info = socket.getaddrinfo(
                hostname, port, proto=socket.IPPROTO_TCP
            )
        except socket.gaierror as exc:
            raise SecurityValidationError(
                f"Could not resolve '{hostname}': {exc}"
            ) from exc

        if not addr_info:
            raise SecurityValidationError(
                f"DNS resolution returned no addresses for '{hostname}'."
            )

        # Validate every resolved address (all must be safe).
        for entry in addr_info:
            resolved_ip = entry[4][0]
            if is_ip_private(resolved_ip):
                raise SecurityValidationError(
                    f"Request to '{hostname}' blocked: "
                    f"resolves to a forbidden IP ({resolved_ip})."
                )

        # Pin the first resolved IP into the URL so urllib3 connects directly
        # without performing another DNS lookup.
        pinned_ip = addr_info[0][4][0]
        # IPv6 addresses must be wrapped in brackets in URLs.
        if ":" in pinned_ip:
            netloc_ip = f"[{pinned_ip}]:{port}"
        else:
            netloc_ip = f"{pinned_ip}:{port}"

        pinned_url = urlunparse(parsed._replace(netloc=netloc_ip))
        request.url = pinned_url

        # Preserve the original hostname in the Host header so TLS SNI and
        # virtual-host routing continue to work correctly.
        request.headers["Host"] = (
            hostname if parsed.port is None else f"{hostname}:{parsed.port}"
        )

        logger.debug(
            "SSRFSafeHTTPAdapter: '%s' pinned to %s", hostname, pinned_ip
        )
        return super().send(request, **kwargs)
