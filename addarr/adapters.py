"""
Filename: adapters.py
Author: Christian Blank
Created Date: 2026-09-11
Description: Radarr, Sonarr and Lidarr API calls, request submission and remote reconciliation.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from .domain import MediaRef, Options, SearchResult, ServiceConfig, ServiceError
from .store import Store


class ArrClient:
    """API adapter for one configured Arr instance.

    The caller owns the HTTP client and Store. Remote media IDs belong to this
    instance; catalog IDs in MediaRef are used to reconcile interrupted adds.
    Search commands have a separate persistent ledger to avoid blind replay.
    """
    def __init__(self, config: ServiceConfig, store: Store, client: httpx.AsyncClient):
        self.config, self.store, self.client = config, store, client
        version = "v1" if config.kind == "lidarr" else "v3"
        self.base = f"{str(config.url).rstrip('/')}/api/{version}/"
        self.instance = hashlib.sha256(self.base.encode()).hexdigest()[:16]

    def identity(self, ref: MediaRef) -> str:
        """Return the service-instance and parent-media key used to detect address changes.

        Albums share their artist key; their own identity and options remain part
        of the request scope computed by Engine.create().
        """
        return f"{ref.service}:{self.instance}:{ref.artist_id or ref.external_id}"

    async def call(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, data: Any = None
    ) -> Any:
        """Send an authenticated request to a relative Arr API path.

        Args:
            method: HTTP verb.
            path: Endpoint relative to this instance's versioned API base.
            params: Optional query parameters.
            data: Optional JSON request body.

        Returns:
            Decoded JSON, or None for an empty response body.

        Raises:
            ServiceError: Network, status or JSON decoding failure. Messages omit
                response bodies and credentials. A timeout may follow an accepted
                write, so callers must reconcile before retrying it.
        """
        try:
            auth = (
                httpx.BasicAuth(self.config.username, self.config.password) if self.config.username else None
            )
            response = await self.client.request(
                method,
                self.base + path,
                headers={"X-Api-Key": self.config.api_key},
                auth=auth,
                params=params,
                json=data,
                timeout=httpx.Timeout(20, connect=5),
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ServiceError("network", "Service connection failed or timed out", True) from exc
        if response.status_code in (401, 403):
            raise ServiceError("credentials", "Service credentials were rejected")
        if response.status_code == 429 or response.status_code >= 500:
            raise ServiceError(
                "unavailable", f"Service temporarily unavailable (HTTP {response.status_code})", True
            )
        if not response.is_success:
            raise ServiceError("validation", f"Service rejected the operation (HTTP {response.status_code})")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ServiceError("response", "Service returned invalid JSON") from exc

    async def capabilities(self) -> dict[str, Any]:
        """Fetch version, quality profiles, root folders and Lidarr metadata profiles.

        Returns keys version, profiles, folders and metadata. Non-Lidarr services
        return an empty metadata list. Malformed choices raise ServiceError.
        """
        status, profiles, folders = await asyncio.gather(
            self.call("GET", "system/status"),
            self.call("GET", "qualityprofile"),
            self.call("GET", "rootfolder"),
        )
        metadata = await self.call("GET", "metadataprofile") if self.config.kind == "lidarr" else []
        if not isinstance(status, dict):
            raise ServiceError("response", "Service returned an invalid status response")
        for choices, fields in (
            (profiles, {"id": int, "name": str}),
            (folders, {"path": str}),
            (metadata, {"id": int, "name": str}),
        ):
            if not isinstance(choices, list) or any(
                not isinstance(item, dict)
                or any(not isinstance(item.get(key), expected) for key, expected in fields.items())
                for item in choices
            ):
                raise ServiceError("response", "Service returned invalid profiles or root folders")
        return {
            "version": status.get("version", "unknown"),
            "profiles": profiles,
            "folders": folders,
            "metadata": metadata,
        }

    async def search(self, term: str, kind: str = "") -> list[SearchResult]:
        """Return up to 30 catalog results with usable external identities.

        kind selects album lookup for Lidarr; other lookups follow the configured
        service. Albums without a parent artist ID are omitted.
        """
        endpoint = {"radarr": "movie", "sonarr": "series", "lidarr": "artist"}[self.config.kind]
        if self.config.kind == "lidarr" and kind == "album":
            endpoint = "album"
        rows = await self.call("GET", endpoint + "/lookup", params={"term": term})
        if not isinstance(rows, list):
            raise ServiceError("response", "Unexpected search response")
        output = []
        for row in rows[:30]:
            external = row.get(
                {
                    "movie": "tmdbId",
                    "series": "tvdbId",
                    "artist": "foreignArtistId",
                    "album": "foreignAlbumId",
                }[endpoint]
            )
            artist_id = row.get("artist", {}).get("foreignArtistId") if endpoint == "album" else None
            if not external or (endpoint == "album" and not artist_id):
                continue
            title = row.get("title") or row.get("artistName") or str(external)
            if endpoint == "album":
                title += " — " + row.get("artist", {}).get("artistName", "")
            images = row.get("images", [])
            image = next(
                (
                    i.get("remoteUrl") or i.get("url", "")
                    for i in images
                    if i.get("coverType") in ("poster", "cover")
                ),
                "",
            )
            output.append(
                SearchResult(
                    ref=MediaRef.model_validate(
                        dict(
                            service=self.config.kind,
                            external_id=str(external),
                            title=title,
                            kind=endpoint,
                            artist_id=artist_id,
                        )
                    ),
                    overview=row.get("overview", "") or "",
                    image=image,
                    seasons=[s["seasonNumber"] for s in row.get("seasons", [])],
                )
            )
        field = {"movie": "tmdbId", "series": "tvdbId", "artist": "foreignArtistId", "album": "foreignAlbumId"}[endpoint]
        library = await self.call("GET", endpoint)
        if not isinstance(library, list) or any(not isinstance(item, dict) for item in library):
            raise ServiceError("response", "Service returned an invalid library response")
        known = {str(item.get(field)) for item in library}
        for result in output:
            result.in_library = result.ref.external_id in known
        return output

    async def validate_options(self, options: Options) -> Options:
        """Copy options, fill service defaults and check current profiles and folders.

        The input object is unchanged. Raises ServiceError when a choice is absent
        from the remote service or excluded by a configured allowlist.
        """
        caps = await self.capabilities()
        opts = options.model_copy(deep=True)
        opts.quality_profile = opts.quality_profile or self.config.quality_profile
        opts.root_folder = opts.root_folder or self.config.root_folder
        opts.metadata_profile = opts.metadata_profile or self.config.metadata_profile
        profiles = {p["id"] for p in caps["profiles"]}
        folders = {p["path"] for p in caps["folders"]}
        if opts.quality_profile not in profiles or (
            self.config.allowed_profiles and opts.quality_profile not in self.config.allowed_profiles
        ):
            raise ServiceError("configuration", "Choose an available, permitted quality profile")
        if opts.root_folder not in folders or (
            self.config.allowed_folders and opts.root_folder not in self.config.allowed_folders
        ):
            raise ServiceError("configuration", "Choose an available, permitted root folder")
        if self.config.kind == "lidarr" and opts.metadata_profile not in {p["id"] for p in caps["metadata"]}:
            raise ServiceError("configuration", "Choose an available metadata profile")
        return opts

    async def lookup(self, endpoint: str, external: str, field: str) -> dict[str, Any]:
        """Look up an exact catalog ID and raise ServiceError if the response has no match."""
        prefix = {"movie": "tmdb", "series": "tvdb", "artist": "lidarr", "album": "lidarr"}[endpoint]
        rows = await self.call("GET", endpoint + "/lookup", params={"term": f"{prefix}:{external}"})
        match = next((row for row in rows if str(row.get(field)) == external), None)
        if not match:
            raise ServiceError("identity", "The exact selected item is no longer available")
        return dict(match)

    async def existing(self, endpoint: str, field: str, external: str) -> dict[str, Any] | None:
        """Find an existing library entry by external ID, returning None when absent."""
        rows = await self.call("GET", endpoint)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ServiceError("response", "Service returned an invalid library response")
        return next((dict(row) for row in rows if str(row.get(field)) == external), None)

    async def already_in_library(self, ref: MediaRef, options: Options) -> bool:
        """Check the live library before accepting a new request.

        Existing movies and whole-series/artist requests are duplicates even if
        downloads are incomplete. Selected seasons and albums can still request
        missing, unmonitored parts of an existing library entry. This guard is
        for new requests; submit() must remain able to recover interrupted adds.
        """
        endpoint = "artist" if ref.kind == "album" else ref.kind
        field = {"movie": "tmdbId", "series": "tvdbId", "artist": "foreignArtistId"}[endpoint]
        item = await self.existing(endpoint, field, ref.artist_id or ref.external_id)
        if item is None:
            return False
        if ref.kind == "series" and options.monitoring == "selected" and options.seasons:
            episodes = await self.call("GET", "episode", params={"seriesId": item["id"]})
            seasons = {season["seasonNumber"]: season for season in item.get("seasons", [])}
            for number in options.seasons:
                season = seasons.get(number, {})
                files = [episode for episode in episodes if episode["seasonNumber"] == number]
                if not season.get("monitored") and not (files and all(e.get("hasFile") for e in files)):
                    return False
            return True
        if ref.kind == "album":
            albums = await self.call("GET", "album", params={"artistId": item["id"]})
            album = next((a for a in albums if str(a.get("foreignAlbumId")) == ref.external_id), None)
            if album is None:
                return False
            stats = album.get("statistics", {})
            total = stats.get("totalTrackCount", stats.get("trackCount", 0))
            return bool(album.get("monitored") or total > 0 and stats.get("trackFileCount", 0) >= total)
        if ref.kind in ("series", "artist") and options.monitoring == "future":
            return bool(item.get("monitored") and item.get("monitorNewItems") == "all")
        return True

    async def tags(self, user_id: int) -> list[int]:
        """Resolve configured tag labels to remote IDs, creating missing tags as needed."""
        labels = list(self.config.tags)
        if self.config.requester_tag:
            labels.append(f"requester-{user_id}")
        if not labels:
            return []
        existing = await self.call("GET", "tag")
        output = []
        for label in labels:
            tag = next((t for t in existing if t["label"] == label), None)
            if not tag:
                tag = await self.call("POST", "tag", data={"label": label})
            output.append(tag["id"])
        return output

    async def command(self, key: str, name: str, arguments: dict[str, Any]) -> None:
        """Submit a search command once per instance-scoped operation key.

        The ledger records uncertainty before sending the POST. A later attempt
        checks remote command history for matching arguments. If no match proves
        acceptance, raise ServiceError rather than replay an ambiguous write.
        Definitive credential or validation rejection removes the ledger entry.
        """
        key = f"{self.instance}:{key}"
        operation = self.store.one("SELECT * FROM operations WHERE key=?", (key,))
        if operation and operation["state"] == "done":
            return
        if operation:
            commands = await self.call("GET", "command")
            for command in commands:
                body = command.get("body", {})
                if command.get("name", body.get("name")) == name and all(
                    body.get(k) == v for k, v in arguments.items()
                ):
                    self.store.execute(
                        "UPDATE operations SET state='done',remote_id=? WHERE key=?", (command.get("id"), key)
                    )
                    return
            raise ServiceError(
                "uncertain", "Search outcome needs review in the media service; automatic replay stopped"
            )
        self.store.execute("INSERT INTO operations(key,state) VALUES(?,'uncertain')", (key,))
        try:
            result = await self.call("POST", "command", data={"name": name, **arguments})
        except ServiceError as exc:
            if exc.category in ("credentials", "validation"):
                self.store.execute("DELETE FROM operations WHERE key=?", (key,))
            raise
        self.store.execute(
            "UPDATE operations SET state='done',remote_id=? WHERE key=?", (result.get("id"), key)
        )

    async def submit(self, request_id: int, user_id: int, ref: MediaRef, options: Options) -> int:
        """Reconcile or add media, apply monitoring and issue configured searches.

        Args:
            request_id: Local request ID used to scope movie search commands.
            user_id: Telegram requester ID used by optional requester tags.
            ref: Catalog identity selected by the requester.
            options: Requested profiles, destination and monitoring scope.

        Returns:
            The remote movie, series or artist ID. Album requests return the
            parent artist ID; progress() resolves the album by its catalog ID.

        Existing library settings are retained while requested monitoring is
        added. Missing Lidarr album metadata raises a retryable ServiceError.
        Interrupted submissions must re-enter here to reconcile remote state.
        """
        opts = await self.validate_options(options)
        endpoint = "artist" if ref.kind == "album" else ref.kind
        field = {"movie": "tmdbId", "series": "tvdbId", "artist": "foreignArtistId"}[endpoint]
        external = ref.artist_id if ref.kind == "album" else ref.external_id
        assert external is not None
        item = await self.existing(endpoint, field, external)
        is_new = item is None
        if item is None:
            item = await self.lookup(endpoint, external, field)
            item.pop("id", None)
            item.update(
                qualityProfileId=opts.quality_profile,
                rootFolderPath=opts.root_folder,
                monitored=opts.monitoring != "none",
                tags=await self.tags(user_id),
            )
            if endpoint == "movie":
                item.update(
                    minimumAvailability=self.config.minimum_availability, addOptions={"searchForMovie": False}
                )
            elif endpoint == "series":
                item.update(
                    seasonFolder=self.config.season_folder,
                    monitorNewItems="none",
                    addOptions={"searchForMissingEpisodes": False, "monitor": "none"},
                )
                for season in item.get("seasons", []):
                    season["monitored"] = False
            else:
                item.update(
                    metadataProfileId=opts.metadata_profile,
                    monitorNewItems="none",
                    addOptions={"monitor": "none", "searchForMissingAlbums": False},
                )
            item = await self.call("POST", endpoint, data=item)
        remote_id = item["id"]
        # Restart reconciliation always continues configuring the remote object.
        command_name, command_args = "", {}
        if endpoint == "movie":
            if is_new or not item.get("hasFile"):
                command_name, command_args = "MoviesSearch", {"movieIds": [remote_id]}
        elif endpoint == "series":
            item = await self.call("GET", f"series/{remote_id}")
            selected = set(opts.seasons)
            if opts.monitoring == "selected" and not selected:
                raise ServiceError("validation", "Select at least one season")
            available = {s["seasonNumber"] for s in item.get("seasons", [])}
            if not selected.issubset(available):
                raise ServiceError("validation", "A selected season is no longer available")
            if opts.monitoring == "all":
                selected = available
            for season in item.get("seasons", []):
                if season["seasonNumber"] in selected:
                    season["monitored"] = True
            if opts.monitoring in ("all", "future"):
                item["monitorNewItems"] = "all"
            if opts.monitoring != "none":
                item["monitored"] = True
            await self.call("PUT", f"series/{remote_id}", data=item)
            if opts.monitoring == "future":
                episodes = await self.call("GET", "episode", params={"seriesId": remote_id})
                future_ids = [e["id"] for e in episodes if is_future(e.get("airDateUtc"))]
                if future_ids:
                    await self.call(
                        "PUT", "episode/monitor", data={"episodeIds": future_ids, "monitored": True}
                    )
            for season in sorted(selected):
                if self.config.search:
                    await self.command(
                        f"sonarr:{remote_id}:season:{season}",
                        "SeasonSearch",
                        {"seriesId": remote_id, "seasonNumber": season},
                    )
        else:
            albums = await self.call("GET", "album", params={"artistId": remote_id})
            if ref.kind == "album":
                selected_albums = [a for a in albums if a.get("foreignAlbumId") == ref.external_id]
                if not selected_albums:
                    raise ServiceError(
                        "metadata", "Waiting for artist metadata to include the selected album", True
                    )
            elif opts.monitoring == "all":
                if not albums:
                    raise ServiceError("metadata", "Waiting for artist album metadata", True)
                selected_albums = albums
            elif opts.monitoring == "future":
                selected_albums = [a for a in albums if is_future(a.get("releaseDate"))]
            else:
                selected_albums = []
            artist = await self.call("GET", f"artist/{remote_id}")
            if ref.kind == "artist" and opts.monitoring in ("all", "future"):
                artist["monitorNewItems"] = "all"
            elif is_new or (ref.kind == "album" and not artist.get("monitored")):
                artist["monitorNewItems"] = "none"
            if opts.monitoring != "none":
                artist["monitored"] = True
            await self.call("PUT", f"artist/{remote_id}", data=artist)
            ids = sorted(a["id"] for a in selected_albums)
            if ids:
                await self.call("PUT", "album/monitor", data={"albumIds": ids, "monitored": True})
                if self.config.search:
                    for album_id in ids:
                        await self.command(
                            f"lidarr:{remote_id}:album:{album_id}", "AlbumSearch", {"albumIds": [album_id]}
                        )
        if self.config.search and opts.monitoring != "none" and command_name:
            await self.command(f"{request_id}:search", command_name, command_args)
        return int(remote_id)

    async def progress(self, ref: MediaRef, options: Options, remote_id: int) -> tuple[bool, str]:
        """Return (complete, display_text) from files reported by the Arr service.

        Selected seasons and individual albums can finish. Open-ended series or
        artist monitoring stays incomplete so later releases continue to be polled.
        The display text is capped at 2,000 characters.
        """
        if ref.kind == "movie":
            row = await self.call("GET", f"movie/{remote_id}")
            return bool(row.get("hasFile")), "1/1" if row.get("hasFile") else "0/1"
        if ref.kind == "series":
            episodes = await self.call("GET", "episode", params={"seriesId": remote_id})
            seasons = sorted(
                set(options.seasons)
                if options.monitoring == "selected"
                else {e["seasonNumber"] for e in episodes}
            )
            totals = [(s, [e for e in episodes if e["seasonNumber"] == s]) for s in seasons]
            complete = bool(totals) and all(es and all(e.get("hasFile") for e in es) for _, es in totals)
            text = ", ".join(f"S{s}: {sum(bool(e.get('hasFile')) for e in es)}/{len(es)}" for s, es in totals)
        else:
            albums = await self.call("GET", "album", params={"artistId": remote_id})
            if ref.kind == "album":
                albums = [a for a in albums if a.get("foreignAlbumId") == ref.external_id]

            def counts(album: dict[str, Any]) -> tuple[int, int]:
                stats = album.get("statistics", {})
                return stats.get("trackFileCount", 0), stats.get(
                    "totalTrackCount", stats.get("trackCount", 0)
                )

            complete = bool(albums) and all(counts(a)[1] > 0 and counts(a)[0] >= counts(a)[1] for a in albums)
            text = ", ".join(f"{a.get('title', '')}: {counts(a)[0]}/{counts(a)[1]}" for a in albums)
        if options.monitoring in ("all", "future", "none") and ref.kind != "album":
            complete = False
        return complete, text[:2000]


def configured_clients(store: Store, http: httpx.AsyncClient) -> dict[str, ArrClient]:
    """Build adapters for saved, enabled services using the caller-owned HTTP client."""
    clients = {}
    for kind in ("radarr", "sonarr", "lidarr"):
        raw = store.setting(f"service:{kind}")
        if raw:
            config = ServiceConfig.model_validate(raw)
            if config.enabled:
                clients[kind] = ArrClient(config, store, http)
    return clients


def is_future(value: str | None) -> bool:
    """Compare an ISO date to UTC now; assume UTC when naive and return False for invalid input."""
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc) > datetime.now(timezone.utc)
    except ValueError:
        return False
