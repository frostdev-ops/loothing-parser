# Guild Management API

The Guild Management API provides endpoints for managing guild information, accessing guild-specific data, and performing guild administration tasks.

## Overview

All API endpoints automatically operate within your guild's context when using a guild-associated API key. This ensures data isolation and security across multiple guilds.

### Base URL

```
https://api.example.com/api/v1
```

### Authentication

All guild endpoints require authentication with a valid API key that's associated with a guild.

```bash
Authorization: Bearer YOUR_GUILD_API_KEY
```

## Endpoints

### Get Current Guild Information

Retrieve information about the guild associated with your API key.

```http
GET /guilds/current
```

**Response:**

```json
{
  "guild_id": 123,
  "guild_name": "Mythic Raiders",
  "server": "Stormrage",
  "region": "US",
  "faction": "Alliance",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-09-20T14:22:00Z",
  "is_active": true,
  "member_count": 25,
  "total_encounters": 1247,
  "total_characters": 67
}
```

**Example:**

```python
import requests

headers = {"Authorization": "Bearer YOUR_API_KEY"}
response = requests.get("https://api.example.com/api/v1/guilds/current", headers=headers)
guild = response.json()

print(f"Guild: {guild['guild_name']} on {guild['server']}")
print(f"Members: {guild['member_count']}")
```

### List Accessible Guilds

Get all guilds you have access to (for multi-guild users).

```http
GET /guilds
```

**Query Parameters:**

| Parameter | Type    | Default | Description                         |
| --------- | ------- | ------- | ----------------------------------- |
| `page`    | integer | 1       | Page number for pagination          |
| `limit`   | integer | 20      | Number of guilds per page (max 100) |
| `region`  | string  | -       | Filter by region (US, EU, etc.)     |
| `faction` | string  | -       | Filter by faction (Alliance, Horde) |

**Response:**

```json
{
  "data": [
    {
      "guild_id": 123,
      "guild_name": "Mythic Raiders",
      "server": "Stormrage",
      "region": "US",
      "faction": "Alliance",
      "member_count": 25,
      "last_activity": "2024-09-20T20:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 1,
    "has_next": false
  }
}
```

### Get Guild Statistics

Retrieve comprehensive statistics for your guild.

```http
GET /guilds/current/statistics
```

**Query Parameters:**

| Parameter        | Type    | Default | Description                                        |
| ---------------- | ------- | ------- | -------------------------------------------------- |
| `days`           | integer | 30      | Number of days to include in statistics            |
| `encounter_type` | string  | "all"   | Filter by encounter type (raid, dungeon, all)      |
| `difficulty`     | string  | "all"   | Filter by difficulty (Normal, Heroic, Mythic, all) |

**Response:**

```json
{
  "guild_id": 123,
  "period": {
    "start_date": "2024-08-21T00:00:00Z",
    "end_date": "2024-09-20T23:59:59Z",
    "days": 30
  },
  "encounters": {
    "total": 156,
    "successful": 142,
    "success_rate": 91.0,
    "by_difficulty": {
      "Normal": { "total": 45, "successful": 45 },
      "Heroic": { "total": 89, "successful": 82 },
      "Mythic": { "total": 22, "successful": 15 }
    }
  },
  "characters": {
    "total_unique": 28,
    "active_last_week": 23,
    "by_class": {
      "Warrior": 4,
      "Mage": 3,
      "Hunter": 5
    }
  },
  "performance": {
    "avg_encounter_duration": 285,
    "avg_wipe_count": 1.2,
    "total_combat_time": 42570
  }
}
```

### Get Guild Members

List all characters that have participated in guild encounters.

```http
GET /guilds/current/members
```

**Query Parameters:**

| Parameter     | Type    | Default | Description                                       |
| ------------- | ------- | ------- | ------------------------------------------------- |
| `page`        | integer | 1       | Page number for pagination                        |
| `limit`       | integer | 50      | Number of members per page (max 100)              |
| `class`       | string  | -       | Filter by character class                         |
| `active_days` | integer | 30      | Only include members active in last N days        |
| `sort`        | string  | "name"  | Sort by: name, last_seen, encounters, performance |
| `order`       | string  | "asc"   | Sort order: asc, desc                             |

**Response:**

```json
{
  "data": [
    {
      "character_name": "Thrall",
      "character_class": "Warrior",
      "specialization": "Protection",
      "level": 80,
      "realm": "Stormrage",
      "last_seen": "2024-09-20T20:30:00Z",
      "total_encounters": 45,
      "avg_item_level": 628,
      "performance_summary": {
        "avg_dps": 425000,
        "avg_hps": 125000,
        "avg_dtps": 85000
      }
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 28,
    "has_next": false
  }
}
```

### Get Guild Encounters

Retrieve encounter history for your guild.

```http
GET /encounters
```

!!! note "Guild Context"
This endpoint automatically filters encounters to your guild. The guild_id parameter is optional and only works if you have multi-guild access.

**Query Parameters:**

| Parameter        | Type    | Default      | Description                                |
| ---------------- | ------- | ------------ | ------------------------------------------ |
| `guild_id`       | integer | -            | Specific guild ID (multi-guild users only) |
| `page`           | integer | 1            | Page number for pagination                 |
| `limit`          | integer | 20           | Number of encounters per page (max 100)    |
| `days`           | integer | -            | Filter to encounters in last N days        |
| `encounter_name` | string  | -            | Filter by encounter name                   |
| `difficulty`     | string  | -            | Filter by difficulty                       |
| `success`        | boolean | -            | Filter by success status                   |
| `sort`           | string  | "start_time" | Sort by: start_time, duration, success     |
| `order`          | string  | "desc"       | Sort order: asc, desc                      |

**Response:**

```json
{
  "data": [
    {
      "encounter_id": 12345,
      "guild_id": 123,
      "instance_name": "The War Within",
      "encounter_name": "Ulgrax the Devourer",
      "difficulty": "Heroic",
      "start_time": "2024-09-20T20:00:00Z",
      "end_time": "2024-09-20T20:05:30Z",
      "duration_seconds": 330,
      "success": true,
      "wipe_count": 2,
      "character_count": 20
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 156,
    "has_next": true
  }
}
```

### Get Guild Characters

Retrieve character information for your guild.

```http
GET /characters
```

**Query Parameters:**

| Parameter        | Type    | Default | Description                                   |
| ---------------- | ------- | ------- | --------------------------------------------- |
| `guild_id`       | integer | -       | Specific guild ID (multi-guild users only)    |
| `page`           | integer | 1       | Page number for pagination                    |
| `limit`          | integer | 50      | Number of characters per page (max 100)       |
| `class`          | string  | -       | Filter by character class                     |
| `encounter_id`   | integer | -       | Filter to characters in specific encounter    |
| `min_item_level` | integer | -       | Minimum item level filter                     |
| `active_days`    | integer | 30      | Only include characters active in last N days |

### Guild Analytics

#### Performance Trends

Get performance trends for your guild over time.

```http
GET /analytics/guild/trends
```

**Query Parameters:**

| Parameter        | Type    | Default | Description                                     |
| ---------------- | ------- | ------- | ----------------------------------------------- |
| `metric`         | string  | "dps"   | Metric to analyze (dps, hps, encounter_success) |
| `period`         | string  | "daily" | Aggregation period (daily, weekly, monthly)     |
| `days`           | integer | 30      | Number of days to analyze                       |
| `encounter_type` | string  | "all"   | Filter by encounter type                        |

**Response:**

```json
{
  "guild_id": 123,
  "metric": "dps",
  "period": "daily",
  "data_points": [
    {
      "date": "2024-09-20",
      "avg_value": 425000,
      "median_value": 410000,
      "encounters": 8,
      "characters": 20
    }
  ],
  "summary": {
    "trend_direction": "increasing",
    "trend_strength": 0.85,
    "improvement_percentage": 12.5
  }
}
```

#### Class Balance Analysis

Analyze class representation and performance in your guild.

```http
GET /analytics/guild/class-balance
```

**Response:**

```json
{
  "guild_id": 123,
  "analysis_period": "30_days",
  "class_distribution": {
    "Warrior": { "count": 4, "percentage": 14.3 },
    "Mage": { "count": 3, "percentage": 10.7 },
    "Hunter": { "count": 5, "percentage": 17.9 }
  },
  "performance_by_class": {
    "Warrior": { "avg_dps": 380000, "avg_hps": 45000 },
    "Mage": { "avg_dps": 520000, "avg_hps": 12000 }
  },
  "recommendations": [
    "Consider recruiting more healers for raid balance",
    "Warrior DPS performance is below average - consider gear optimization"
  ]
}
```

## Guild Administration

### Update Guild Information

Update your guild's basic information (requires admin permissions).

```http
PUT /guilds/current
```

**Request Body:**

```json
{
  "guild_name": "Updated Guild Name",
  "server": "New Server",
  "region": "US",
  "faction": "Alliance"
}
```

**Response:**

```json
{
  "guild_id": 123,
  "guild_name": "Updated Guild Name",
  "server": "New Server",
  "region": "US",
  "faction": "Alliance",
  "updated_at": "2024-09-20T15:30:00Z"
}
```

### Create Guild API Key

Generate a new API key for your guild (admin only).

```http
POST /guilds/current/api-keys
```

**Request Body:**

```json
{
  "name": "Discord Bot Key",
  "permissions": ["read", "upload"],
  "expires_at": "2025-09-20T00:00:00Z"
}
```

**Response:**

```json
{
  "api_key": "guild_123_key_abc123def456",
  "name": "Discord Bot Key",
  "permissions": ["read", "upload"],
  "created_at": "2024-09-20T15:30:00Z",
  "expires_at": "2025-09-20T00:00:00Z"
}
```

### List Guild API Keys

List all API keys for your guild (admin only).

```http
GET /guilds/current/api-keys
```

**Response:**

```json
{
  "data": [
    {
      "key_id": "key_123",
      "name": "Main API Key",
      "permissions": ["read", "write", "admin"],
      "last_used": "2024-09-20T14:30:00Z",
      "created_at": "2024-01-15T10:00:00Z",
      "expires_at": null
    }
  ]
}
```

### Revoke Guild API Key

Revoke an API key (admin only).

```http
DELETE /guilds/current/api-keys/{key_id}
```

**Response:**

```json
{
  "message": "API key revoked successfully",
  "revoked_at": "2024-09-20T15:45:00Z"
}
```

## Error Responses

### Common Guild Errors

#### Guild Not Found

```json
{
  "error": "guild_not_found",
  "message": "Guild not found or access denied",
  "status_code": 404
}
```

#### Guild Required

```json
{
  "error": "guild_required",
  "message": "Guild ID is required. Please ensure your API key is associated with a guild.",
  "status_code": 400
}
```

#### Insufficient Permissions

```json
{
  "error": "insufficient_permissions",
  "message": "Admin permissions required for this operation",
  "status_code": 403
}
```

## Rate Limiting

Guild API endpoints have specific rate limits:

- **Standard Endpoints**: 1000 requests per hour per guild
- **Analytics Endpoints**: 100 requests per hour per guild
- **Admin Endpoints**: 50 requests per hour per guild

Rate limit headers are included in all responses:

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1695225600
X-Guild-Context: 123
```

## Best Practices

### 1. Cache Guild Information

```python
class GuildClient:
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
```

### 2. Handle Multi-Guild Context

```python
def get_encounters(guild_id=None, **params):
    """Get encounters with optional guild specification."""
    if guild_id:
        params['guild_id'] = guild_id

    response = requests.get(
        "https://api.example.com/api/v1/encounters",
        headers=headers,
        params=params
    )
    return response.json()
```

### 3. Monitor Guild Activity

```python
def monitor_guild_activity():
    """Monitor recent guild activity."""
    # Get recent encounters
    recent = requests.get(
        "https://api.example.com/api/v1/encounters",
        headers=headers,
        params={"days": 1, "limit": 50}
    ).json()

    # Get guild statistics
    stats = requests.get(
        "https://api.example.com/api/v1/guilds/current/statistics",
        headers=headers,
        params={"days": 7}
    ).json()

    return {
        "recent_encounters": len(recent['data']),
        "weekly_success_rate": stats['encounters']['success_rate'],
        "active_members": stats['characters']['active_last_week']
    }
```

## Examples

### Complete Guild Dashboard

```python
import requests
from datetime import datetime, timedelta

class GuildDashboard:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.base_url = "https://api.example.com/api/v1"

    def get_dashboard_data(self):
        """Get comprehensive guild dashboard data."""

        # Guild basic info
        guild_info = self._get_guild_info()

        # Recent activity (last 7 days)
        recent_encounters = self._get_recent_encounters(days=7)

        # Performance trends (last 30 days)
        performance_trends = self._get_performance_trends(days=30)

        # Class balance
        class_balance = self._get_class_balance()

        # Top performers
        top_performers = self._get_top_performers()

        return {
            "guild": guild_info,
            "recent_activity": recent_encounters,
            "performance_trends": performance_trends,
            "class_balance": class_balance,
            "top_performers": top_performers,
            "last_updated": datetime.utcnow().isoformat()
        }

    def _get_guild_info(self):
        response = requests.get(f"{self.base_url}/guilds/current", headers=self.headers)
        return response.json()

    def _get_recent_encounters(self, days=7):
        response = requests.get(
            f"{self.base_url}/encounters",
            headers=self.headers,
            params={"days": days, "limit": 100}
        )
        return response.json()

    def _get_performance_trends(self, days=30):
        response = requests.get(
            f"{self.base_url}/analytics/guild/trends",
            headers=self.headers,
            params={"metric": "dps", "days": days, "period": "daily"}
        )
        return response.json()

    def _get_class_balance(self):
        response = requests.get(
            f"{self.base_url}/analytics/guild/class-balance",
            headers=self.headers
        )
        return response.json()

    def _get_top_performers(self):
        response = requests.get(
            f"{self.base_url}/characters",
            headers=self.headers,
            params={"limit": 10, "sort": "performance", "order": "desc"}
        )
        return response.json()

# Usage
dashboard = GuildDashboard("your_api_key_here")
data = dashboard.get_dashboard_data()

print(f"Guild: {data['guild']['guild_name']}")
print(f"Recent Encounters: {len(data['recent_activity']['data'])}")
print(f"Performance Trend: {data['performance_trends']['summary']['trend_direction']}")
```

## See Also

- [Guild Setup Guide](../getting-started/guild-setup.md) - Complete guild setup instructions
- [Authentication](../getting-started/authentication.md) - API key management
- [Characters API](characters.md) - Character-specific endpoints
- [Encounters API](encounters.md) - Encounter-specific endpoints
- [Analytics API](analytics.md) - Advanced analytics endpoints
