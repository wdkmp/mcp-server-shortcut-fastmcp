"""Shortcut API client with caching."""

from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://api.app.shortcut.com/api/v3"
CACHE_TTL = 300  # 5 minutes


class Cache:
    def __init__(self, ttl: int = CACHE_TTL):
        self._data: dict[str, Any] = {}
        self._loaded_at: float = 0
        self._ttl = ttl

    @property
    def is_stale(self) -> bool:
        return time.time() - self._loaded_at > self._ttl

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def values(self) -> list[Any]:
        return list(self._data.values())

    def set_many(self, items: list[tuple[str | int, Any]]):
        self._data = {str(k): v for k, v in items}
        self._loaded_at = time.time()


class ShortcutClient:
    def __init__(self, api_token: str):
        self._token = api_token
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Shortcut-Token": api_token, "Content-Type": "application/json"},
            timeout=30.0,
        )
        self._current_user: dict | None = None
        self._user_cache = Cache()
        self._team_cache = Cache()
        self._workflow_cache = Cache()
        self._custom_field_cache = Cache()

    def _get(self, path: str, **params) -> Any:
        r = self._http.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: dict | None = None) -> Any:
        r = self._http.post(path, json=json or {})
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, json: dict) -> Any:
        r = self._http.put(path, json=json)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> None:
        r = self._http.delete(path)
        r.raise_for_status()

    # ── Users ──────────────────────────────────────────────────

    def get_current_user(self) -> dict:
        if self._current_user:
            return self._current_user
        self._current_user = self._get("/member")
        return self._current_user

    def list_members(self) -> list[dict]:
        if self._user_cache.is_stale:
            members = self._get("/members")
            self._user_cache.set_many([(m["id"], m) for m in members])
        return self._user_cache.values()

    def get_member(self, member_id: str) -> dict | None:
        self.list_members()
        return self._user_cache.get(member_id)

    # ── Teams (Groups) ─────────────────────────────────────────

    def list_teams(self) -> list[dict]:
        if self._team_cache.is_stale:
            groups = self._get("/groups")
            self._team_cache.set_many([(g["id"], g) for g in groups])
        return self._team_cache.values()

    def get_team(self, team_id: str) -> dict | None:
        try:
            return self._get(f"/groups/{team_id}")
        except httpx.HTTPStatusError:
            return None

    # ── Workflows ──────────────────────────────────────────────

    def list_workflows(self) -> list[dict]:
        if self._workflow_cache.is_stale:
            workflows = self._get("/workflows")
            self._workflow_cache.set_many([(w["id"], w) for w in workflows])
        return self._workflow_cache.values()

    def get_workflow(self, workflow_id: int) -> dict | None:
        try:
            return self._get(f"/workflows/{workflow_id}")
        except httpx.HTTPStatusError:
            return None

    # ── Stories ────────────────────────────────────────────────

    def get_story(self, story_id: int) -> dict | None:
        try:
            return self._get(f"/stories/{story_id}")
        except httpx.HTTPStatusError:
            return None

    def get_story_history(self, story_id: int) -> list[dict]:
        try:
            return self._get(f"/stories/{story_id}/history")
        except httpx.HTTPStatusError:
            return []

    def search_stories(self, query: str, page_size: int = 25, next_token: str | None = None) -> dict:
        body: dict[str, Any] = {"query": query, "page_size": page_size, "detail": "full"}
        if next_token:
            body["next"] = next_token
        return self._post("/search/stories", json=body)

    def create_story(self, params: dict) -> dict:
        return self._post("/stories", json=params)

    def update_story(self, story_id: int, params: dict) -> dict:
        return self._put(f"/stories/{story_id}", json=params)

    def create_story_comment(self, story_id: int, params: dict) -> dict:
        return self._post(f"/stories/{story_id}/comments", json=params)

    def create_task(self, story_id: int, params: dict) -> dict:
        return self._post(f"/stories/{story_id}/tasks", json=params)

    def get_task(self, story_id: int, task_id: int) -> dict | None:
        try:
            return self._get(f"/stories/{story_id}/tasks/{task_id}")
        except httpx.HTTPStatusError:
            return None

    def update_task(self, story_id: int, task_id: int, params: dict) -> dict:
        return self._put(f"/stories/{story_id}/tasks/{task_id}", json=params)

    def create_story_link(self, params: dict) -> dict:
        return self._post("/story-links", json=params)

    def get_stories_by_external_link(self, external_link: str) -> list[dict]:
        return self._get("/external-link/stories", external_link=external_link)

    # ── Epics ──────────────────────────────────────────────────

    def get_epic(self, epic_id: int) -> dict | None:
        try:
            return self._get(f"/epics/{epic_id}")
        except httpx.HTTPStatusError:
            return None

    def search_epics(self, query: str, page_size: int = 25, next_token: str | None = None) -> dict:
        body: dict[str, Any] = {"query": query, "page_size": page_size, "detail": "full"}
        if next_token:
            body["next"] = next_token
        return self._post("/search/epics", json=body)

    def create_epic(self, params: dict) -> dict:
        return self._post("/epics", json=params)

    def update_epic(self, epic_id: int, params: dict) -> dict:
        return self._put(f"/epics/{epic_id}", json=params)

    def delete_epic(self, epic_id: int) -> None:
        self._delete(f"/epics/{epic_id}")

    def create_epic_comment(self, epic_id: int, params: dict) -> dict:
        return self._post(f"/epics/{epic_id}/comments", json=params)

    def create_epic_comment_reply(self, epic_id: int, comment_id: int, params: dict) -> dict:
        return self._post(f"/epics/{epic_id}/comments/{comment_id}", json=params)

    # ── Iterations ─────────────────────────────────────────────

    def get_iteration(self, iteration_id: int) -> dict | None:
        try:
            return self._get(f"/iterations/{iteration_id}")
        except httpx.HTTPStatusError:
            return None

    def list_iterations(self) -> list[dict]:
        return self._get("/iterations")

    def list_iteration_stories(self, iteration_id: int, includes_description: bool = False) -> list[dict]:
        return self._get(f"/iterations/{iteration_id}/stories", includes_description=includes_description)

    def search_iterations(self, query: str, page_size: int = 25, next_token: str | None = None) -> dict:
        body: dict[str, Any] = {"query": query, "page_size": page_size, "detail": "full"}
        if next_token:
            body["next"] = next_token
        return self._post("/search/iterations", json=body)

    def create_iteration(self, params: dict) -> dict:
        return self._post("/iterations", json=params)

    def update_iteration(self, iteration_id: int, params: dict) -> dict:
        return self._put(f"/iterations/{iteration_id}", json=params)

    def delete_iteration(self, iteration_id: int) -> None:
        self._delete(f"/iterations/{iteration_id}")

    # ── Milestones (Objectives) ────────────────────────────────

    def get_milestone(self, milestone_id: int) -> dict | None:
        try:
            return self._get(f"/milestones/{milestone_id}")
        except httpx.HTTPStatusError:
            return None

    def search_milestones(self, query: str, page_size: int = 25, next_token: str | None = None) -> dict:
        body: dict[str, Any] = {"query": query, "page_size": page_size, "detail": "full"}
        if next_token:
            body["next"] = next_token
        return self._post("/search/milestones", json=body)

    # ── Labels ─────────────────────────────────────────────────

    def list_labels(self, slim: bool = False) -> list[dict]:
        return self._get("/labels", slim=slim)

    def create_label(self, params: dict) -> dict:
        return self._post("/labels", json=params)

    def list_label_stories(self, label_id: int) -> list[dict]:
        return self._get(f"/labels/{label_id}/stories")

    # ── Projects ───────────────────────────────────────────────

    def list_projects(self) -> list[dict]:
        return self._get("/projects")

    def get_project(self, project_id: int) -> dict | None:
        try:
            return self._get(f"/projects/{project_id}")
        except httpx.HTTPStatusError:
            return None

    def list_project_stories(self, project_id: int) -> list[dict]:
        return self._get(f"/projects/{project_id}/stories")

    # ── Custom Fields ──────────────────────────────────────────

    def list_custom_fields(self) -> list[dict]:
        if self._custom_field_cache.is_stale:
            fields = self._get("/custom-fields")
            self._custom_field_cache.set_many([(f["id"], f) for f in fields])
        return self._custom_field_cache.values()

    # ── Documents ──────────────────────────────────────────────

    def list_docs(self) -> list[dict]:
        return self._get("/docs")

    def get_doc(self, doc_id: str) -> dict | None:
        try:
            return self._get(f"/docs/{doc_id}")
        except httpx.HTTPStatusError:
            return None

    def create_doc(self, params: dict) -> dict:
        return self._post("/docs", json=params)

    def update_doc(self, doc_id: str, params: dict) -> dict:
        return self._put(f"/docs/{doc_id}", json=params)

    def search_docs(self, params: dict) -> dict:
        return self._post("/docs/search", json=params)
