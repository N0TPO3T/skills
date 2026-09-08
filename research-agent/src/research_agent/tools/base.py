from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel


InputT = TypeVar("InputT", bound=BaseModel, contravariant=True)
OutputT = TypeVar("OutputT", bound=BaseModel, covariant=True)


class Tool(Protocol[InputT, OutputT]):
    name: str

    async def run(self, input: InputT) -> OutputT: ...

