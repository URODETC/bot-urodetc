from __future__ import annotations

from dataclasses import dataclass

KIND_AUDIO = "audio"
KIND_VIDEO = "video"


@dataclass(frozen=True)
class MediaOption:
    kind: str
    label: str
    size: int | None
    approx: bool
    format_id: str
    ext: str
    post: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "size": self.size,
            "approx": self.approx,
            "format_id": self.format_id,
            "ext": self.ext,
            "post": self.post,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MediaOption":
        return cls(
            kind=str(data["kind"]),
            label=str(data["label"]),
            size=data["size"] if data["size"] is not None else None,  # type: ignore[arg-type]
            approx=bool(data["approx"]),
            format_id=str(data["format_id"]),
            ext=str(data["ext"]),
            post=data["post"] if data["post"] is not None else None,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    url: str
    title: str
    author: str
    duration: int | None
    thumbnail: str | None
    options: tuple[MediaOption, ...]


@dataclass(frozen=True)
class VideoPreview:
    request_id: str
    info: VideoInfo