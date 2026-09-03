from __future__ import annotations

import asyncio
import json
import re
import shutil
import socket
import time
from typing import Protocol

import httpx

from app.tools.network.errors import DiagnosticUnavailableError, LookupFailedError, LookupTimeoutError
from app.tools.network.models import HttpCheckResult, MtrHop, MtrResult, PingResult

_PACKETS_RE = re.compile(
    r"(?P<sent>\d+) packets transmitted, (?P<received>\d+) (?:packets )?received, "
    r"(?P<loss>[\d.]+)% packet loss"
)
_RTT_RE = re.compile(
    r"(?:round-trip|rtt) min/avg/max/(?:stddev|mdev) = "
    r"(?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/[\d.]+ ms"
)
_SAMPLE_RE = re.compile(r"time[=<]([\d.]+)\s*ms")


class DiagnosticsProvider(Protocol):
    async def ping(self, host: str) -> PingResult: ...
    async def check_http(self, url: str) -> HttpCheckResult: ...
    async def mtr(self, host: str) -> MtrResult: ...


class SystemDiagnosticsProvider:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def ping(self, host: str) -> PingResult:
        binary = shutil.which("ping")
        if binary is None:
            raise DiagnosticUnavailableError("Команда ping не установлена на сервере бота")
        ip = await _resolve(host)
        output, returncode = await _run(binary, "-n", "-c", "4", host, timeout=15)
        packets = _PACKETS_RE.search(output)
        if packets is None:
            raise LookupFailedError(_last_error(output, "Не удалось разобрать ответ ping"))
        rtt = _RTT_RE.search(output)
        samples = tuple(float(value) for value in _SAMPLE_RE.findall(output))
        return PingResult(
            host=host,
            ip=ip,
            transmitted=int(packets.group("sent")),
            received=int(packets.group("received")),
            packet_loss=float(packets.group("loss")),
            min_ms=float(rtt.group("min")) if rtt else None,
            avg_ms=float(rtt.group("avg")) if rtt else None,
            max_ms=float(rtt.group("max")) if rtt else None,
            samples_ms=samples,
        )

    async def check_http(self, url: str) -> HttpCheckResult:
        started = time.perf_counter()
        try:
            async with self._http.stream("GET", url, follow_redirects=True) as response:
                elapsed_ms = (time.perf_counter() - started) * 1000
                raw_length = response.headers.get("content-length")
                try:
                    content_length = int(raw_length) if raw_length else None
                except ValueError:
                    content_length = None
                return HttpCheckResult(
                    url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    reason=response.reason_phrase,
                    elapsed_ms=elapsed_ms,
                    redirects=len(response.history),
                    server=response.headers.get("server"),
                    content_type=response.headers.get("content-type"),
                    content_length=content_length,
                    reachable=response.status_code < 500,
                )
        except httpx.TimeoutException as exc:
            raise LookupTimeoutError("HTTP-сервер не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            raise LookupFailedError(f"HTTP-проверка не удалась: {exc}") from exc

    async def mtr(self, host: str) -> MtrResult:
        ip = await _resolve(host)
        binary = shutil.which("mtr")
        if binary is None:
            raise DiagnosticUnavailableError("MTR не установлен на сервере бота")
        output, returncode = await _run(
            binary,
            "--report",
            "--report-cycles",
            "5",
            "--no-dns",
            "--json",
            host,
            timeout=45,
        )
        if returncode not in {0, 1}:
            raise LookupFailedError(_last_error(output, "MTR завершился с ошибкой"))
        try:
            payload = json.loads(output)
            raw_hops = payload["report"]["hubs"]
            hops = tuple(_parse_hop(item, index) for index, item in enumerate(raw_hops, 1))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LookupFailedError("Не удалось разобрать результат MTR") from exc
        if not hops:
            raise LookupFailedError("MTR не вернул ни одного узла")
        return MtrResult(host=host, ip=ip, hops=hops)


async def _resolve(host: str) -> str:
    loop = asyncio.get_running_loop()
    try:
        rows = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise LookupFailedError(f"Не удалось определить IP-адрес: {host}") from exc
    return rows[0][4][0]


async def _run(*args: str, timeout: float) -> tuple[str, int]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise LookupTimeoutError("Диагностика не завершилась вовремя") from exc
    return stdout.decode(errors="replace"), process.returncode or 0


def _parse_hop(item: dict[str, object], fallback_number: int) -> MtrHop:
    return MtrHop(
        number=int(item.get("count") or fallback_number),
        host=str(item.get("host") or "???"),
        loss_percent=_float(item.get("Loss%")),
        sent=_int(item.get("Snt")),
        last_ms=_float(item.get("Last")),
        avg_ms=_float(item.get("Avg")),
        best_ms=_float(item.get("Best")),
        worst_ms=_float(item.get("Wrst")),
    )


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _last_error(output: str, fallback: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return (lines[-1] if lines else fallback)[:400]
