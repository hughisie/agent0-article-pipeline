from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    paths: list[str]
    skip_duplicates: bool = True


class RescanRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    mode: str | None = None
    skip_duplicates: bool | None = None


class ScanItem(BaseModel):
    index: int
    file_path: str
    basename: str
    article_no: str
    headline_raw: str
    headline_en_gb: str
    language: str
    is_duplicate: bool
    duplicate_reason: str | None = None
    fingerprint: str


class TranslateRequest(BaseModel):
    file_paths: list[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    file_paths: list[str]


class RunItem(BaseModel):
    file_path: str
    status: str
    wp_post_id: int | None = None
    wp_link: str | None = None
    link_report: dict | None = None
    errors: list[str] = Field(default_factory=list)
    duration_s: float | None = None


class SettingsPayload(BaseModel):
    data: dict
