# Shortcut MCP Server (FastMCP)

MCP server for [Shortcut](https://shortcut.com) project management, built with [FastMCP](https://github.com/jlowin/fastmcp).

Manage stories, epics, iterations, objectives, documents, labels, teams, workflows, and more - directly from Claude.

## Setup

### 1. Get a Shortcut API Token

Go to [Shortcut API Tokens](https://app.shortcut.com/settings/account/api-tokens) and generate a token.

### 2. Install

```bash
cd mcp-server-shortcut-fastmcp
uv sync
```

### 3. Connect to Claude

#### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "shortcut": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-server-shortcut-fastmcp", "run", "server.py"],
      "env": {
        "SHORTCUT_API_TOKEN": "your-token-here"
      }
    }
  }
}
```

#### Claude Code (CLI)

Add to your `.claude.json` or run:

```bash
claude mcp add shortcut -- uv --directory /path/to/mcp-server-shortcut-fastmcp run server.py
```

Set the env var:
```bash
export SHORTCUT_API_TOKEN=your-token-here
```

#### Claude Web (Remote via SSE)

Run the server with SSE transport:

```bash
SHORTCUT_API_TOKEN=your-token-here fastmcp run server.py --transport sse --port 8000
```

Then add `http://localhost:8000/sse` as a remote MCP server in Claude settings.

### 4. Deploy Remotely (optional)

For remote deployment accessible from Claude Web:

```bash
# Install FastMCP CLI
pip install fastmcp

# Deploy (e.g. to a cloud server)
SHORTCUT_API_TOKEN=your-token-here fastmcp run server.py --transport sse --host 0.0.0.0 --port 8000
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SHORTCUT_API_TOKEN` | Yes | Your Shortcut API token |
| `SHORTCUT_READONLY` | No | Set to `true` to disable write operations |

## Available Tools

### Users
- `users_get_current` - Get current user
- `users_get_current_teams` - Get current user's teams
- `users_list` - List all workspace members

### Stories
- `stories_get_by_id` - Get story by ID
- `stories_get_history` - Get story change history
- `stories_search` - Search stories with filters
- `stories_get_branch_name` - Get git branch name for story
- `stories_create` - Create a new story
- `stories_update` - Update a story
- `stories_assign_current_user` - Assign yourself to a story
- `stories_unassign_current_user` - Remove yourself from a story
- `stories_create_comment` - Comment on a story
- `stories_create_subtask` - Create a sub-task
- `stories_add_subtask` - Add existing story as sub-task
- `stories_remove_subtask` - Remove sub-task from parent
- `stories_add_task` - Add checklist task
- `stories_update_task` - Update a checklist task
- `stories_add_relation` - Add story relationship
- `stories_add_external_link` - Add external link
- `stories_remove_external_link` - Remove external link
- `stories_set_external_links` - Replace all external links
- `stories_get_by_external_link` - Find stories by external link

### Epics
- `epics_get_by_id` - Get epic by ID
- `epics_search` - Search epics
- `epics_create` - Create epic
- `epics_update` - Update epic
- `epics_create_comment` - Comment on epic
- `epics_delete` - Delete epic

### Iterations
- `iterations_get_by_id` - Get iteration by ID
- `iterations_get_stories` - Get stories in iteration
- `iterations_search` - Search iterations
- `iterations_create` - Create iteration
- `iterations_update` - Update iteration
- `iterations_delete` - Delete iteration
- `iterations_get_active` - Get active iterations
- `iterations_get_upcoming` - Get upcoming iterations

### Objectives
- `objectives_get_by_id` - Get objective by ID
- `objectives_search` - Search objectives

### Teams
- `teams_get_by_id` - Get team by ID
- `teams_list` - List all teams

### Workflows
- `workflows_get_default` - Get default workflow
- `workflows_get_by_id` - Get workflow by ID
- `workflows_list` - List all workflows

### Documents
- `documents_create` - Create document
- `documents_update` - Update document
- `documents_list` - List documents
- `documents_search` - Search documents
- `documents_get_by_id` - Get document by ID

### Labels
- `labels_list` - List labels
- `labels_get_stories` - Get stories by label
- `labels_create` - Create label

### Projects
- `projects_list` - List projects
- `projects_get_by_id` - Get project by ID
- `projects_get_stories` - Get project stories

### Custom Fields
- `custom_fields_list` - List custom fields and values

## License

MIT
