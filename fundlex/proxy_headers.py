"""Client-IP resolution behind a reverse proxy (opt-in trust only).

Direct connections keep their socket peer as the client identity.  When the
deployment fronts the app with a trusted reverse proxy, the operator sets
``FUNDLEX_TRUSTED_PROXY_HOSTS`` to a comma/space separated list of the proxy
addresses or CIDR ranges (for example ``127.0.0.1`` for the bundled nginx
template).  Only then is ``X-Forwarded-For`` consulted, walking the chain
from the rightmost hop so a client cannot smuggle extra trusted hops.

The default is empty: no header is trusted, which is the only safe posture
when clients can reach the application port directly.  This is used for
rate-limit and upload-quota keys (R2-F01/F02); it must be configured at
deploy time together with the proxy actually sending the header.
"""
from __future__ import annotations

import os
from ipaddress import ip_address, ip_network

TRUSTED_PROXY_HOSTS_ENV = "FUNDLEX_TRUSTED_PROXY_HOSTS"


def _trusted_networks() -> list:
    raw = os.environ.get(TRUSTED_PROXY_HOSTS_ENV, "")
    networks = []
    for token in raw.replace(",", " ").split():
        try:
            networks.append(ip_network(token, strict=False))
        except ValueError:
            # A malformed entry is skipped; it never widens the trust set.
            continue
    return networks


def _is_trusted(networks: list, address: str) -> bool:
    try:
        parsed = ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in networks)


def client_host(headers, peer: str | None) -> str:
    """Resolve the client IP for rate/quota keys.

    ``headers`` is any mapping with case-insensitive ``get`` (Starlette
    ``Headers`` included); ``peer`` is the socket peer.  X-Forwarded-For is
    honoured only when the peer matches the configured trusted proxies.
    """
    peer = (peer or "").strip() or "unknown"
    networks = _trusted_networks()
    if not networks or not _is_trusted(networks, peer):
        return peer
    forwarded = None
    try:
        forwarded = headers.get("x-forwarded-for") if headers is not None else None
    except AttributeError:
        forwarded = None
    if not forwarded:
        return peer
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    # Walk right to left past trusted relays; the first untrusted hop is the
    # client.  Unparseable hops conservatively identify as the client.
    for candidate in reversed(hops):
        if not _is_trusted(networks, candidate):
            return candidate
    return hops[0] if hops else peer
