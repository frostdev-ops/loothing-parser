# Guild Setup Guide

The WoW Combat Log Analysis API uses a multi-tenant architecture where all data is organized by guild. This guide will help you set up your guild and understand how guild context works throughout the API.

## Overview

Every API request operates within a guild context. This ensures that:

- **Data Isolation**: Your guild's data is completely separate from other guilds
- **Performance**: Queries are optimized with guild-specific indexing
- **Security**: You can only access data for your assigned guild
- **Management**: Clear organization for multi-guild environments

## Getting Started

### 1. Register Your Guild

Before you can use the API, your guild must be registered in the system. Contact your system administrator or use the guild registration endpoint (if you have admin access):

```python
import requests

# Register a new guild (admin required)
response = requests.post(
    "https://api.example.com/api/v1/admin/guilds",
    headers={"Authorization": "Bearer ADMIN_API_KEY"},
    json={
        "guild_name": "Mythic Raiders",
        "server": "Stormrage",
        "region": "US",
        "faction": "Alliance"
    }
)

guild = response.json()
print(f"Guild registered with ID: {guild['guild_id']}")
```

### 2. Get Your API Key

Once your guild is registered, you'll receive an API key that's associated with your guild. This key automatically provides guild context for all your requests.

```bash
# Your API key contains your guild context
API_KEY="guild_123_key_abc123def456"
```

### 3. Verify Guild Access

Test your guild access with a simple API call:

```python
import requests

headers = {"Authorization": f"Bearer {API_KEY}"}

# This will return data for your guild only
response = requests.get(
    "https://api.example.com/api/v1/encounters",
    headers=headers,
    params={"limit": 5}
)

encounters = response.json()
print(f"Found {len(encounters['data'])} encounters for your guild")
```

## Understanding Guild Context

### Automatic Context

When you make API requests with your guild-associated API key, the guild context is automatically applied:

```python
# These requests automatically use your guild context
characters = api.get("/api/v1/characters")
encounters = api.get("/api/v1/encounters")
analytics = api.get("/api/v1/analytics/performance")
```

### Explicit Guild Parameters

Some administrative endpoints allow you to specify guild_id explicitly (if you have multi-guild access):

```python
# Only for users with multi-guild access
response = requests.get(
    "https://api.example.com/api/v1/encounters",
    headers=headers,
    params={
        "guild_id": 123,  # Explicit guild specification
        "limit": 10
    }
)
```

### Guild Information

You can retrieve information about your guild:

```python
# Get your guild details
response = requests.get(
    "https://api.example.com/api/v1/guilds/current",
    headers=headers
)

guild_info = response.json()
print(f"Guild: {guild_info['guild_name']} - {guild_info['server']}")
print(f"Region: {guild_info['region']} | Faction: {guild_info['faction']}")
```

## Data Upload

When uploading combat logs, they're automatically associated with your guild:

```python
# Upload a combat log
with open("WoWCombatLog.txt", "rb") as log_file:
    response = requests.post(
        "https://api.example.com/api/v1/logs/upload",
        headers=headers,
        files={"log_file": log_file},
        data={
            "encounter_name": "Ulgrax the Devourer",
            "difficulty": "Heroic"
        }
    )

upload_result = response.json()
print(f"Log uploaded for guild {upload_result['guild_id']}")
```

## WebSocket Streaming

Real-time streaming also respects guild context:

```javascript
const ws = new WebSocket("wss://api.example.com/api/v1/stream", {
  headers: {
    Authorization: "Bearer YOUR_API_KEY",
  },
});

// You'll only receive updates for your guild
ws.on("encounter_update", (data) => {
  console.log(`Guild ${data.guild_id} encounter update:`, data);
});
```

## Multi-Guild Access

Some users may have access to multiple guilds (administrators, analysts):

### Listing Accessible Guilds

```python
# Get all guilds you have access to
response = requests.get(
    "https://api.example.com/api/v1/guilds",
    headers=headers
)

guilds = response.json()
for guild in guilds['data']:
    print(f"Guild: {guild['guild_name']} (ID: {guild['guild_id']})")
```

### Switching Guild Context

For multi-guild users, you can specify which guild to query:

```python
# Query specific guild (if you have access)
response = requests.get(
    "https://api.example.com/api/v1/encounters",
    headers=headers,
    params={
        "guild_id": 456,  # Different guild
        "limit": 10
    }
)
```

## Common Patterns

### Guild Analytics Dashboard

```python
import requests

class GuildAnalytics:
    def __init__(self, api_key):
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.base_url = "https://api.example.com/api/v1"

    def get_guild_summary(self):
        """Get overall guild performance summary."""
        response = requests.get(
            f"{self.base_url}/analytics/guild/summary",
            headers=self.headers
        )
        return response.json()

    def get_recent_encounters(self, days=7):
        """Get recent encounters for the guild."""
        response = requests.get(
            f"{self.base_url}/encounters",
            headers=self.headers,
            params={"days": days, "limit": 20}
        )
        return response.json()

    def get_top_performers(self, metric="dps"):
        """Get top performing characters in the guild."""
        response = requests.get(
            f"{self.base_url}/characters/rankings",
            headers=self.headers,
            params={"metric": metric, "limit": 10}
        )
        return response.json()

# Usage
analytics = GuildAnalytics("your_api_key_here")
summary = analytics.get_guild_summary()
print(f"Guild has {summary['total_encounters']} encounters")
```

### Character Progression Tracking

```python
def track_character_progression(character_name, days=30):
    """Track a character's progression over time."""
    response = requests.get(
        f"https://api.example.com/api/v1/characters/{character_name}/progression",
        headers=headers,
        params={"days": days}
    )

    progression = response.json()

    print(f"Character: {character_name}")
    print(f"Item Level Progress: {progression['item_level_change']}")
    print(f"Performance Trend: {progression['performance_trend']}")
    print(f"Recent Achievements: {len(progression['achievements'])}")

    return progression

# Track progression for guild member
progression = track_character_progression("Thrall")
```

## Best Practices

### 1. API Key Security

- Never expose your API key in client-side code
- Use environment variables to store API keys
- Regularly rotate API keys for security

```python
import os

# Store API key securely
API_KEY = os.getenv("WOW_API_KEY")
headers = {"Authorization": f"Bearer {API_KEY}"}
```

### 2. Error Handling

Always handle guild-related errors gracefully:

```python
def safe_api_call(url, headers, params=None):
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        if response.status_code == 403:
            print("Guild access denied - check your API key")
        elif response.status_code == 400:
            error_detail = response.json().get('detail', 'Unknown error')
            if 'guild' in error_detail.lower():
                print(f"Guild-related error: {error_detail}")
        raise

    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        raise
```

### 3. Caching Guild Context

Cache guild information to reduce API calls:

```python
class GuildAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self._guild_info = None

    @property
    def guild_info(self):
        if self._guild_info is None:
            response = requests.get(
                "https://api.example.com/api/v1/guilds/current",
                headers=self.headers
            )
            self._guild_info = response.json()
        return self._guild_info

    @property
    def guild_id(self):
        return self.guild_info['guild_id']

    @property
    def guild_name(self):
        return self.guild_info['guild_name']
```

## Troubleshooting

### Common Issues

**Issue**: "Guild ID is required" error

```
HTTP 400: Guild ID is required. Please ensure your API key is associated with a guild.
```

**Solution**: Your API key is not properly associated with a guild. Contact your administrator to assign your key to a guild.

**Issue**: "Access denied" when accessing encounters

```
HTTP 403: Access denied for guild data
```

**Solution**: Your API key doesn't have permission to access the requested guild's data. Verify you're using the correct API key.

**Issue**: Empty results for known data

```json
{
  "data": [],
  "total": 0,
  "guild_id": null
}
```

**Solution**: This usually indicates a guild context problem. Check that your API key is properly configured.

### Debugging Guild Context

Use this debug endpoint to verify your guild context:

```python
# Debug your current guild context
response = requests.get(
    "https://api.example.com/api/v1/debug/context",
    headers=headers
)

debug_info = response.json()
print(f"Guild ID: {debug_info.get('guild_id')}")
print(f"Guild Name: {debug_info.get('guild_name')}")
print(f"API Key Valid: {debug_info.get('api_key_valid')}")
print(f"Permissions: {debug_info.get('permissions')}")
```

## Next Steps

- [Authentication Guide](authentication.md) - Detailed authentication information
- [API Reference](../api-reference/guilds.md) - Complete guild API documentation
- [Examples](../examples/basic-usage.md) - Guild-specific examples and use cases
- [Best Practices](../guides/best-practices.md) - Advanced guild management practices
