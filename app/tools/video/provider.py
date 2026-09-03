from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError as YtDownloadError

from app.infrastructure.config import Settings
from app.tools.video.errors import (
    AuthRequiredError,
    DiskFullError,
    DownloadError,
    ExtractionError,
    FfmpegMissingError,
    NoFormatsError,
    RateLimitError,
    TemporaryError,
    VideoUnavailableError,
)
from app.tools.video.models import KIND_AUDIO, KIND_VIDEO, MediaOption, VideoInfo

logger = logging.getLogger(__name__)

ProgressHook = Callable[[dict[str, object]], None]

_SIGN_IN_MESSAGE = "Confirm your Google Account is yours"

_SESSION_COOKIE_NAMES = frozenset(
    {"SID", "HSID", "SSID", "__Secure-1PSID", "SAPISID", "__Secure-3PSID"}
)

YOUTUBE_URL_RE = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)?(?:youtube\.com|youtu\.be)/",
    re.IGNORECASE,
)

_VIDEO_HEIGHTS = (2160, 1440, 1080, 720, 480, 360, 240, 144)
_PREFERRED_AUDIO_EXTS = ("m4a", "opus", "webm", "mp3")


class MediaProvider(ABC):
    @abstractmethod
    async def fetch_info(self, url: str) -> VideoInfo:
        ...

    @abstractmethod
    async def download(
        self,
        url: str,
        option: MediaOption,
        outdir: Path,
        progress: ProgressHook | None = None,
    ) -> Path:
        ...


class YtDlpProvider(MediaProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ffmpeg_available = shutil.which("ffmpeg") is not None
        self._cookies_file = self._resolve_cookies(settings.cookies_file)

    @staticmethod
    def _resolve_cookies(path: Path | None) -> Path | None:
        if path is None:
            return None
        expanded = path.expanduser()
        if expanded.is_file():
            return expanded
        return None

    def _cookies_opt(self, cookies: str | None = None) -> dict[str, object]:
        if cookies:
            return {"cookiefile": _write_cookies_tempfile(cookies)}
        if self._cookies_file is not None:
            return {"cookiefile": str(self._cookies_file)}
        return {}

    def _base_opts(self) -> dict[str, object]:
        opts: dict[str, object] = {
            **self._cookies_opt(),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 2,
            "fragment_retries": 2,
        }
        if self._settings.po_token_http_url:
            opts["extractor_args"] = {
                "youtubepot-bgutilhttp": {
                    "base_url": self._settings.po_token_http_url
                },
                "youtube": {
                    "player_client": "web,default"
                },
            }
        return opts

    async def fetch_info(
        self,
        url: str,
        cookies: str | None = None,
    ) -> VideoInfo:
        cookiefile: str | None = None
        tmp_path: Path | None = None
        if cookies:
            tmp_path = Path(_write_cookies_tempfile(cookies))
            cookiefile = str(tmp_path)
        elif self._cookies_file is not None:
            cookiefile = str(self._cookies_file)
        try:
            async with asyncio.timeout(30):
                raw = await asyncio.to_thread(
                    self._extract_info_sync, url, cookiefile
                )
        except TimeoutError:
            raise TemporaryError("Таймаут при получении данных о видео") from None
        except YtDownloadError as exc:
            raise _translate_yt_error(exc) from exc
        finally:
            if tmp_path is not None:
                _remove_cookies_tempfile(tmp_path)

        if raw.get("is_live"):
            raise VideoUnavailableError("Трансляции пока не поддерживаются")

        options = self._build_options(raw)
        if not options:
            raise NoFormatsError("Не найдено форматов для скачивания")

        return VideoInfo(
            video_id=str(raw.get("id") or ""),
            url=str(raw.get("webpage_url") or url),
            title=str(raw.get("title") or "Без названия"),
            author=str(raw.get("uploader") or raw.get("channel") or "Неизвестно"),
            duration=int(raw["duration"]) if raw.get("duration") else None,
            thumbnail=raw.get("thumbnail") or None,
            options=tuple(options),
        )

    def _extract_info_sync(
        self,
        url: str,
        cookiefile: str | None,
    ) -> dict[str, object]:
        opts = self._base_opts()
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    def _build_options(self, raw: dict[str, object]) -> list[MediaOption]:
        duration = int(raw["duration"]) if raw.get("duration") else None
        formats: list[dict[str, object]] = raw.get("formats") or []

        video = self._build_video_options(formats, duration)
        audio = self._build_audio_options(formats, duration)
        return video + audio

    def _build_video_options(
        self,
        formats: list[dict[str, object]],
        duration: int | None,
    ) -> list[MediaOption]:
        by_height: dict[int, dict[str, object]] = {}
        for fmt in formats:
            vcodec = str(fmt.get("vcodec") or "none")
            if vcodec == "none":
                continue
            height = fmt.get("height")
            if not isinstance(height, int) or height <= 0:
                continue
            current = by_height.get(height)
            if current is None or self._is_better_video(fmt, current):
                by_height[height] = fmt

        best_audio = self._best_audio_format(formats)

        options: list[MediaOption] = []
        for height in _VIDEO_HEIGHTS:
            fmt = by_height.get(height)
            if fmt is None:
                continue
            ext = str(fmt.get("ext") or "mp4")
            merged = str(fmt.get("acodec") or "none") == "none"
            if merged:
                format_id = f"bv*[height<={height}]+ba/b[height<={height}]"
                size = self._merged_size(fmt, best_audio, duration)
            else:
                format_id = f"b[height<={height}]"
                size = self._format_size(fmt, duration)
            options.append(
                MediaOption(
                    kind=KIND_VIDEO,
                    label=f"{height}p",
                    size=size,
                    approx=size is not None and merged,
                    format_id=format_id,
                    ext=ext,
                )
            )
        return options

    @staticmethod
    def _is_better_video(candidate: dict[str, object], current: dict[str, object]) -> bool:
        cand_tbr = float(candidate.get("tbr") or 0)
        cur_tbr = float(current.get("tbr") or 0)
        if cand_tbr != cur_tbr:
            return cand_tbr > cur_tbr
        return _ext_preference(str(candidate.get("ext") or "")) < _ext_preference(
            str(current.get("ext") or "")
        )

    @staticmethod
    def _best_audio_format(formats: list[dict[str, object]]) -> dict[str, object] | None:
        best: dict[str, object] | None = None
        for fmt in formats:
            if str(fmt.get("vcodec") or "none") != "none":
                continue
            bitrate = YtDlpProvider._audio_bitrate(fmt)
            if bitrate <= 0:
                continue
            if best is None or bitrate > YtDlpProvider._audio_bitrate(best):
                best = fmt
        return best

    def _merged_size(
        self,
        video_fmt: dict[str, object],
        audio_fmt: dict[str, object] | None,
        duration: int | None,
    ) -> int | None:
        video_size = video_fmt.get("filesize") or video_fmt.get("filesize_approx")
        if not isinstance(video_size, (int, float)) or not video_size:
            video_bitrate = float(video_fmt.get("tbr") or 0)
            if duration and video_bitrate:
                video_size = int(duration * video_bitrate * 125)
            else:
                return None
        audio_size = None
        if audio_fmt is not None:
            audio_raw = audio_fmt.get("filesize") or audio_fmt.get("filesize_approx")
            if isinstance(audio_raw, (int, float)) and audio_raw:
                audio_size = int(audio_raw)
            elif duration:
                bitrate = self._audio_bitrate(audio_fmt)
                audio_size = int(duration * bitrate * 125)
        return int(video_size) + int(audio_size or 0)

    def _build_audio_options(
        self,
        formats: list[dict[str, object]],
        duration: int | None,
    ) -> list[MediaOption]:
        by_bitrate: dict[int, dict[str, object]] = {}
        for fmt in formats:
            if str(fmt.get("vcodec") or "none") != "none":
                continue
            bitrate = self._audio_bitrate(fmt)
            if bitrate <= 0:
                continue
            current = by_bitrate.get(bitrate)
            if current is None or self._is_better_audio(fmt, current):
                by_bitrate[bitrate] = fmt

        options: list[MediaOption] = []
        for bitrate in sorted(by_bitrate, reverse=True):
            fmt = by_bitrate[bitrate]
            raw_ext = str(fmt.get("ext") or "m4a")
            post = "mp3" if self._ffmpeg_available else None
            size = self._format_size(fmt, duration)
            options.append(
                MediaOption(
                    kind=KIND_AUDIO,
                    label=f"{bitrate} kbps",
                    size=size,
                    approx=size is not None and fmt.get("filesize") is None,
                    format_id=str(fmt.get("format_id") or "bestaudio/best"),
                    ext=post or raw_ext,
                    post=post,
                )
            )
        return options

    @staticmethod
    def _audio_bitrate(fmt: dict[str, object]) -> int:
        abr = fmt.get("abr")
        if isinstance(abr, (int, float)) and abr:
            return round(float(abr))
        tbr = fmt.get("tbr")
        if isinstance(tbr, (int, float)) and tbr:
            return round(float(tbr) * 0.8)
        return 0

    @staticmethod
    def _is_better_audio(candidate: dict[str, object], current: dict[str, object]) -> bool:
        cand_tbr = float(candidate.get("tbr") or 0)
        cur_tbr = float(current.get("tbr") or 0)
        if cand_tbr != cur_tbr:
            return cand_tbr > cur_tbr
        return _ext_preference(str(candidate.get("ext") or "")) < _ext_preference(
            str(current.get("ext") or "")
        )

    def _format_size(self, fmt: dict[str, object], duration: int | None) -> int | None:
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        if isinstance(size, (int, float)) and size:
            return int(size)
        bitrate = self._audio_bitrate(fmt) or float(fmt.get("tbr") or 0)
        if duration and bitrate:
            return int(duration * bitrate * 125)  # kbit/s * s -> bytes (bitrate*1000/8)
        return None

    async def download(
        self,
        url: str,
        option: MediaOption,
        outdir: Path,
        cookies: str | None = None,
        progress: ProgressHook | None = None,
    ) -> Path:
        outdir.mkdir(parents=True, exist_ok=True)
        cookiefile = self._cookies_opt(cookies).get("cookiefile")
        try:
            await asyncio.to_thread(
                self._download_sync,
                url,
                option,
                str(outdir),
                progress,
                cookiefile,
            )
        except TimeoutError:
            raise TemporaryError("Таймаут при скачивании") from None
        except YtDownloadError as exc:
            raise _translate_yt_error(exc) from exc
        except OSError as exc:
            if exc.errno == 28:
                raise DiskFullError("Недостаточно места на диске") from exc
            raise DownloadError(str(exc)) from exc
        finally:
            if cookiefile and cookies:
                _remove_cookies_tempfile(Path(cookiefile))
        return _pick_result_file(outdir)

    def _download_sync(
        self,
        url: str,
        option: MediaOption,
        outdir: str,
        progress: ProgressHook | None,
        cookiefile: str | None,
    ) -> None:
        postprocessors: list[dict[str, object]] = []
        if option.post:
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": option.post,
                    "preferredquality": option.label.split()[0],
                }
            )
        opts: dict[str, object] = {
            **self._base_opts(),
            "format": option.format_id,
            "outtmpl": f"{outdir}/%(id)s.%(ext)s",
            "progress_hooks": [progress] if progress else [],
            "postprocessors": postprocessors,
        }
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])


def _ext_preference(ext: str) -> int:
    try:
        return _PREFERRED_AUDIO_EXTS.index(ext)
    except ValueError:
        return 99


def _pick_result_file(outdir: Path) -> Path:
    candidates = [
        p
        for p in outdir.iterdir()
        if p.is_file()
        and not p.name.endswith((".part", ".ytdl", ".tmp", ".temp"))
        and p.name != "auth_cookies.txt"
    ]
    if not candidates:
        raise DownloadError("Файл не был создан")
    return max(candidates, key=lambda p: (p.stat().st_size, p.stat().st_mtime))


def _write_cookies_tempfile(cookies_text: str) -> str:
    fd, path = tempfile.mkstemp(prefix="yt_cookies_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(cookies_text)
    return path


def _remove_cookies_tempfile(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _translate_yt_error(exc: YtDownloadError) -> "Exception":
    message = str(exc)
    lowered = message.lower()
    if _SIGN_IN_MESSAGE.lower() in lowered or "sign in to confirm" in lowered:
        logger.warning(
            "youtube bot-check hit",
            extra={"detail": message[:400]},
        )
        return AuthRequiredError("Авторизация требуется")
    if any(marker in lowered for marker in ("video unavailable", "not available", "video removed", "private video")):
        return VideoUnavailableError("Видео недоступно (удалено или приватное)")
    if "http error 429" in lowered or "too many requests" in lowered:
        return RateLimitError("Слишком много запросов к YouTube, попробуйте позже")
    if "http error 403" in lowered:
        return TemporaryError("YouTube временно ограничил доступ, попробуйте позже")
    if "timeout" in lowered or "timed out" in lowered:
        return TemporaryError("Сеть недоступна, попробуйте позже")
    if "requested format is not available" in lowered or "no video formats found" in lowered:
        return NoFormatsError("Запрошенный формат недоступен")
    if "ffmpeg" in lowered:
        return FfmpegMissingError("Для обработки требуется FFmpeg")
    if "unsupported url" in lowered:
        return ExtractionError("Ссылка не поддерживается")
    return DownloadError(message[:300])