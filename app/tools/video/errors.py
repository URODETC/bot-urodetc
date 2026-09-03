from __future__ import annotations


class VideoError(Exception):
    """Base error for the video tool."""


class UrlValidationError(VideoError):
    """The provided link is not a supported URL."""


class VideoUnavailableError(VideoError):
    """The video does not exist, is private or geo-blocked."""


class NoFormatsError(VideoError):
    """The video has no formats we can download."""


class AuthRequiredError(VideoError):
    """YouTube asked the user to confirm their identity (bot check)."""


class ExtractionError(VideoError):
    """yt-dlp could not extract metadata."""


class DownloadError(VideoError):
    """Generic download failure."""


class TemporaryError(VideoError):
    """Transient failure (network, YouTube ban); safe to retry."""


class RateLimitError(TemporaryError):
    """HTTP 429 / IP ban from the host."""


class DiskFullError(DownloadError):
    """Not enough disk space."""


class FileTooLargeError(VideoError):
    """Resulting file exceeds the Telegram upload limit."""


class FfmpegMissingError(VideoError):
    """FFmpeg is required to process this media type."""