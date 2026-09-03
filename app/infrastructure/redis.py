from __future__ import annotations

from arq.connections import ArqRedis, RedisSettings, create_pool
from redis.asyncio import Redis


def arq_settings(dsn: str) -> RedisSettings:
    return RedisSettings.from_dsn(dsn)


async def create_arq_pool(dsn: str) -> ArqRedis:
    return await create_pool(arq_settings(dsn))


def create_redis(dsn: str) -> Redis:
    return Redis.from_url(dsn, decode_responses=True)