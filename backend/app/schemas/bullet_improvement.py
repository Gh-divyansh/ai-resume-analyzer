from pydantic import BaseModel


class BulletImprovementResponse(BaseModel):
    """A Gemini-assisted wording improvement grounded in one resume bullet."""

    original: str
    improved: str
    reason: str
    keywords_added: list[str]
    facts_used: list[str]
