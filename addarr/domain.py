"""
Filename: domain.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Shared models for service configuration, media identities and request options.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class ServiceKind(StrEnum):
    """Supported Arr services and their persisted configuration keys."""
    RADARR = "radarr"
    SONARR = "sonarr"
    LIDARR = "lidarr"


class ServiceConfig(BaseModel):
    """Connection details and request defaults for one Arr service.

    Empty allowlists permit any profile or folder offered by that service.
    Credentials are stored with the configuration and must not be logged or
    included in validation messages shown to users.
    """
    kind: ServiceKind
    url: HttpUrl
    api_key: str = Field(min_length=1)
    enabled: bool = True
    username: str = ""
    password: str = ""
    quality_profile: int | None = None
    root_folder: str = ""
    metadata_profile: int | None = None
    allowed_profiles: list[int] = Field(default_factory=list)
    allowed_folders: list[str] = Field(default_factory=list)
    search: bool = True
    minimum_availability: Literal["announced", "inCinemas", "released"] = "released"
    season_folder: bool = True
    tags: list[str] = Field(default_factory=list)
    requester_tag: bool = False

    @model_validator(mode="after")
    def base_url_only(self) -> "ServiceConfig":
        """Reject query strings, fragments and credentials embedded in the service URL."""
        if self.url.query or self.url.fragment or self.url.username or self.url.password:
            raise ValueError("Use a base URL without query, fragment or embedded credentials")
        return self


class MediaRef(BaseModel):
    """Catalog identity captured when a user selects a search result.

    external_id is a TMDB, TVDB or MusicBrainz identifier, not an Arr database
    row ID. Album requests also carry the MusicBrainz artist_id so submission
    can locate their parent artist in Lidarr.
    """
    service: ServiceKind
    external_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    kind: Literal["movie", "series", "artist", "album"]
    artist_id: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> "MediaRef":
        """Reject mismatched service/media types and albums without an artist identity."""
        expected = {"movie": "radarr", "series": "sonarr", "artist": "lidarr", "album": "lidarr"}
        if self.service != expected[self.kind]:
            raise ValueError("Media kind does not match service")
        if self.kind == "album" and not self.artist_id:
            raise ValueError("Album requests require an artist identity")
        return self


class Options(BaseModel):
    """Requested profiles, destination and monitoring scope, before service defaults are applied."""
    quality_profile: int | None = None
    root_folder: str = ""
    metadata_profile: int | None = None
    monitoring: Literal["selected", "all", "future", "none"] = "all"
    seasons: list[int] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A selectable catalog item with the details needed for its preview and season choices."""
    ref: MediaRef
    overview: str = ""
    image: str = ""
    seasons: list[int] = Field(default_factory=list)
    in_library: bool = False


class ServiceError(Exception):
    """Service failure with a safe display message and an explicit retry decision.

    category identifies the failure for diagnostics. retryable allows the
    request worker to schedule another attempt; it does not replay the call.
    """
    def __init__(self, category: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


Json = dict[str, Any]
