# WoW Combat Log Analysis API v1

Welcome to the comprehensive documentation for the World of Warcraft Combat Log Analysis API. This powerful REST API provides extensive capabilities for parsing, analyzing, and querying WoW combat log data.

## Overview

The WoW Combat Log Analysis API enables developers to:

- **Parse and Process** combat logs in real-time or batch mode
- **Analyze Performance** with detailed metrics and statistics
- **Track Characters** across encounters and time periods
- **Monitor Encounters** with comprehensive replay capabilities
- **Generate Analytics** with advanced aggregation and trending
- **Search and Filter** data with powerful query capabilities
- **Stream Real-time** updates via WebSocket connections
- **Manage Guild Data** with multi-tenant architecture and data isolation

## Key Features

### 🔍 **Advanced Analytics**

- Performance trending and forecasting
- Class balance analysis
- Cross-encounter comparisons
- Percentile calculations and distributions

### 📊 **Comprehensive Data Model**

- Character profiles with complete performance history
- Detailed encounter analysis with timeline reconstruction
- Guild management and progression tracking with multi-tenant isolation
- Spell usage statistics and optimization insights

### 🚀 **High Performance**

- Optimized database queries with intelligent caching
- Rate limiting and performance monitoring
- Parallel processing for large datasets
- Real-time streaming capabilities

### 🔐 **Enterprise Ready**

- Robust authentication with API keys
- Comprehensive rate limiting
- Detailed audit logging
- Error handling and monitoring

## Quick Start

Get started with the API in minutes:

=== "Python"

    ```python
    import requests

    # Set your API key (must be associated with a guild)
    headers = {"Authorization": "Bearer YOUR_API_KEY"}

    # Get character performance for your guild
    response = requests.get(
        "https://api.example.com/api/v1/characters/Thrall/performance",
        headers=headers,
        params={"days": 30, "encounter_type": "raid"}
    )

    performance_data = response.json()
    print(f"Average DPS: {performance_data['summary']['avg_dps']}")
    ```

=== "JavaScript"

    ```javascript
    // API key must be associated with a guild
    const apiKey = 'YOUR_API_KEY';

    const response = await fetch(
        'https://api.example.com/api/v1/characters/Thrall/performance?days=30&encounter_type=raid',
        {
            headers: {
                'Authorization': `Bearer ${apiKey}`
            }
        }
    );

    const performanceData = await response.json();
    console.log(`Average DPS: ${performanceData.summary.avg_dps}`);
    ```

=== "cURL"

    ```bash
    curl -H "Authorization: Bearer YOUR_API_KEY" \
         "https://api.example.com/api/v1/characters/Thrall/performance?days=30&encounter_type=raid"
    ```

## API Endpoints Overview

| Category         | Endpoints       | Description                               |
| ---------------- | --------------- | ----------------------------------------- |
| **Characters**   | `/characters`   | Character profiles, performance, rankings |
| **Encounters**   | `/encounters`   | Encounter details, replay, analysis       |
| **Analytics**    | `/analytics`    | Trends, comparisons, advanced metrics     |
| **Search**       | `/search`       | Full-text search, fuzzy matching          |
| **Aggregations** | `/aggregations` | Custom metrics, percentiles, correlations |
| **Logs**         | `/logs`         | Upload, processing, streaming             |
| **Streaming**    | `/stream`       | Real-time WebSocket updates               |
| **Guilds**       | `/guilds`       | Guild management, member analytics        |

## Interactive API Explorer

Explore the API interactively with our built-in tools:

<div class="grid cards" markdown>

- :material-api: **OpenAPI Spec**

  ***

  Browse the complete OpenAPI specification with interactive examples

  [Explore API :octicons-arrow-right-24:](../openapi.yaml){ .md-button }

- :material-code-braces: **Swagger UI**

  ***

  Test endpoints directly in your browser with Swagger UI

  [Try API :octicons-arrow-right-24:](/api/v1/docs){ .md-button }

- :material-book-open: **ReDoc**

  ***

  Beautiful, responsive API documentation with ReDoc

  [View Docs :octicons-arrow-right-24:](/api/v1/redoc){ .md-button }

</div>

## Example Use Cases

### Performance Monitoring

Track character performance across raids and dungeons:

```python
# Get trending performance for a character
trends = api.get_performance_trends(
    character="Thrall",
    metric="dps",
    days=90
)

# Analyze improvement over time
improvement = trends["summary"]["trend_direction"]
print(f"Performance trend: {improvement}")
```

### Guild Analytics

Monitor guild progression and member performance:

```python
# Get guild roster with performance metrics
guild = api.get_guild("Earthen Ring", include_members=True)

# Calculate guild-wide statistics
avg_performance = sum(m.performance.avg_dps for m in guild.members) / len(guild.members)
```

### Real-time Monitoring

Stream live encounter data:

```javascript
const ws = new WebSocket("wss://api.example.com/api/v1/stream");

ws.on("encounter_update", (data) => {
  console.log(`Live DPS: ${data.current_dps}`);
  updateDashboard(data);
});
```

## Support and Community

- 📖 **Documentation**: Complete guides and references
- 💬 **Discord**: Join our community for support
- 🐛 **Issues**: Report bugs on GitHub
- 📧 **Email**: Contact support team

## Version Information

- **Current Version**: 1.0.0
- **Release Date**: January 2024
- **Stability**: Production Ready
- **Breaking Changes**: See [Changelog](changelog.md)

---

Ready to get started? Check out the [Quick Start Guide](getting-started/quick-start.md) or explore the [API Reference](api-reference/overview.md).
