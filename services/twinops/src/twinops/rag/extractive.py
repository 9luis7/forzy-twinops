"""Deterministic, exact-substring fallback selection for retrieved manual chunks."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Sequence

from twinops.rag.retrieval import FusedRetrievalHit


MAX_EXCERPT_CHARACTERS = 500
MAX_EXCERPTS = 3
_MIN_EXCERPT_CHARACTERS = 28
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SPAN_PATTERN = re.compile(r"[^.!?\r\n]+(?:[.!?]+|(?=\r?$))", re.MULTILINE)
_COLUMN_SEPARATOR_PATTERN = re.compile(r"[^\S\r\n]{2,}")

_LANGUAGE_MARKERS = {
    "pt": frozenset(
        {
            "a",
            "antes",
            "como",
            "da",
            "de",
            "deve",
            "do",
            "em",
            "o",
            "os",
            "para",
            "por",
            "quando",
            "que",
            "quais",
            "verifique",
            "verificar",
        }
    ),
    "en": frozenset(
        {
            "before",
            "for",
            "how",
            "in",
            "inspect",
            "should",
            "the",
            "to",
            "verify",
            "what",
            "when",
            "which",
        }
    ),
    "es": frozenset(
        {
            "antes",
            "como",
            "cuando",
            "de",
            "debe",
            "el",
            "en",
            "la",
            "para",
            "por",
            "que",
            "verificar",
        }
    ),
}
_STOPWORDS = frozenset().union(*_LANGUAGE_MARKERS.values()) | {
    "e",
    "is",
    "no",
    "ou",
    "se",
}
_TECHNICAL_CONCEPTS = (
    frozenset(
        {
            "lubrificacao",
            "lubrificar",
            "lubricacion",
            "lubrication",
            "relubrificacao",
            "relubricacion",
            "relubrication",
            "graxa",
            "grease",
        }
    ),
    frozenset(
        {
            "bearing",
            "bearings",
            "cojinete",
            "cojinetes",
            "rolamento",
            "rolamentos",
            "rodamiento",
            "rodamientos",
        }
    ),
    frozenset({"vibracao", "vibracion", "vibration"}),
    frozenset(
        {"interval", "intervalo", "period", "periodo", "frequencia", "frequency"}
    ),
    frozenset(
        {
            "check",
            "checked",
            "checking",
            "checagem",
            "inspecao",
            "inspect",
            "inspected",
            "inspection",
            "verificacao",
            "verificar",
            "verifique",
            "verify",
        }
    ),
    frozenset({"humidity", "humedad", "moisture", "umidade"}),
    frozenset({"temperature", "temperatura"}),
    frozenset({"almacenamiento", "armazenamento", "storage"}),
    frozenset({"alinhamento", "alineacion", "alignment"}),
)


@dataclass(frozen=True)
class ExtractiveExcerpt:
    hit: FusedRetrievalHit
    excerpt: str
    language: str
    start: int
    end: int


@dataclass(frozen=True)
class _Candidate:
    hit: FusedRetrievalHit
    excerpt: str
    language: str
    match_count: int
    hit_index: int
    span_index: int
    tokens: frozenset[str]
    start: int
    end: int


def select_safe_excerpts(
    question: str,
    hits: Sequence[FusedRetrievalHit],
    *,
    limit: int = MAX_EXCERPTS,
) -> tuple[ExtractiveExcerpt, ...]:
    """Select relevant readable spans without translating or paraphrasing them."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("fallback question must not be empty")
    if not 1 <= limit <= MAX_EXCERPTS:
        raise ValueError("fallback excerpt limit is out of range")

    query_tokens = _tokens(question)
    query_terms = _expanded_query_terms(query_tokens)
    if not query_terms:
        return ()
    question_language = _detect_language(query_tokens)
    requested_language = _requested_language(question)
    candidates: list[_Candidate] = []

    for hit_index, hit in enumerate(hits):
        chunk_text = hit.candidate.chunk.text
        document_language = _single_document_language(
            hit.candidate.document.language
        )
        for span_index, (excerpt, start, end) in enumerate(_spans(chunk_text)):
            if not _is_safe_prose(excerpt):
                continue
            span_tokens = _tokens(excerpt)
            match_count = _match_count(query_terms, span_tokens)
            if match_count == 0:
                continue
            language = _detect_language(span_tokens) or document_language
            candidates.append(
                _Candidate(
                    hit=hit,
                    excerpt=excerpt,
                    language=language or "und",
                    match_count=match_count,
                    hit_index=hit_index,
                    span_index=span_index,
                    tokens=frozenset(span_tokens),
                    start=start,
                    end=end,
                )
            )

    if not candidates:
        return ()
    candidates.sort(
        key=lambda item: (
            -item.match_count,
            item.hit_index,
            item.span_index,
            item.excerpt,
        )
    )
    selected_language = _selected_language(
        candidates, requested_language or question_language
    )
    candidates = [
        item for item in candidates if item.language == selected_language
    ]

    selected: list[_Candidate] = []
    selected_chunk_ids: set[str] = set()
    for candidate in candidates:
        chunk_id = candidate.hit.candidate.chunk.chunk_id
        if chunk_id in selected_chunk_ids:
            continue
        if any(_too_similar(candidate.tokens, item.tokens) for item in selected):
            continue
        chunk_text = candidate.hit.candidate.chunk.text
        if chunk_text[candidate.start:candidate.end] != candidate.excerpt:
            continue
        selected.append(candidate)
        selected_chunk_ids.add(chunk_id)
        if selected_language == "und" or len(selected) == limit:
            break

    return tuple(
        ExtractiveExcerpt(
            item.hit,
            item.excerpt,
            item.language,
            item.start,
            item.end,
        )
        for item in selected
    )


def _spans(text: str):
    for match in _SPAN_PATTERN.finditer(text):
        raw = match.group(0)
        start = match.start() + len(raw) - len(raw.lstrip())
        end = match.end() - (len(raw) - len(raw.rstrip()))
        excerpt = text[start:end]
        if excerpt:
            yield excerpt, start, end


def _is_safe_prose(excerpt: str) -> bool:
    if not _MIN_EXCERPT_CHARACTERS <= len(excerpt) <= MAX_EXCERPT_CHARACTERS:
        return False
    if "|" in excerpt or "\t" in excerpt:
        return False
    if len(_COLUMN_SEPARATOR_PATTERN.findall(excerpt)) >= 2:
        return False
    if not excerpt.endswith((".", "!", "?")):
        return False
    tokens = _TOKEN_PATTERN.findall(excerpt)
    if len(tokens) < 4:
        return False
    numeric_tokens = sum(
        any(character.isdigit() for character in token) for token in tokens
    )
    if numeric_tokens / len(tokens) >= 0.35:
        return False
    non_space = sum(not character.isspace() for character in excerpt)
    alphabetic = sum(character.isalpha() for character in excerpt)
    return non_space > 0 and alphabetic / non_space >= 0.55


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN_PATTERN.findall(_normalized(text)))


def _expanded_query_terms(tokens: Sequence[str]) -> frozenset[str]:
    terms = {token for token in tokens if len(token) >= 3 and token not in _STOPWORDS}
    expanded = set(terms)
    for concept in _TECHNICAL_CONCEPTS:
        if terms & concept:
            expanded.update(concept)
    return frozenset(expanded)


def _match_count(query_terms: frozenset[str], span_tokens: Sequence[str]) -> int:
    matched = set()
    for span_token in span_tokens:
        for query_term in query_terms:
            if _terms_match(query_term, span_token):
                matched.add(query_term)
    return len(matched)


def _terms_match(left: str, right: str) -> bool:
    if left == right:
        return True
    shortest = min(len(left), len(right))
    return shortest >= 5 and (left.startswith(right) or right.startswith(left))


def _detect_language(tokens: Sequence[str]) -> str | None:
    token_set = set(tokens)
    scores = {
        language: len(token_set & markers)
        for language, markers in _LANGUAGE_MARKERS.items()
    }
    best = max(scores.values(), default=0)
    winners = [
        language for language, score in scores.items() if score == best and score
    ]
    return winners[0] if len(winners) == 1 else None


def _requested_language(question: str) -> str | None:
    normalized = _normalized(question)
    requests = {
        "en": ("em ingles", "secao em ingles", "in english", "english section"),
        "pt": (
            "em portugues",
            "secao em portugues",
            "in portuguese",
            "portuguese section",
        ),
        "es": (
            "em espanhol",
            "secao em espanhol",
            "in spanish",
            "spanish section",
        ),
    }
    matches = [
        language
        for language, markers in requests.items()
        if any(marker in normalized for marker in markers)
    ]
    return matches[0] if len(matches) == 1 else None


def _single_document_language(raw: str) -> str | None:
    codes = {
        value.split("-", 1)[0].casefold()
        for value in re.split(r"[,;/\s]+", raw)
        if value
    }
    supported = codes & set(_LANGUAGE_MARKERS)
    return next(iter(supported)) if len(supported) == 1 else None


def _selected_language(
    candidates: Sequence[_Candidate], question_language: str | None
) -> str:
    if question_language and any(
        item.language == question_language for item in candidates
    ):
        return question_language
    return candidates[0].language


def _too_similar(left: frozenset[str], right: frozenset[str]) -> bool:
    union = left | right
    return bool(union) and len(left & right) / len(union) >= 0.8
