from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    limit: int = Field(default=10, ge=1, le=100)


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    url: str | None = None
    snippet: str = ""
    synthetic_test_data: bool = False


class SearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[SearchResult]


class MockSearchTool:
    name = "search"

    async def run(self, input: SearchInput) -> SearchOutput:
        return SearchOutput(
            results=[
                SearchResult(
                    title=f"Synthetic paper for {input.query}",
                    snippet="synthetic_test_data",
                    synthetic_test_data=True,
                )
            ]
        )


class SearchTool(MockSearchTool):
    """Interface placeholder. TODO: inject a source-verifying live search provider."""
