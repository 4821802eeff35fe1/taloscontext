from pydantic import BaseModel, Field


class GenerationResult(BaseModel):
    """The single-call structured output contract every text generation must satisfy.

    Kept deliberately flat and small — this is the one AI call per ordinary post
    (see ARCHITECTURE.md §5); nothing here should require a second call.
    """

    schema_version: int = 1
    topic: str
    category: str
    angle: str = ""
    title: str
    telegram_html: str
    plain_text: str
    cta_key: str | None = None
    image_prompt: str = ""
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    duplicate_fingerprint: str
    requires_review: bool = False
    risk_flags: list[str] = Field(default_factory=list)
