from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url


def normalize_checkpoint_database_url(
    database_url: str,
) -> str:
    url = make_url(database_url)

    if not url.drivername.startswith("postgresql"):
        raise ValueError(
            "LangGraph PostgreSQL checkpointing requires a PostgreSQL URL."
        )

    normalized_url = url.set(drivername="postgresql")

    return normalized_url.render_as_string(
        hide_password=False,
    )


@contextmanager
def postgres_checkpointer(
    *,
    database_url: str,
    min_pool_size: int,
    max_pool_size: int,
) -> Iterator[PostgresSaver]:
    if min_pool_size < 1:
        raise ValueError(
            "Checkpoint minimum pool size must be at least 1."
        )

    if max_pool_size < min_pool_size:
        raise ValueError(
            "Checkpoint maximum pool size cannot be smaller "
            "than the minimum pool size."
        )

    connection_string = normalize_checkpoint_database_url(
        database_url
    )

    serializer = JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=None,
    )

    with ConnectionPool(
        conninfo=connection_string,
        min_size=min_pool_size,
        max_size=max_pool_size,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    ) as pool:
        pool.wait()

        checkpointer = PostgresSaver(
            pool,
            serde=serializer,
        )

        checkpointer.setup()

        yield checkpointer