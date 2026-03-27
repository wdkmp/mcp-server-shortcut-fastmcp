"""Shortcut MCP Server - FastMCP edition.

Provides full read/write access to Shortcut (project management) via MCP.
Set SHORTCUT_API_TOKEN env var. Optionally set SHORTCUT_READONLY=true.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastmcp import FastMCP

from shortcut_client import ShortcutClient

# ── Configuration ──────────────────────────────────────────────

API_TOKEN = os.environ.get("SHORTCUT_API_TOKEN") or os.environ.get("SHORTCUT_API_TKN", "")
READONLY = os.environ.get("SHORTCUT_READONLY", "false").lower() == "true"

mcp = FastMCP(
    "Shortcut",
    instructions=(
        "MCP server for Shortcut project management. "
        "Manage stories, epics, iterations, objectives, documents, labels, and more."
    ),
)

# Lazy-initialised client (token might not be available at import time)
_client: ShortcutClient | None = None


def client() -> ShortcutClient:
    global _client
    if _client is None:
        token = API_TOKEN
        if not token:
            raise RuntimeError(
                "SHORTCUT_API_TOKEN environment variable is required. "
                "Get one at https://app.shortcut.com/settings/account/api-tokens"
            )
        _client = ShortcutClient(token)
    return _client


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _write_guard():
    if READONLY:
        raise RuntimeError("Server is in read-only mode. Write operations are disabled.")


# ── Search query builder ───────────────────────────────────────

_KEY_RENAMES = {"name": "title"}


def _map_key(key: str) -> str:
    return _KEY_RENAMES.get(key.lower(), key.lower())


def _get_query_key(prop: str) -> str:
    if prop.startswith("is_"):
        return f"is:{_map_key(prop[3:])}"
    if prop.startswith("has_"):
        return f"has:{_map_key(prop[4:])}"
    return _map_key(prop)


def _build_search_query(params: dict[str, Any], current_user: dict | None = None) -> str:
    parts: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        q = _get_query_key(key)
        if key in ("owner", "requester"):
            if value == "me" and current_user:
                parts.append(f"{q}:{current_user.get('mention_name', value)}")
            else:
                parts.append(f"{q}:{str(value).lstrip('@')}")
        elif isinstance(value, bool):
            parts.append(q if value else f"!{q}")
        elif isinstance(value, int):
            parts.append(f"{q}:{value}")
        elif isinstance(value, str) and " " in value:
            parts.append(f'{q}:"{value}"')
        else:
            parts.append(f"{q}:{value}")
    return " ".join(parts)


def _extract_next_token(next_url: str | None) -> str | None:
    if not next_url:
        return None
    m = re.search(r"next=(.+?)(?:&|$)", next_url)
    return m.group(1) if m else None


# ── Simplified entity formatters ───────────────────────────────

def _slim_story(s: dict) -> dict:
    return {
        "id": s.get("id"),
        "name": s.get("name"),
        "app_url": s.get("app_url"),
        "archived": s.get("archived"),
        "story_type": s.get("story_type"),
        "team_id": s.get("group_id"),
        "epic_id": s.get("epic_id"),
        "iteration_id": s.get("iteration_id"),
        "workflow_state_id": s.get("workflow_state_id"),
        "owner_ids": s.get("owner_ids", []),
        "estimate": s.get("estimate"),
        "labels": [l.get("name") for l in s.get("labels", [])],
        "description": s.get("description", "")[:500],
    }


def _slim_epic(e: dict) -> dict:
    return {
        "id": e.get("id"),
        "name": e.get("name"),
        "app_url": e.get("app_url"),
        "archived": e.get("archived"),
        "state": e.get("state"),
        "team_id": e.get("group_id"),
        "objective_id": e.get("milestone_id"),
        "owner_ids": e.get("owner_ids", []),
    }


def _slim_iteration(i: dict) -> dict:
    return {
        "id": i.get("id"),
        "name": i.get("name"),
        "app_url": i.get("app_url"),
        "team_ids": i.get("group_ids", []),
        "status": i.get("status"),
        "start_date": i.get("start_date"),
        "end_date": i.get("end_date"),
    }


# ═══════════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def users_get_current() -> str:
    """Get the current authenticated Shortcut user."""
    user = client().get_current_user()
    return f"Current user:\n\n{_json(user)}"


@mcp.tool()
def users_get_current_teams() -> str:
    """Get teams where the current user is a member."""
    teams = client().list_teams()
    user = client().get_current_user()
    user_teams = [t for t in teams if not t.get("archived") and user["id"] in t.get("member_ids", [])]
    if not user_teams:
        return "Current user is not a member of any teams."
    return f"Current user is a member of {len(user_teams)} teams:\n\n{_json(user_teams)}"


@mcp.tool()
def users_list() -> str:
    """List all Shortcut workspace members."""
    members = client().list_members()
    return f"Found {len(members)} members:\n\n{_json(members)}"


# ═══════════════════════════════════════════════════════════════
#  STORIES
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def stories_get_by_id(story_id: int, full: bool = False) -> str:
    """Get a Shortcut story by its public ID.

    Args:
        story_id: The story public ID (e.g. 12345)
        full: Return all fields instead of a slim view
    """
    story = client().get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    data = story if full else _slim_story(story)
    return f"Story sc-{story_id}:\n\n{_json(data)}"


@mcp.tool()
def stories_get_history(story_id: int) -> str:
    """Get the change history for a Shortcut story.

    Args:
        story_id: The story public ID
    """
    story = client().get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    history = client().get_story_history(story_id)
    if not history:
        return f"No history found for story sc-{story_id}."
    return f"{len(history)} history entries for story sc-{story_id}:\n\n{_json(history)}"


@mcp.tool()
def stories_search(
    name: str | None = None,
    description: str | None = None,
    comment: str | None = None,
    type: str | None = None,
    estimate: int | None = None,
    epic: int | None = None,
    objective: int | None = None,
    state: str | None = None,
    label: str | None = None,
    owner: str | None = None,
    requester: str | None = None,
    team: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    is_done: bool | None = None,
    is_started: bool | None = None,
    is_unstarted: bool | None = None,
    is_overdue: bool | None = None,
    is_archived: bool = False,
    is_blocked: bool | None = None,
    is_blocker: bool | None = None,
    has_label: bool | None = None,
    has_deadline: bool | None = None,
    has_owner: bool | None = None,
    has_epic: bool | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for Shortcut stories using filters.

    Args:
        name: Story name contains this text
        description: Description contains
        comment: Comment contains
        type: Story type (feature, bug, chore)
        estimate: Point estimate
        epic: Epic ID
        objective: Objective ID
        state: Workflow state name
        label: Label name
        owner: Owner mention name or "me"
        requester: Requester mention name or "me"
        team: Team name or mention
        priority: Priority level
        severity: Severity level
        is_done: Filter completed stories
        is_started: Filter started stories
        is_unstarted: Filter unstarted stories
        is_overdue: Filter overdue stories
        is_archived: Include archived (default false)
        is_blocked: Filter blocked stories
        is_blocker: Filter blocking stories
        has_label: Has any label
        has_deadline: Has a deadline
        has_owner: Has an owner
        has_epic: Has an epic
        next_page_token: Pagination token from previous search
    """
    params = {}
    for k, v in {
        "name": name, "description": description, "comment": comment,
        "type": type, "estimate": estimate, "epic": epic,
        "objective": objective, "state": state, "label": label,
        "owner": owner, "requester": requester, "team": team,
        "priority": priority, "severity": severity,
        "is_done": is_done, "is_started": is_started,
        "is_unstarted": is_unstarted, "is_overdue": is_overdue,
        "is_archived": is_archived, "is_blocked": is_blocked,
        "is_blocker": is_blocker, "has_label": has_label,
        "has_deadline": has_deadline, "has_owner": has_owner,
        "has_epic": has_epic,
    }.items():
        if v is not None:
            params[k] = v

    current_user = client().get_current_user()
    query = _build_search_query(params, current_user)
    result = client().search_stories(query, next_token=next_page_token)

    stories = result.get("data", [])
    total = result.get("total", 0)
    token = _extract_next_token(result.get("next"))

    if not stories:
        return "No stories found."

    slim = [_slim_story(s) for s in stories]
    msg = f"{len(stories)} shown of {total} total stories found:\n\n{_json(slim)}"
    if token:
        msg += f"\n\nNext page token: {token}"
    return msg


@mcp.tool()
def stories_get_branch_name(story_id: int) -> str:
    """Get a valid git branch name for a story.

    Args:
        story_id: The story public ID
    """
    user = client().get_current_user()
    story = client().get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    branch = story.get("formatted_vcs_branch_name")
    if not branch:
        slug = re.sub(r"[^\w-]", "", re.sub(r"\s+", "-", story["name"].lower()))
        branch = f"{user.get('mention_name', 'user')}/sc-{story_id}/{slug}"[:50]
    return f"Branch name for story sc-{story_id}: {branch}"


@mcp.tool()
def stories_create(
    name: str,
    description: str | None = None,
    type: str = "feature",
    owner: str | None = None,
    epic: int | None = None,
    iteration: int | None = None,
    team: str | None = None,
    workflow: int | None = None,
) -> str:
    """Create a new Shortcut story. Requires name and either team or workflow.

    Args:
        name: Story name (required)
        description: Story description
        type: Story type - feature, bug, or chore
        owner: Owner user ID
        epic: Epic ID to assign to
        iteration: Iteration ID to assign to
        team: Team ID (required if no workflow)
        workflow: Workflow ID (required if no team)
    """
    _write_guard()
    c = client()

    if not workflow and not team:
        raise ValueError("Either team or workflow must be specified")

    if not workflow and team:
        full_team = c.get_team(team)
        if full_team and full_team.get("workflow_ids"):
            workflow = full_team["workflow_ids"][0]

    if not workflow:
        raise ValueError("Could not determine workflow for team")

    full_workflow = c.get_workflow(workflow)
    if not full_workflow:
        raise ValueError("Workflow not found")

    params: dict[str, Any] = {
        "name": name,
        "story_type": type,
        "workflow_state_id": full_workflow["default_state_id"],
    }
    if description:
        params["description"] = description
    if owner:
        params["owner_ids"] = [owner]
    if epic:
        params["epic_id"] = epic
    if iteration:
        params["iteration_id"] = iteration
    if team:
        params["group_id"] = team

    story = c.create_story(params)
    return f"Created story sc-{story['id']}. URL: {story.get('app_url', '')}"


@mcp.tool()
def stories_update(
    story_id: int,
    name: str | None = None,
    description: str | None = None,
    type: str | None = None,
    epic: int | None = None,
    estimate: int | None = None,
    iteration: int | None = None,
    owner_ids: list[str] | None = None,
    workflow_state_id: int | None = None,
    team_id: str | None = None,
    project_id: int | None = None,
    deadline: str | None = None,
    archived: bool | None = None,
) -> str:
    """Update a Shortcut story. Only provide fields you want to change.

    Args:
        story_id: Story ID (required)
        name: New story name
        description: New description
        type: Story type (feature, bug, chore)
        epic: Epic ID (use -1 to unset)
        estimate: Point estimate (use -1 to unset)
        iteration: Iteration ID (use -1 to unset)
        owner_ids: List of owner user UUIDs
        workflow_state_id: Workflow state ID
        team_id: Team UUID
        project_id: Project ID
        deadline: Due date ISO 8601
        archived: Archive the story
    """
    _write_guard()
    c = client()

    story = c.get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")

    params: dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if description is not None:
        params["description"] = description
    if type is not None:
        params["story_type"] = type
    if epic is not None:
        params["epic_id"] = None if epic == -1 else epic
    if estimate is not None:
        params["estimate"] = None if estimate == -1 else estimate
    if iteration is not None:
        params["iteration_id"] = None if iteration == -1 else iteration
    if owner_ids is not None:
        params["owner_ids"] = owner_ids
    if workflow_state_id is not None:
        params["workflow_state_id"] = workflow_state_id
    if team_id is not None:
        params["group_id"] = team_id
    if project_id is not None:
        params["project_id"] = None if project_id == -1 else project_id
    if deadline is not None:
        params["deadline"] = None if deadline == "" else deadline
    if archived is not None:
        params["archived"] = archived

    updated = c.update_story(story_id, params)
    return f"Updated story sc-{story_id}. URL: {updated.get('app_url', '')}"


@mcp.tool()
def stories_assign_current_user(story_id: int) -> str:
    """Assign the current user as owner of a story.

    Args:
        story_id: The story public ID
    """
    _write_guard()
    c = client()
    story = c.get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    user = c.get_current_user()
    if user["id"] in story.get("owner_ids", []):
        return f"Current user is already an owner of story sc-{story_id}"
    c.update_story(story_id, {"owner_ids": story["owner_ids"] + [user["id"]]})
    return f"Assigned current user as owner of story sc-{story_id}"


@mcp.tool()
def stories_unassign_current_user(story_id: int) -> str:
    """Remove the current user as owner of a story.

    Args:
        story_id: The story public ID
    """
    _write_guard()
    c = client()
    story = c.get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    user = c.get_current_user()
    if user["id"] not in story.get("owner_ids", []):
        return f"Current user is not an owner of story sc-{story_id}"
    c.update_story(story_id, {"owner_ids": [oid for oid in story["owner_ids"] if oid != user["id"]]})
    return f"Unassigned current user from story sc-{story_id}"


@mcp.tool()
def stories_create_comment(story_id: int, text: str, reply_to_comment_id: int | None = None) -> str:
    """Add a comment to a story.

    Args:
        story_id: The story public ID
        text: Comment text
        reply_to_comment_id: Optional comment ID to reply to
    """
    _write_guard()
    c = client()
    story = c.get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    params: dict[str, Any] = {"text": text}
    if reply_to_comment_id:
        params["parent_id"] = reply_to_comment_id
    comment = c.create_story_comment(story_id, params)
    return f"Created comment on story sc-{story_id}. Comment URL: {comment.get('app_url', '')}"


@mcp.tool()
def stories_create_subtask(parent_story_id: int, name: str, description: str | None = None) -> str:
    """Create a new story as a sub-task of an existing story.

    Args:
        parent_story_id: Parent story public ID
        name: Sub-task name
        description: Sub-task description
    """
    _write_guard()
    c = client()
    parent = c.get_story(parent_story_id)
    if not parent:
        raise ValueError(f"Parent story {parent_story_id} not found")

    workflow = c.get_workflow(parent["workflow_id"])
    if not workflow or not workflow.get("states"):
        raise ValueError("Could not determine workflow state")

    params: dict[str, Any] = {
        "name": name,
        "story_type": parent.get("story_type", "feature"),
        "epic_id": parent.get("epic_id"),
        "group_id": parent.get("group_id"),
        "workflow_state_id": workflow["states"][0]["id"],
        "parent_story_id": parent_story_id,
    }
    if description:
        params["description"] = description
    sub = c.create_story(params)
    return f"Created sub-task sc-{sub['id']}"


@mcp.tool()
def stories_add_subtask(parent_story_id: int, subtask_story_id: int) -> str:
    """Add an existing story as a sub-task of another story.

    Args:
        parent_story_id: Parent story public ID
        subtask_story_id: Story ID to make a sub-task
    """
    _write_guard()
    c = client()
    if not c.get_story(parent_story_id):
        raise ValueError(f"Parent story {parent_story_id} not found")
    if not c.get_story(subtask_story_id):
        raise ValueError(f"Story {subtask_story_id} not found")
    c.update_story(subtask_story_id, {"parent_story_id": parent_story_id})
    return f"Added story sc-{subtask_story_id} as sub-task of sc-{parent_story_id}"


@mcp.tool()
def stories_remove_subtask(subtask_story_id: int) -> str:
    """Remove a story from its parent (becomes a regular story).

    Args:
        subtask_story_id: The sub-task story ID
    """
    _write_guard()
    c = client()
    if not c.get_story(subtask_story_id):
        raise ValueError(f"Story {subtask_story_id} not found")
    c.update_story(subtask_story_id, {"parent_story_id": None})
    return f"Removed story sc-{subtask_story_id} from its parent"


@mcp.tool()
def stories_add_task(story_id: int, task_description: str, task_owner_ids: list[str] | None = None) -> str:
    """Add a task (checklist item) to a story.

    Args:
        story_id: The story public ID
        task_description: Task description text
        task_owner_ids: Optional list of owner user IDs
    """
    _write_guard()
    c = client()
    if not c.get_story(story_id):
        raise ValueError(f"Story {story_id} not found")
    params: dict[str, Any] = {"description": task_description}
    if task_owner_ids:
        params["owner_ids"] = task_owner_ids
    task = c.create_task(story_id, params)
    return f"Created task for story sc-{story_id}. Task ID: {task['id']}"


@mcp.tool()
def stories_update_task(
    story_id: int,
    task_id: int,
    task_description: str | None = None,
    task_owner_ids: list[str] | None = None,
    is_completed: bool | None = None,
) -> str:
    """Update a task in a story.

    Args:
        story_id: The story public ID
        task_id: The task ID
        task_description: New task description
        task_owner_ids: New owner user IDs
        is_completed: Mark as completed
    """
    _write_guard()
    c = client()
    params: dict[str, Any] = {}
    if task_description is not None:
        params["description"] = task_description
    if task_owner_ids is not None:
        params["owner_ids"] = task_owner_ids
    if is_completed is not None:
        params["complete"] = is_completed
    task = c.update_task(story_id, task_id, params)
    action = "Completed" if is_completed else "Updated"
    return f"{action} task for story sc-{story_id}. Task ID: {task['id']}"


@mcp.tool()
def stories_add_relation(
    story_id: int,
    related_story_id: int,
    relationship_type: str = "relates to",
) -> str:
    """Add a relationship between two stories.

    Args:
        story_id: The story public ID
        related_story_id: The related story public ID
        relationship_type: One of: "relates to", "blocks", "blocked by", "duplicates", "duplicated by"
    """
    _write_guard()
    c = client()
    if not c.get_story(story_id):
        raise ValueError(f"Story {story_id} not found")
    if not c.get_story(related_story_id):
        raise ValueError(f"Story {related_story_id} not found")

    subject_id, object_id = story_id, related_story_id
    verb = relationship_type
    if verb == "blocked by":
        verb = "blocks"
        subject_id, object_id = related_story_id, story_id
    elif verb == "duplicated by":
        verb = "duplicates"
        subject_id, object_id = related_story_id, story_id

    c.create_story_link({"subject_id": subject_id, "object_id": object_id, "verb": verb})
    return f"Added '{relationship_type}' relationship between sc-{story_id} and sc-{related_story_id}"


@mcp.tool()
def stories_add_external_link(story_id: int, url: str) -> str:
    """Add an external link to a story.

    Args:
        story_id: The story public ID
        url: The URL to add
    """
    _write_guard()
    c = client()
    story = c.get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    links = story.get("external_links", [])
    if url in links:
        return f"Link already exists on story sc-{story_id}"
    c.update_story(story_id, {"external_links": links + [url]})
    return f"Added external link to story sc-{story_id}"


@mcp.tool()
def stories_remove_external_link(story_id: int, url: str) -> str:
    """Remove an external link from a story.

    Args:
        story_id: The story public ID
        url: The URL to remove
    """
    _write_guard()
    c = client()
    story = c.get_story(story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    c.update_story(story_id, {"external_links": [l for l in story.get("external_links", []) if l != url]})
    return f"Removed external link from story sc-{story_id}"


@mcp.tool()
def stories_set_external_links(story_id: int, urls: list[str]) -> str:
    """Replace all external links on a story.

    Args:
        story_id: The story public ID
        urls: List of URLs (replaces all existing links)
    """
    _write_guard()
    c = client()
    if not c.get_story(story_id):
        raise ValueError(f"Story {story_id} not found")
    updated = c.update_story(story_id, {"external_links": urls})
    count = len(urls)
    msg = f"Removed all external links from" if count == 0 else f"Set {count} external link(s) on"
    return f"{msg} story sc-{story_id}. URL: {updated.get('app_url', '')}"


@mcp.tool()
def stories_get_by_external_link(url: str) -> str:
    """Find stories containing a specific external link.

    Args:
        url: The URL to search for
    """
    stories = client().get_stories_by_external_link(url)
    if not stories:
        return f"No stories found with external link: {url}"
    slim = [_slim_story(s) for s in stories]
    return f"Found {len(stories)} stories with external link:\n\n{_json(slim)}"


# ═══════════════════════════════════════════════════════════════
#  EPICS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def epics_get_by_id(epic_id: int, full: bool = False) -> str:
    """Get a Shortcut epic by its public ID.

    Args:
        epic_id: The epic public ID
        full: Return all fields instead of slim view
    """
    epic = client().get_epic(epic_id)
    if not epic:
        raise ValueError(f"Epic {epic_id} not found")
    data = epic if full else _slim_epic(epic)
    return f"Epic {epic_id}:\n\n{_json(data)}"


@mcp.tool()
def epics_search(
    name: str | None = None,
    description: str | None = None,
    state: str | None = None,
    objective: int | None = None,
    owner: str | None = None,
    team: str | None = None,
    is_done: bool | None = None,
    is_started: bool | None = None,
    is_archived: bool = False,
    is_overdue: bool | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for Shortcut epics.

    Args:
        name: Name contains
        description: Description contains
        state: Epic state (unstarted, started, done)
        objective: Objective ID
        owner: Owner mention name or "me"
        team: Team mention name
        is_done: Filter completed
        is_started: Filter started
        is_archived: Include archived (default false)
        is_overdue: Filter overdue
        next_page_token: Pagination token
    """
    params = {}
    for k, v in {"name": name, "description": description, "state": state,
                  "objective": objective, "owner": owner, "team": team,
                  "is_done": is_done, "is_started": is_started,
                  "is_archived": is_archived, "is_overdue": is_overdue}.items():
        if v is not None:
            params[k] = v

    current_user = client().get_current_user()
    query = _build_search_query(params, current_user)
    result = client().search_epics(query, next_token=next_page_token)

    epics = result.get("data", [])
    total = result.get("total", 0)
    token = _extract_next_token(result.get("next"))

    if not epics:
        return "No epics found."

    slim = [_slim_epic(e) for e in epics]
    msg = f"{len(epics)} shown of {total} total epics found:\n\n{_json(slim)}"
    if token:
        msg += f"\n\nNext page token: {token}"
    return msg


@mcp.tool()
def epics_create(
    name: str,
    description: str | None = None,
    owner: str | None = None,
    team_id: str | None = None,
) -> str:
    """Create a new Shortcut epic.

    Args:
        name: Epic name
        description: Epic description
        owner: Owner user ID
        team_id: Team ID
    """
    _write_guard()
    params: dict[str, Any] = {"name": name}
    if description:
        params["description"] = description
    if owner:
        params["owner_ids"] = [owner]
    if team_id:
        params["group_id"] = team_id
    epic = client().create_epic(params)
    return f"Epic created with ID: {epic['id']}. URL: {epic.get('app_url', '')}"


@mcp.tool()
def epics_update(
    epic_id: int,
    name: str | None = None,
    description: str | None = None,
    state: str | None = None,
    team_id: str | None = None,
    owner_ids: list[str] | None = None,
    deadline: str | None = None,
    archived: bool | None = None,
) -> str:
    """Update an epic. Only provide fields to change.

    Args:
        epic_id: Epic ID (required)
        name: Epic name
        description: Epic description
        state: State (to do, in progress, done)
        team_id: Team UUID
        owner_ids: Owner user UUIDs
        deadline: Due date ISO 8601 (empty string to unset)
        archived: Archive the epic
    """
    _write_guard()
    c = client()
    if not c.get_epic(epic_id):
        raise ValueError(f"Epic {epic_id} not found")

    params: dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if description is not None:
        params["description"] = description
    if state is not None:
        params["state"] = state
    if team_id is not None:
        params["group_id"] = team_id
    if owner_ids is not None:
        params["owner_ids"] = owner_ids
    if deadline is not None:
        params["deadline"] = None if deadline == "" else deadline
    if archived is not None:
        params["archived"] = archived

    updated = c.update_epic(epic_id, params)
    return f"Updated epic {epic_id}. URL: {updated.get('app_url', '')}"


@mcp.tool()
def epics_create_comment(epic_id: int, text: str, reply_to_comment_id: int | None = None) -> str:
    """Add a comment to an epic.

    Args:
        epic_id: The epic public ID
        text: Comment text
        reply_to_comment_id: Comment ID to reply to
    """
    _write_guard()
    c = client()
    if not c.get_epic(epic_id):
        raise ValueError(f"Epic {epic_id} not found")

    if reply_to_comment_id:
        comment = c.create_epic_comment_reply(epic_id, reply_to_comment_id, {"text": text})
    else:
        comment = c.create_epic_comment(epic_id, {"text": text})
    return f"Created comment on epic {epic_id}. Comment URL: {comment.get('app_url', '')}"


@mcp.tool()
def epics_delete(epic_id: int) -> str:
    """Delete an epic (cannot be undone).

    Args:
        epic_id: The epic public ID
    """
    _write_guard()
    c = client()
    if not c.get_epic(epic_id):
        raise ValueError(f"Epic {epic_id} not found")
    c.delete_epic(epic_id)
    return f"Deleted epic {epic_id}."


# ═══════════════════════════════════════════════════════════════
#  ITERATIONS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def iterations_get_by_id(iteration_id: int, full: bool = False) -> str:
    """Get a Shortcut iteration by public ID.

    Args:
        iteration_id: The iteration public ID
        full: Return all fields
    """
    iteration = client().get_iteration(iteration_id)
    if not iteration:
        raise ValueError(f"Iteration {iteration_id} not found")
    data = iteration if full else _slim_iteration(iteration)
    return f"Iteration {iteration_id}:\n\n{_json(data)}"


@mcp.tool()
def iterations_get_stories(iteration_id: int, include_descriptions: bool = False) -> str:
    """Get all stories in a specific iteration.

    Args:
        iteration_id: The iteration public ID
        include_descriptions: Include story descriptions (slower)
    """
    stories = client().list_iteration_stories(iteration_id, include_descriptions)
    if not stories:
        return f"No stories found in iteration {iteration_id}."
    slim = [_slim_story(s) for s in stories]
    return f"{len(stories)} stories in iteration {iteration_id}:\n\n{_json(slim)}"


@mcp.tool()
def iterations_search(
    name: str | None = None,
    description: str | None = None,
    state: str | None = None,
    team: str | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for Shortcut iterations.

    Args:
        name: Name contains
        description: Description contains
        state: State (started, unstarted, done)
        team: Team ID or mention name
        next_page_token: Pagination token
    """
    params = {}
    for k, v in {"name": name, "description": description, "state": state, "team": team}.items():
        if v is not None:
            params[k] = v

    current_user = client().get_current_user()
    query = _build_search_query(params, current_user)
    result = client().search_iterations(query, next_token=next_page_token)

    iterations = result.get("data", [])
    total = result.get("total", 0)
    token = _extract_next_token(result.get("next"))

    if not iterations:
        return "No iterations found."

    slim = [_slim_iteration(i) for i in iterations]
    msg = f"{len(iterations)} shown of {total} total iterations found:\n\n{_json(slim)}"
    if token:
        msg += f"\n\nNext page token: {token}"
    return msg


@mcp.tool()
def iterations_create(
    name: str,
    start_date: str,
    end_date: str,
    team_id: str | None = None,
    description: str | None = None,
) -> str:
    """Create a new Shortcut iteration.

    Args:
        name: Iteration name
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        team_id: Team ID
        description: Iteration description
    """
    _write_guard()
    params: dict[str, Any] = {"name": name, "start_date": start_date, "end_date": end_date}
    if team_id:
        params["group_ids"] = [team_id]
    if description:
        params["description"] = description
    iteration = client().create_iteration(params)
    return f"Iteration created with ID: {iteration['id']}."


@mcp.tool()
def iterations_update(
    iteration_id: int,
    name: str | None = None,
    description: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    team_ids: list[str] | None = None,
) -> str:
    """Update an iteration. Only provide fields to change.

    Args:
        iteration_id: Iteration ID (required)
        name: Iteration name
        description: Iteration description
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        team_ids: Team UUIDs
    """
    _write_guard()
    c = client()
    if not c.get_iteration(iteration_id):
        raise ValueError(f"Iteration {iteration_id} not found")

    params: dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if description is not None:
        params["description"] = description
    if start_date is not None:
        params["start_date"] = start_date
    if end_date is not None:
        params["end_date"] = end_date
    if team_ids is not None:
        params["group_ids"] = team_ids

    updated = c.update_iteration(iteration_id, params)
    return f"Updated iteration {iteration_id}. URL: {updated.get('app_url', '')}"


@mcp.tool()
def iterations_delete(iteration_id: int) -> str:
    """Delete an iteration (cannot be undone).

    Args:
        iteration_id: The iteration public ID
    """
    _write_guard()
    c = client()
    if not c.get_iteration(iteration_id):
        raise ValueError(f"Iteration {iteration_id} not found")
    c.delete_iteration(iteration_id)
    return f"Deleted iteration {iteration_id}."


@mcp.tool()
def iterations_get_active(team_id: str | None = None) -> str:
    """Get active iterations for the current user's teams.

    Args:
        team_id: Optional team ID to filter by
    """
    c = client()
    user = c.get_current_user()
    teams = c.list_teams()
    today = datetime.now().strftime("%Y-%m-%d")

    if team_id:
        team_ids = [team_id]
    else:
        team_ids = [t["id"] for t in teams if user["id"] in t.get("member_ids", [])]

    if not team_ids:
        return "Current user does not belong to any teams."

    all_iterations = c.list_iterations()
    active = []
    for it in all_iterations:
        if it.get("status") != "started":
            continue
        start = it.get("start_date", "")[:10]
        end = it.get("end_date", "")[:10]
        if start > today or end < today:
            continue
        it_teams = it.get("group_ids", [])
        if not it_teams or any(tid in team_ids for tid in it_teams):
            active.append(it)

    if not active:
        return "No active iterations found."
    slim = [_slim_iteration(i) for i in active]
    return f"{len(active)} active iterations:\n\n{_json(slim)}"


@mcp.tool()
def iterations_get_upcoming(team_id: str | None = None) -> str:
    """Get upcoming iterations for the current user's teams.

    Args:
        team_id: Optional team ID to filter by
    """
    c = client()
    user = c.get_current_user()
    teams = c.list_teams()
    today = datetime.now().strftime("%Y-%m-%d")

    if team_id:
        team_ids = [team_id]
    else:
        team_ids = [t["id"] for t in teams if user["id"] in t.get("member_ids", [])]

    if not team_ids:
        return "Current user does not belong to any teams."

    all_iterations = c.list_iterations()
    upcoming = []
    for it in all_iterations:
        if it.get("status") != "unstarted":
            continue
        start = it.get("start_date", "")[:10]
        if start < today:
            continue
        it_teams = it.get("group_ids", [])
        if not it_teams or any(tid in team_ids for tid in it_teams):
            upcoming.append(it)

    if not upcoming:
        return "No upcoming iterations found."
    slim = [_slim_iteration(i) for i in upcoming]
    return f"{len(upcoming)} upcoming iterations:\n\n{_json(slim)}"


# ═══════════════════════════════════════════════════════════════
#  OBJECTIVES (Milestones)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def objectives_get_by_id(objective_id: int, full: bool = False) -> str:
    """Get a Shortcut objective by public ID.

    Args:
        objective_id: The objective public ID
        full: Return all fields
    """
    objective = client().get_milestone(objective_id)
    if not objective:
        raise ValueError(f"Objective {objective_id} not found")
    if not full:
        objective = {
            "id": objective.get("id"),
            "name": objective.get("name"),
            "app_url": objective.get("app_url"),
            "archived": objective.get("archived"),
            "state": objective.get("state"),
            "categories": [c.get("name") for c in objective.get("categories", [])],
        }
    return f"Objective {objective_id}:\n\n{_json(objective)}"


@mcp.tool()
def objectives_search(
    name: str | None = None,
    description: str | None = None,
    state: str | None = None,
    owner: str | None = None,
    team: str | None = None,
    is_done: bool | None = None,
    is_started: bool | None = None,
    is_archived: bool | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for Shortcut objectives.

    Args:
        name: Name contains
        description: Description contains
        state: State (unstarted, started, done)
        owner: Owner mention name or "me"
        team: Team mention name
        is_done: Filter completed
        is_started: Filter started
        is_archived: Include archived
        next_page_token: Pagination token
    """
    params = {}
    for k, v in {"name": name, "description": description, "state": state,
                  "owner": owner, "team": team, "is_done": is_done,
                  "is_started": is_started, "is_archived": is_archived}.items():
        if v is not None:
            params[k] = v

    current_user = client().get_current_user()
    query = _build_search_query(params, current_user)
    result = client().search_milestones(query, next_token=next_page_token)

    milestones = result.get("data", [])
    total = result.get("total", 0)
    token = _extract_next_token(result.get("next"))

    if not milestones:
        return "No objectives found."

    msg = f"{len(milestones)} shown of {total} total objectives found:\n\n{_json(milestones)}"
    if token:
        msg += f"\n\nNext page token: {token}"
    return msg


# ═══════════════════════════════════════════════════════════════
#  TEAMS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def teams_get_by_id(team_id: str, full: bool = False) -> str:
    """Get a Shortcut team by ID.

    Args:
        team_id: The team public ID
        full: Return all fields
    """
    team = client().get_team(team_id)
    if not team:
        raise ValueError(f"Team {team_id} not found")
    return f"Team {team_id}:\n\n{_json(team)}"


@mcp.tool()
def teams_list(include_archived: bool = False) -> str:
    """List all Shortcut teams.

    Args:
        include_archived: Include archived teams
    """
    teams = client().list_teams()
    if not include_archived:
        teams = [t for t in teams if not t.get("archived")]
    if not teams:
        return "No teams found."
    return f"{len(teams)} teams found:\n\n{_json(teams)}"


# ═══════════════════════════════════════════════════════════════
#  WORKFLOWS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def workflows_get_default(team_id: str | None = None) -> str:
    """Get the default workflow for a team or workspace.

    Args:
        team_id: Team ID (omit for workspace default)
    """
    c = client()
    if team_id:
        team = c.get_team(team_id)
        if team and team.get("default_workflow_id"):
            wf = c.get_workflow(team["default_workflow_id"])
            if wf:
                return f"Default workflow for team (ID {wf['id']}):\n\n{_json(wf)}"

    user = c.get_current_user()
    default_wf_id = user.get("workspace2", {}).get("default_workflow_id")
    if default_wf_id:
        wf = c.get_workflow(default_wf_id)
        if wf:
            return f"Default workflow (ID {wf['id']}):\n\n{_json(wf)}"
    return "No default workflow found."


@mcp.tool()
def workflows_get_by_id(workflow_id: int) -> str:
    """Get a Shortcut workflow by ID.

    Args:
        workflow_id: The workflow public ID
    """
    wf = client().get_workflow(workflow_id)
    if not wf:
        raise ValueError(f"Workflow {workflow_id} not found")
    return f"Workflow {workflow_id}:\n\n{_json(wf)}"


@mcp.tool()
def workflows_list() -> str:
    """List all Shortcut workflows."""
    workflows = client().list_workflows()
    if not workflows:
        return "No workflows found."
    return f"{len(workflows)} workflows found:\n\n{_json(workflows)}"


# ═══════════════════════════════════════════════════════════════
#  DOCUMENTS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def documents_create(title: str, content: str) -> str:
    """Create a new document in Markdown format.

    Args:
        title: Document title
        content: Content in Markdown
    """
    _write_guard()
    doc = client().create_doc({"title": title, "content": content, "content_format": "markdown"})
    return f"Document created. ID: {doc['id']}, URL: {doc.get('app_url', '')}"


@mcp.tool()
def documents_update(doc_id: str, title: str | None = None, content: str | None = None) -> str:
    """Update a document's title or content.

    Args:
        doc_id: Document ID
        title: New title
        content: New content in Markdown
    """
    _write_guard()
    c = client()
    doc = c.get_doc(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    params: dict[str, Any] = {"content_format": "markdown"}
    params["title"] = title if title is not None else doc.get("title", "")
    params["content"] = content if content is not None else doc.get("content_markdown", "")
    updated = c.update_doc(doc_id, params)
    return f"Document updated. ID: {updated['id']}, URL: {updated.get('app_url', '')}"


@mcp.tool()
def documents_list() -> str:
    """List all documents in Shortcut."""
    docs = client().list_docs()
    if not docs:
        return "No documents found."
    return f"{len(docs)} documents found:\n\n{_json(docs)}"


@mcp.tool()
def documents_search(
    title: str,
    archived: bool | None = None,
    created_by_me: bool | None = None,
    followed_by_me: bool | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for documents.

    Args:
        title: Title contains
        archived: Filter by archived status
        created_by_me: Only documents created by me
        followed_by_me: Only documents I follow
        next_page_token: Pagination token
    """
    params: dict[str, Any] = {"title": title, "page_size": 25}
    if archived is not None:
        params["archived"] = archived
    if created_by_me is not None:
        params["created_by_me"] = created_by_me
    if followed_by_me is not None:
        params["followed_by_me"] = followed_by_me
    if next_page_token:
        params["next"] = next_page_token

    result = client().search_docs(params)
    docs = result.get("data", [])
    total = result.get("total", 0)
    token = _extract_next_token(result.get("next"))

    if not docs:
        return "No documents found."

    msg = f"{len(docs)} shown of {total} total documents found:\n\n{_json(docs)}"
    if token:
        msg += f"\n\nNext page token: {token}"
    return msg


@mcp.tool()
def documents_get_by_id(doc_id: str) -> str:
    """Get a document by ID (returns Markdown content).

    Args:
        doc_id: Document ID
    """
    doc = client().get_doc(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    return f"Document {doc_id}:\n\n{_json(doc)}"


# ═══════════════════════════════════════════════════════════════
#  LABELS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def labels_list(include_archived: bool = False) -> str:
    """List all labels in the workspace.

    Args:
        include_archived: Include archived labels
    """
    labels = client().list_labels()
    if not include_archived:
        labels = [l for l in labels if not l.get("archived")]
    if not labels:
        return "No labels found."
    slim = [{"id": l["id"], "name": l["name"], "app_url": l.get("app_url")} for l in labels]
    return f"{len(labels)} labels found:\n\n{_json(slim)}"


@mcp.tool()
def labels_get_stories(label_id: int) -> str:
    """Get all stories with a specific label.

    Args:
        label_id: The label public ID
    """
    stories = client().list_label_stories(label_id)
    if not stories:
        return f"No stories found for label {label_id}."
    slim = [_slim_story(s) for s in stories]
    return f"{len(stories)} stories with label {label_id}:\n\n{_json(slim)}"


@mcp.tool()
def labels_create(name: str, color: str | None = None, description: str | None = None) -> str:
    """Create a new label.

    Args:
        name: Label name
        color: Hex color (e.g. #ff0000)
        description: Label description
    """
    _write_guard()
    params: dict[str, Any] = {"name": name}
    if color:
        params["color"] = color
    if description:
        params["description"] = description
    label = client().create_label(params)
    return f"Label created with ID: {label['id']}."


# ═══════════════════════════════════════════════════════════════
#  PROJECTS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def projects_list(include_archived: bool = False) -> str:
    """List all projects in the workspace.

    Args:
        include_archived: Include archived projects
    """
    projects = client().list_projects()
    if not include_archived:
        projects = [p for p in projects if not p.get("archived")]
    if not projects:
        return "No projects found."
    slim = [{"id": p["id"], "name": p["name"], "app_url": p.get("app_url")} for p in projects]
    return f"{len(projects)} projects found:\n\n{_json(slim)}"


@mcp.tool()
def projects_get_by_id(project_id: int) -> str:
    """Get a Shortcut project by ID.

    Args:
        project_id: The project public ID
    """
    project = client().get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")
    return f"Project {project_id}:\n\n{_json(project)}"


@mcp.tool()
def projects_get_stories(project_id: int) -> str:
    """Get all stories in a project.

    Args:
        project_id: The project public ID
    """
    c = client()
    if not c.get_project(project_id):
        raise ValueError(f"Project {project_id} not found")
    stories = c.list_project_stories(project_id)
    if not stories:
        return f"No stories found in project {project_id}."
    slim = [_slim_story(s) for s in stories]
    return f"{len(stories)} stories in project {project_id}:\n\n{_json(slim)}"


# ═══════════════════════════════════════════════════════════════
#  CUSTOM FIELDS
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
def custom_fields_list(include_disabled: bool = False) -> str:
    """List custom fields and their possible values.

    Args:
        include_disabled: Include disabled fields
    """
    fields = client().list_custom_fields()
    if not include_disabled:
        fields = [f for f in fields if f.get("enabled")]
    if not fields:
        return "No custom fields found."
    slim = []
    for f in fields:
        values = f.get("values", [])
        if not include_disabled:
            values = [v for v in values if v.get("enabled")]
        slim.append({
            "id": f["id"],
            "name": f["name"],
            "field_type": f.get("field_type"),
            "values": [{"id": v["id"], "value": v["value"]} for v in values],
        })
    return f"{len(fields)} custom fields found:\n\n{_json(slim)}"


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    mcp.run()


if __name__ == "__main__":
    main()
