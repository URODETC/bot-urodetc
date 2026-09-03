from app.tools.base import ToolManifest

VPN_MANIFEST = ToolManifest(
    name="vpn",
    description="Manage Remnawave VPN users, subscriptions and traffic reports",
    commands=["vpn", "vpn_add", "vpn_extend", "vpn_report"],
    inline=False,
    async_mode=True,
    required_permission="owner",
)
