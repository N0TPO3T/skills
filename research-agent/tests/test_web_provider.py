from __future__ import annotations

from research_agent.literature.providers.web import _CitationMetaParser


def test_web_parser_separates_article_from_page_chrome() -> None:
    parser = _CitationMetaParser()
    parser.feed(
        "<html><body><nav>Navigation</nav><article><p>Paper body.</p></article>"
        "<footer>Footer</footer></body></html>"
    )
    assert parser.article_text == ["Paper body."]
    assert "Navigation" in parser.visible_text
