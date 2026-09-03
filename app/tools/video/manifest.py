from __future__ import annotations

from app.tools.base import ToolManifest

VIDEO_MANIFEST = ToolManifest(
    name="video",
    description="Download media from YouTube (audio or video)",
    commands=["download"],
    inline=False,
    async_mode=True,
)