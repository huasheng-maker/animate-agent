"""Bounded search -> public-page reading -> one gap-directed search.

Uses the existing adapters and their URL/content protections. Coverage is a
lexical diagnostic, never a claim that evidence has been fact-checked.
"""
from __future__ import annotations

import asyncio

from animate_agent.sources.adapters import QueryAdapter, UrlAdapter
from animate_agent.sources.models import QuerySourceInput, SourceDocument, UrlSourceInput
from animate_agent.sources.search_focus import (
    evidence_gaps,
    excerpt_read_document,
    focus_search_results,
)

READ_TIMEOUT_SECONDS = 20.0
SUPPLEMENT_TIMEOUT_SECONDS = 30.0


async def research_query(
    source: QuerySourceInput, search: QueryAdapter, reader: UrlAdapter,
) -> list[SourceDocument]:
    detailed_query = QuerySourceInput(query=(
        source.query + "\nExplain the mechanism: inputs, intermediate steps, outputs, "
        "worked examples or equations. Prefer original technical documentation."
    ))
    documents = await search.resolve(detailed_query)
    selected = focus_search_results(documents, source.query)
    # Use original content for reading/fallback; avoid irreversibly trimming to 3000 first.
    originals = {doc.id: doc for doc in documents}
    selected = [excerpt_read_document(originals[d.id], source.query) for d in selected]
    visited: set[str] = set()

    async def read(doc: SourceDocument) -> SourceDocument:
        if not doc.url or doc.url in visited:
            return doc
        visited.add(doc.url)
        try:
            pages = await asyncio.wait_for(
                reader.resolve(UrlSourceInput(url=doc.url)), timeout=READ_TIMEOUT_SECONDS,
            )
            if not pages:
                raise ValueError("empty reader result")
            page = excerpt_read_document(pages[0], source.query)
            # Keep real reader source identity and URL; never attach another page's prose
            # to a search citation. Short/error-like pages don't replace useful snippets.
            if len(page.content) < min(500, len(doc.content)):
                return doc.model_copy(update={"metadata": {
                    **doc.metadata, "read_status": "insufficient_body",
                }})
            return page.model_copy(update={"metadata": {
                **page.metadata, "read_status": "read", "search_source_id": doc.id,
                "search_provider": doc.metadata.get("provider"),
            }})
        except Exception as exc:
            # Preserve useful evidence on denial/timeout. Never log URLs or response bodies.
            return doc.model_copy(update={"metadata": {
                **doc.metadata, "read_status": "fallback", "read_error_type": type(exc).__name__,
            }})

    selected[:2] = await asyncio.gather(*(read(doc) for doc in selected[:2]))
    gaps = evidence_gaps("\n".join(doc.content for doc in selected))
    supplement_status = "not_needed"
    if gaps:
        query = (source.query + "\nMechanism details and worked example; specifically: "
                 + "; ".join(gaps))
        try:
            extra = await asyncio.wait_for(
                search.resolve(QuerySourceInput(query=query)), timeout=SUPPLEMENT_TIMEOUT_SECONDS,
            )
            candidates = focus_search_results(extra, source.query)
            # Keep the read evidence, add one new source only (maximum three final sources).
            known_urls = {doc.url for doc in selected if doc.url}
            known_content = {" ".join(doc.content.split()).casefold() for doc in selected}
            fresh = next((doc for doc in candidates if doc.id not in {d.id for d in selected}
                          and (not doc.url or doc.url not in known_urls)
                          and " ".join(doc.content.split()).casefold() not in known_content), None)
            if fresh is not None:
                original = next((d for d in extra if d.id == fresh.id), fresh)
                enriched = await read(excerpt_read_document(original, source.query))
                selected = [*selected[:2], enriched]
            supplement_status = "completed"
        except Exception as exc:
            supplement_status = f"fallback:{type(exc).__name__}"
    gaps = evidence_gaps("\n".join(doc.content for doc in selected))
    return [doc.model_copy(update={"metadata": {
        **doc.metadata, "coverage_method": "lexical-hints-v1", "evidence_gaps": gaps,
        "supplement_status": supplement_status,
    }}) for doc in selected]
