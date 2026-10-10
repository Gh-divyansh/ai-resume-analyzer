"""Domain-neutral, deterministic factual-claim extraction for bullet safety."""

from __future__ import annotations

import re

from app.schemas.bullet_claims import BulletClaim, ClaimComparison, ClaimKind
from app.services.job_matcher import _contains_phrase, _skills_in_text


NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9.+#/-]*")
TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9.+#/-]*|\d+(?:\.\d+)?")
ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,}s?\b")
# A version label may be written with or without a separator: ``OS 2.0`` and
# ``OS2.0`` denote the same source-visible version. The no-space form is
# deliberately limited to an uppercase label followed by a dotted number.
VERSION_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z+#/-]*)(?:\s+(?:version|v))?(?:\s+|(?<=[A-Z]))(\d+(?:\.\d+)+)\b",
    re.IGNORECASE,
)
EXPANDED_VERSION_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z+#/-]*\s+)*([A-Z][A-Za-z+#/-]*\s+[A-Z][A-Za-z+#/-]*)\s+(\d+(?:\.\d+)+)\b"
)
PARENTHETICAL_ENUMERATION_PATTERN = re.compile(r"\(([^()]*)\)")
CONTEXTUAL_ENTITY_PATTERN = re.compile(
    r"\b(?:at|from|by|for|with)\s+(?:the\s+|a\s+|an\s+)?"
    r"((?:[A-Z][A-Za-z0-9/-]*\s+){1,}[A-Z][A-Za-z0-9/-]*)"
)
STRUCTURED_TITLE_PATTERN = re.compile(
    r"^\s*((?:[A-Z][A-Za-z0-9/-]*\s+){1,}[A-Z][A-Za-z0-9/-]*"
    r"\s*&\s*(?:[A-Z][A-Za-z0-9/-]*\s+)*[A-Z][A-Za-z0-9/-]*)"
    r"\s*(?:[-:]\s*[a-z]|[,\.])"
)
CONTEXTUAL_WORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "the", "to", "with",
    "that", "this", "these", "those", "using", "via", "while", "within", "across", "through", "including", "s",
}
PREDICATE_PRECEDERS = {"and", "but", "that", "which", "who", "then", "while"}
ACHIEVEMENT_TERMS = {"award", "prize", "medal", "trophy", "honor", "honour", "finalist", "winner"}
ORDINAL_TERMS = {
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth",
    "eighteenth", "nineteenth", "twentieth",
}
CREDENTIAL_TERMS = {
    "certified", "certification", "certificate", "credential", "licensed", "licence", "license",
    "registered", "registration", "degree", "diploma",
}

# These are material-claim indicators, not a verb synonym dictionary. They
# identify expanded authority, ownership, or organizational scope that needs
# explicit source evidence before a generated bullet may assert it.
MATERIAL_RESPONSIBILITY_PATTERNS = {
    "leadership": ("lead", "led", "leading", "manage", "managed", "managing", "oversee", "oversaw", "overseeing", "supervise", "supervised", "supervising", "mentor", "mentored", "mentoring"),
    "ownership": ("own", "owned", "owning", "ownership", "direct", "directed", "directing"),
    "architecture": ("architect", "architected", "architecting"),
    "seniority": ("senior", "principal", "staff", "director", "head"),
    "organizational_scope": ("team", "department", "division", "enterprise", "organization", "portfolio"),
}


def _term_base(term: str) -> str:
    lowered = term.casefold().strip(".+#/-")
    return lowered[:-1] if lowered.isalpha() and len(lowered) > 3 and lowered.endswith("s") and not lowered.endswith("ss") else lowered


def _claim_key(claim: BulletClaim) -> tuple[ClaimKind, str]:
    value = claim.value.casefold()
    if claim.kind is ClaimKind.version:
        value = re.sub(r"\s+", "", value)
    return claim.kind, value


def _normalised_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _version_parts(value: str) -> tuple[str, str]:
    label, number = value.rsplit(" ", maxsplit=1)
    return label.strip(), number


def _version_labels_match(source_label: str, generated_label: str) -> bool:
    normalized_source = _normalised_text(source_label)
    normalized_generated = _normalised_text(generated_label)
    if normalized_source == normalized_generated:
        return True
    # A documented acronym can be expanded naturally in generated prose when
    # the ordered initials match (``OS`` -> ``Online Store``). This applies
    # only to a version claim with the exact same dotted number, never to
    # general technologies, entities, responsibilities, or skills.
    return (
        source_label.isupper()
        and len(source_label) >= 2
        and " " in normalized_generated
        and "".join(part[0] for part in normalized_generated.split()) == source_label.casefold()
    )


def _versions_match(source: BulletClaim, generated: BulletClaim) -> bool:
    if source.kind is not ClaimKind.version or generated.kind is not ClaimKind.version:
        return False
    source_label, source_number = _version_parts(source.value)
    generated_label, generated_number = _version_parts(generated.value)
    return source_number == generated_number and _version_labels_match(source_label, generated_label)


def extract_factual_claims(text: str) -> list[BulletClaim]:
    """Extract bounded, source-visible claims without inferring occupation facts.

    Capitalization alone is deliberately not evidence of a named entity: resume
    headings commonly title-case ordinary domain concepts. Named entities need
    a structural context (for example, an event after ``at``) or a structured
    product/project title marker. Concepts, actions, and qualifiers are not
    promoted to factual claims merely because they are capitalized.
    """

    claims: dict[tuple[ClaimKind, str], BulletClaim] = {}

    def add(kind: ClaimKind, value: str) -> None:
        cleaned = value.strip()
        if cleaned:
            claim = BulletClaim(kind=kind, value=cleaned, source_text=text)
            claims[_claim_key(claim)] = claim

    for skill in _skills_in_text(text):
        add(ClaimKind.technology, skill)
    expanded_version_spans: list[tuple[int, int]] = []
    for match in EXPANDED_VERSION_PATTERN.finditer(text):
        label, number = match.groups()
        # Preserve only the final two title-cased words as the expanded label.
        # It avoids treating surrounding prose (for example, "Shopify's") as
        # part of the version while retaining "Online Store 2.0".
        label = " ".join(label.split()[-2:])
        add(ClaimKind.version, f"{label} {number}")
        expanded_version_spans.append(match.span())
    version_acronyms: set[str] = set()
    for match in VERSION_PATTERN.finditer(text):
        if any(start <= match.start() and match.end() <= end for start, end in expanded_version_spans):
            continue
        product, number = match.groups()
        add(ClaimKind.version, f"{product} {number}")
        if ACRONYM_PATTERN.fullmatch(product):
            version_acronyms.add(_term_base(product))
    for acronym in ACRONYM_PATTERN.findall(text):
        if _term_base(acronym) in version_acronyms:
            continue
        add(ClaimKind.acronym, _term_base(acronym))

    tokens = TOKEN_PATTERN.findall(text)
    for index, token in enumerate(tokens):
        base = _term_base(token)
        if not base:
            continue
        if base in ACHIEVEMENT_TERMS or base in ORDINAL_TERMS:
            add(ClaimKind.achievement, base)
        if base in CREDENTIAL_TERMS:
            add(ClaimKind.credential, base)
    for match in CONTEXTUAL_ENTITY_PATTERN.finditer(text):
        phrase = match.group(1)
        # "REST API" and similar all-acronym phrases are tools/interfaces,
        # not named organizations or events. Their individual acronym claims
        # already protect the factual components.
        if not all(ACRONYM_PATTERN.fullmatch(part) for part in phrase.split()):
            add(ClaimKind.named_entity, phrase)
    for match in STRUCTURED_TITLE_PATTERN.finditer(text):
        add(ClaimKind.named_entity, match.group(1))

    for claim_type, markers in MATERIAL_RESPONSIBILITY_PATTERNS.items():
        if any(_contains_phrase(text, marker) for marker in markers):
            add(ClaimKind.material_responsibility, claim_type)

    return sorted(claims.values(), key=lambda claim: (claim.kind.value, claim.value.casefold()))


def _introduced_material_content(source: str, generated: str) -> list[str]:
    """Return generated content that is not grammatical rewording or source evidence.

    This is intentionally part of factual-claim comparison rather than an
    independent word-preservation gate. It only catches material additions
    that are neither source-anchored nor a predicate at a clause boundary.
    """

    source_terms = {_term_base(term) for term in WORD_PATTERN.findall(source)}
    source_terms.update(
        _term_base(component)
        for term in WORD_PATTERN.findall(source)
        for component in re.split(r"[/-]", term)
        if component
    )
    source_compact_versions = {
        re.sub(r"\s+", "", claim.value.casefold())
        for claim in extract_factual_claims(source)
        if claim.kind is ClaimKind.version
    }
    source_enumeration_terms = {
        _term_base(term)
        for match in PARENTHETICAL_ENUMERATION_PATTERN.finditer(source)
        for term in WORD_PATTERN.findall(match.group(1))
    }
    source_versions = [
        claim for claim in extract_factual_claims(source) if claim.kind is ClaimKind.version
    ]
    generated_versions = [
        claim for claim in extract_factual_claims(generated) if claim.kind is ClaimKind.version
    ]
    matched_generated_versions = [
        claim
        for claim in generated_versions
        if any(_versions_match(source_version, claim) for source_version in source_versions)
    ]
    generated_version_context_terms = {
        _term_base(part)
        for claim in matched_generated_versions
        for part in _version_parts(claim.value)[0].split()
    }
    matched_version_numbers = {_version_parts(claim.value)[1] for claim in matched_generated_versions}
    generated_tokens = TOKEN_PATTERN.findall(generated)
    generated_terms = [_term_base(token) for token in generated_tokens]
    generated_enumeration_terms = source_enumeration_terms & set(generated_terms)
    is_enumeration_rewrite = len(source_enumeration_terms) >= 2 and len(generated_enumeration_terms) >= 2
    introduced: set[str] = set()
    for index, token in enumerate(generated_tokens):
        if token[0].isdigit():
            continue
        term = _term_base(token)
        previous = _term_base(generated_tokens[index - 1]) if index else ""
        if (
            not term
            or term in CONTEXTUAL_WORDS
            or term in source_terms
            or term in source_compact_versions
            or term in generated_version_context_terms
        ):
            continue
        # The leading word of a clause and a predicate after a connector are
        # wording positions, not evidence positions. This is a structural
        # grammar rule, not a configurable action/synonym list.
        if index == 0 or previous in PREDICATE_PRECEDERS:
            continue
        # A regular verb form is process wording rather than factual evidence.
        # Material verbs such as management, leadership, ownership, and
        # architecture remain independently protected factual claims; numbers,
        # credentials, technologies, entities, and new material objects still
        # pass through their dedicated guards. This avoids treating ordinary
        # verbs such as "utilizing" as invented resume facts.
        if term.endswith(("ed", "ing")):
            continue
        # A parenthetical source enumeration describes a bounded set of
        # documented categories. In a natural rewrite each category may take
        # one immediately trailing classifier (``payment gateways, shipping
        # providers, CRM systems``). This is structural list realization, not
        # a dictionary of profession-specific terms; all other additions,
        # including multiple new words or terms outside the enumeration,
        # remain material content.
        if is_enumeration_rewrite and previous in source_enumeration_terms:
            continue
        # Generated prose may append one grammatical classifier immediately to
        # a version phrase (for example, "Online Store 2.0 system"). The
        # version itself has already matched exactly; additional words beyond
        # this one continue through the normal material-content guard.
        if previous in matched_version_numbers:
            continue
        introduced.add(term)
    return sorted(introduced)


def compare_factual_claims(source: str, generated: str) -> ClaimComparison:
    source_claims = extract_factual_claims(source)
    generated_claims = extract_factual_claims(generated)
    source_by_key = {_claim_key(claim): claim for claim in source_claims}
    generated_by_key = {_claim_key(claim): claim for claim in generated_claims}
    source_text = _normalised_text(source)
    generated_text = _normalised_text(generated)

    def source_entity_is_present(claim: BulletClaim) -> bool:
        return claim.kind is ClaimKind.named_entity and _normalised_text(claim.value) in generated_text

    def generated_entity_is_anchored(claim: BulletClaim) -> bool:
        return claim.kind is ClaimKind.named_entity and _normalised_text(claim.value) in source_text

    def source_version_is_present(claim: BulletClaim) -> bool:
        return claim.kind is ClaimKind.version and any(
            _versions_match(claim, generated_claim) for generated_claim in generated_claims
        )

    def generated_version_is_anchored(claim: BulletClaim) -> bool:
        return claim.kind is ClaimKind.version and any(
            _versions_match(source_claim, claim) for source_claim in source_claims
        )

    return ClaimComparison(
        source_claims=source_claims,
        generated_claims=generated_claims,
        missing_claims=[
            source_by_key[key]
            for key in sorted(source_by_key.keys(), key=lambda key: (key[0].value, key[1]))
            if key not in generated_by_key
            and not source_entity_is_present(source_by_key[key])
            and not source_version_is_present(source_by_key[key])
        ],
        introduced_claims=[
            generated_by_key[key]
            for key in sorted(generated_by_key.keys(), key=lambda key: (key[0].value, key[1]))
            if key not in source_by_key
            and not generated_entity_is_anchored(generated_by_key[key])
            and not generated_version_is_anchored(generated_by_key[key])
        ],
        introduced_material_content=_introduced_material_content(source, generated),
    )
