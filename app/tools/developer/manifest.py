from app.tools.base import ToolManifest

DEVELOPER_MANIFEST = ToolManifest(
    name="developer",
    description="Text codecs, hashes, QR codes, colors, timestamps and small developer utilities",
    commands=[
        "urlencode",
        "urldecode",
        "sha1",
        "sha256",
        "sha384",
        "sha512",
        "md2",
        "md5",
        "length",
        "qr",
        "getcolor",
        "unix",
        "base64encode",
        "base64decode",
        "uuid",
        "password",
    ],
    inline=False,
    async_mode=False,
)
