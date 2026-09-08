from __future__ import annotations

from research_agent.literature.providers.arxiv import ArxivLikeProvider
from research_agent.schemas.literature import LiteratureSearchQuery


ATOM_FIXTURE = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom'>
  <entry>
    <id>http://arxiv.org/abs/2501.01234v2</id>
    <published>2025-01-03T00:00:00Z</published>
    <title>Adaptive Test-Time Compute</title>
    <summary>A verified fixture abstract.</summary>
    <author><name>Alice Smith</name></author>
    <arxiv:doi>10.1000/example</arxiv:doi>
  </entry>
</feed>"""


def test_arxiv_candidate_conversion() -> None:
    entries = ArxivLikeProvider.parse_feed(ATOM_FIXTURE)
    query = LiteratureSearchQuery(
        id="QUERY-1", query="adaptive compute", purpose="canonical", priority=1.0
    )
    provider = ArxivLikeProvider(minimum_request_interval=0)
    result = provider._candidate_from_entry(entries[0], query.id, 1)
    assert result.identifiers.arxiv_id == "2501.01234"
    assert result.identifiers.doi == "10.1000/example"
    assert result.raw_authors == ["Alice Smith"]
    assert result.status == "candidate"

