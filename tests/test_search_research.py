import asyncio

from animate_agent.sources.models import QuerySourceInput, SourceBlock, SourceDocument
from animate_agent.sources.research import research_query
from animate_agent.sources.search_focus import READ_DOCUMENT_CHARS, excerpt_read_document


def doc(identity, content, *, page=False):
    return SourceDocument(id=identity, title="Mechanism tutorial", content=content,
                          url=f"https://example.com/{identity}",
                          source_type="web_page" if page else "web_search")


DEEP = ("Input: given numbers.\n\nStep: multiply and update intermediate state.\n\n"
        "Output: resulting prediction.\n\nWorked example: y = 2*x.")


class Search:
    def __init__(self, results):
        self.results, self.calls = results, []

    async def resolve(self, source):
        self.calls.append(source.query)
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


class Reader:
    def __init__(self, results):
        self.results, self.calls = results, []

    async def resolve(self, source):
        self.calls.append(source.url)
        result = self.results[source.url]
        if isinstance(result, Exception):
            raise result
        return [result]


def test_reads_selected_sources_in_depth_and_preserves_real_page_provenance():
    search = Search([[doc("one", "General definition"), doc("two", "Another overview")]])
    body = doc("canonical", DEEP + "\n\n" + "Detailed calculation. " * 180, page=True)
    reader = Reader({"https://example.com/one": body,
                     "https://example.com/two": doc("two", DEEP, page=True)})
    result = asyncio.run(research_query(QuerySourceInput(query="mechanism"), search, reader))
    assert len(search.calls) == 1
    assert len(reader.calls) == 2
    assert len(result[0].content) > 3000
    assert result[0].id == "canonical" and result[0].url.endswith("canonical")
    assert result[0].metadata["search_source_id"] == "one"
    assert result[0].metadata["evidence_gaps"] == []


def test_one_targeted_supplement_for_shallow_evidence_with_bounded_reads():
    search = Search([[doc("one", "Definition only")], [doc("worked", DEEP)]])
    reader = Reader({"https://example.com/one": TimeoutError(),
                     "https://example.com/worked": doc("worked", DEEP, page=True)})
    result = asyncio.run(research_query(QuerySourceInput(query="mechanism"), search, reader))
    assert len(search.calls) == 2 and len(reader.calls) == 2
    assert "inputs / initial state" in search.calls[1]
    assert result[0].metadata["read_status"] == "fallback"
    assert result[1].metadata["read_status"] == "read"
    assert all(d.metadata["evidence_gaps"] == [] for d in result)


def test_missing_material_stays_flagged_without_unbounded_retries():
    search = Search([[doc("one", "Brief description")]])
    reader = Reader({"https://example.com/one": ValueError("blocked URL")})
    result = asyncio.run(research_query(QuerySourceInput(query="mechanism"), search, reader))
    assert len(search.calls) == 2 and len(reader.calls) == 1
    assert result[0].content == "Brief description"
    assert result[0].metadata["evidence_gaps"]
    assert result[0].metadata["read_error_type"] == "ValueError"


def test_structured_evidence_is_bounded_and_preserves_equation_block():
    original = doc("one", "Overview")
    blocks = tuple(SourceBlock(id=f"intro-{i}", type="paragraph", text="Background. " * 90)
                   for i in range(20))
    equation = SourceBlock(id="equation", type="equation", text="Output = input * 2")
    original = original.model_copy(update={"blocks": (*blocks, equation)})
    selected = excerpt_read_document(original, "mechanism")
    assert len(selected.content) <= READ_DOCUMENT_CHARS
    assert equation in selected.blocks
    assert len(original.blocks) == 21


def test_supplement_failure_keeps_existing_evidence():
    class FailingSearch(Search):
        async def resolve(self, source):
            if self.calls:
                self.calls.append(source.query)
                raise TimeoutError()
            return await super().resolve(source)

    search = FailingSearch([[doc("one", "Definition")]])
    reader = Reader({"https://example.com/one": TimeoutError()})
    result = asyncio.run(research_query(QuerySourceInput(query="mechanism"), search, reader))
    assert len(result) == 1
    assert result[0].metadata["supplement_status"] == "fallback:TimeoutError"
