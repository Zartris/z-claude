# z-claude

A Claude Code plugin marketplace by Zartris.

## Installation

### 1. Add the marketplace

Inside Claude Code, run:

```
/plugin marketplace add zartris/z-claude
```

### 2. Browse available plugins

```
/plugin search @z-claude
```

### 3. Install a plugin

```
/plugin install <plugin-name>@z-claude
```

### 4. Reload

```
/reload-plugins
```

## Team auto-install

To share plugins across your team, add this to your project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "z-claude": {
      "source": { "source": "github", "repo": "zartris/z-claude" }
    }
  },
  "enabledPlugins": {
    "<plugin-name>@z-claude": true
  }
}
```

## Authoring a plugin

### Plugin directory structure

Each plugin lives in its own directory under `plugins/`:

```
plugins/
  my-plugin/
    .claude-plugin/
      plugin.json         # Plugin manifest
    skills/
      my-skill/
        SKILL.md           # Skill definition
    agents/
      my-agent.md          # Agent definition (optional)
    commands/
      my-command.md        # Slash command (optional)
```

### plugin.json

The `plugin.json` inside `.claude-plugin/` describes the plugin:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "What this plugin does",
  "author": { "name": "Your Name" },
  "license": "MIT",
  "skills": "./skills",
  "agents": ["./agents/my-agent.md"]
}
```

### SKILL.md

A skill file defines a reusable capability. It lives at `skills/<skill-name>/SKILL.md` and contains the prompt and instructions for the skill.

### Registering your plugin in the marketplace

Add an entry to `.claude-plugin/marketplace.json` in the `plugins` array:

```json
{
  "name": "my-plugin",
  "description": "What this plugin does",
  "version": "1.0.0",
  "author": { "name": "Your Name" },
  "source": "./plugins/my-plugin",
  "category": "developer-tools",
  "tags": ["your", "tags"],
  "keywords": ["your", "keywords"]
}
```

#### Source types

Plugins can be sourced from multiple locations:

| Type | Example |
|------|---------|
| Local path | `"./plugins/my-plugin"` |
| GitHub repo | `{ "source": "github", "repo": "owner/repo" }` |
| Git URL | `{ "source": "url", "url": "https://gitlab.com/team/plugin.git" }` |
| Git subdirectory | `{ "source": "git-subdir", "url": "...", "path": "subdir" }` |
| npm | `{ "source": "npm", "package": "@scope/plugin" }` |

#### Categories

Use a descriptive category string. Common examples:

- `code-intelligence` -- LSP-based plugins
- `external-integrations` -- MCP server connections
- `developer-tools` -- Development workflow tools
- `workflow` -- Automation and process plugins
- `examples` -- Example and tutorial plugins

### Validating

Run validation before committing:

```
claude plugin validate .
```

Or from within Claude Code:

```
/plugin validate .
```

## License

MIT
