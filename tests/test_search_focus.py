from animate_agent.sources.models import SourceDocument
from animate_agent.sources.search_focus import focus_search_results


def document(identity: str, title: str, content: str, url: str = "") -> SourceDocument:
    return SourceDocument(
        id=identity,
        source_type="web_search",
        title=title,
        content=content,
        url=url or f"https://example.com/{identity}",
    )


def test_focus_discards_tangents_and_keeps_at_most_three_unique_sources() -> None:
    docs = [
        document("noise", "Industry history", "A broad introduction to technology."),
        document("one", "TCP handshake", "TCP handshake uses SYN and ACK."),
        document("copy", "TCP handshake", "TCP handshake uses SYN and ACK."),
        document("two", "TCP handshake states", "TCP handshake transitions between states."),
        document("three", "TCP handshake packets", "TCP handshake packet exchange."),
        document("four", "TCP handshake example", "A TCP handshake example."),
    ]
    result = focus_search_results(docs, "How does a TCP handshake work?")
    assert [doc.id for doc in result] == ["one", "two", "three"]


def test_focus_bounds_excerpts_and_retains_relevant_late_paragraphs() -> None:
    content = "Historical background. " * 200 + "\n\nTCP handshake uses SYN and ACK."
    original = document("one", "TCP handshake", content)
    result = focus_search_results([original], "TCP handshake")[0]
    assert len(result.content) <= 3000
    assert "SYN and ACK" in result.content
    assert result.metadata["excerpted"] is True
    assert result.url == original.url
    assert original.content == content


def test_cross_language_no_match_preserves_provider_order_and_url_deduplication() -> None:
    docs = [
        document("one", "A", "English first", "https://example.com/page#first"),
        document("copy", "B", "English second", "https://example.com/page#second"),
        document("two", "C", "English third"),
    ]
    assert [doc.id for doc in focus_search_results(docs, "传输控制协议")] == ["one", "two"]


def test_chinese_query_prefers_mechanism_over_general_background() -> None:
    docs = [
        document("overview", "行业介绍", "人工智能的发展历史。"),
        document("mechanism", "注意力机制", "注意力机制利用查询与键计算权重。"),
    ]
    assert focus_search_results(docs, "我想了解注意力机制如何工作")[0].id == "mechanism"
