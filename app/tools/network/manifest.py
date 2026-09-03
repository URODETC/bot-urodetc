from __future__ import annotations

from app.tools.base import ToolManifest

NETWORK_MANIFEST = ToolManifest(
    name="network",
    description=(
        "Network diagnostics: domain WHOIS, IP geolocation, DNS/NS lookup, "
        "IP ownership (RIR/LIR), reverse DNS and TLS certificate info"
    ),
    commands=["whois", "ip", "ping", "check", "mtr", "geo", "rdns", "tls"],
    inline=True,
    async_mode=False,
)
