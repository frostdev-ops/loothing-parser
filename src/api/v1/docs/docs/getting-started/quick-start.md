# Quick Start Guide

Get up and running with the WoW Combat Log Analysis API in just a few minutes. This guide walks you through the essential steps to start analyzing combat log data.

## Prerequisites

Before you begin, ensure you have:

- A valid API key (contact support to obtain one)
- Basic understanding of REST APIs
- A tool for making HTTP requests (cURL, Postman, or programming language of choice)

## Step 1: Get Your API Key

Contact our support team to obtain your API key. You'll receive:

- **API Key**: Your unique authentication token
- **Base URL**: The API endpoint (typically `https://api.example.com/api/v1`)
- **Rate Limits**: Your specific usage limits

!!! tip "API Key Security"
    Keep your API key secure and never expose it in client-side code or public repositories.

## Step 2: Test Your Connection

First, let's verify your API key works by checking the health endpoint:

=== "cURL"

    ```bash
    curl -H "Authorization: Bearer YOUR_API_KEY" \
         https://api.example.com/api/v1/health
    ```

=== "Python"

    ```python
    import requests

    headers = {"Authorization": "Bearer YOUR_API_KEY"}
    response = requests.get("https://api.example.com/api/v1/health", headers=headers)
    print(response.json())
    ```

=== "JavaScript"

    ```javascript
    const response = await fetch('https://api.example.com/api/v1/health', {
        headers: {
            'Authorization': 'Bearer YOUR_API_KEY'
        }
    });
    const health = await response.json();
    console.log(health);
    ```

**Expected Response:**
```json
{
    "status": "healthy",
    "timestamp": "2024-01-15T10:30:00Z",
    "version": "1.0.0",
    "database": {
        "status": "healthy",
        "latency_ms": 12.5
    }
}
```

## Step 3: Explore Characters

Let's start by exploring character data:

### List Characters

Get a list of characters in the system:

=== "cURL"

    ```bash
    curl -H "Authorization: Bearer YOUR_API_KEY" \
         "https://api.example.com/api/v1/characters?limit=5"
    ```

=== "Python"

    ```python
    import requests

    headers = {"Authorization": "Bearer YOUR_API_KEY"}
    params = {"limit": 5}

    response = requests.get(
        "https://api.example.com/api/v1/characters",
        headers=headers,
        params=params
    )

    characters = response.json()
    for char in characters["data"]:
        print(f"{char['name']} - {char['class_name']} ({char['guild_name']})")
    ```

=== "JavaScript"

    ```javascript
    const response = await fetch(
        'https://api.example.com/api/v1/characters?limit=5',
        { headers: { 'Authorization': 'Bearer YOUR_API_KEY' } }
    );

    const characters = await response.json();
    characters.data.forEach(char => {
        console.log(`${char.name} - ${char.class_name} (${char.guild_name})`);
    });
    ```

### Get Character Details

Retrieve detailed information about a specific character:

=== "cURL"

    ```bash
    curl -H "Authorization: Bearer YOUR_API_KEY" \
         "https://api.example.com/api/v1/characters/Thrall?server=Stormrage"
    ```

=== "Python"

    ```python
    response = requests.get(
        "https://api.example.com/api/v1/characters/Thrall",
        headers=headers,
        params={"server": "Stormrage"}
    )

    character = response.json()
    print(f"Character: {character['name']}")
    print(f"Class: {character['class_name']} ({character['spec_name']})")
    print(f"Guild: {character['guild_name']}")
    print(f"Average Item Level: {character['avg_item_level']}")
    ```

## Step 4: Analyze Performance

Now let's look at character performance data:

### Get Performance Metrics

=== "Python"

    ```python
    # Get 30-day performance for raids
    response = requests.get(
        "https://api.example.com/api/v1/characters/Thrall/performance",
        headers=headers,
        params={
            "days": 30,
            "encounter_type": "raid",
            "difficulty": "heroic"
        }
    )

    performance = response.json()

    # Display summary
    summary = performance["summary"]
    print(f"Average DPS: {summary['avg_dps']:,.0f}")
    print(f"Best DPS: {summary['best_dps']:,.0f}")
    print(f"Survival Rate: {summary['survival_rate']:.1f}%")
    print(f"Parse Percentile: {summary['parse_percentile']:.1f}")

    # Show recent encounters
    print("\nRecent Encounters:")
    for encounter in performance["performances"][:5]:
        print(f"  {encounter['encounter_name']}: {encounter['dps']:,.0f} DPS")
    ```

=== "JavaScript"

    ```javascript
    const response = await fetch(
        'https://api.example.com/api/v1/characters/Thrall/performance?days=30&encounter_type=raid&difficulty=heroic',
        { headers: { 'Authorization': 'Bearer YOUR_API_KEY' } }
    );

    const performance = await response.json();

    // Display summary
    const summary = performance.summary;
    console.log(`Average DPS: ${summary.avg_dps.toLocaleString()}`);
    console.log(`Best DPS: ${summary.best_dps.toLocaleString()}`);
    console.log(`Survival Rate: ${summary.survival_rate.toFixed(1)}%`);

    // Show recent encounters
    console.log('Recent Encounters:');
    performance.performances.slice(0, 5).forEach(encounter => {
        console.log(`  ${encounter.encounter_name}: ${encounter.dps.toLocaleString()} DPS`);
    });
    ```

## Step 5: Explore Encounters

Analyze specific encounters:

### List Recent Encounters

=== "Python"

    ```python
    # Get recent successful raid encounters
    response = requests.get(
        "https://api.example.com/api/v1/encounters",
        headers=headers,
        params={
            "encounter_type": "raid",
            "success_only": True,
            "days": 7,
            "limit": 10
        }
    )

    encounters = response.json()
    print("Recent Successful Raids:")
    for encounter in encounters["data"]:
        duration_min = encounter["duration"] / 60
        print(f"  {encounter['boss_name']} ({encounter['difficulty']}) - {duration_min:.1f}min")
    ```

### Get Encounter Details

=== "Python"

    ```python
    # Get detailed information about a specific encounter
    encounter_id = 12345  # Replace with actual encounter ID

    response = requests.get(
        f"https://api.example.com/api/v1/encounters/{encounter_id}",
        headers=headers
    )

    encounter = response.json()
    print(f"Encounter: {encounter['boss_name']}")
    print(f"Duration: {encounter['duration']/60:.1f} minutes")
    print(f"Success: {'Yes' if encounter['success'] else 'No'}")
    print(f"Participants: {len(encounter['participants'])}")

    # Top DPS players
    top_dps = sorted(encounter["participants"], key=lambda x: x["dps"], reverse=True)[:3]
    print("\nTop DPS:")
    for i, player in enumerate(top_dps, 1):
        print(f"  {i}. {player['character_name']}: {player['dps']:,.0f}")
    ```

## Step 6: Use Analytics

Explore performance trends and analytics:

### Performance Trends

=== "Python"

    ```python
    # Get DPS trends for the last 90 days
    response = requests.get(
        "https://api.example.com/api/v1/analytics/trends/dps",
        headers=headers,
        params={
            "character_name": "Thrall",
            "days": 90,
            "granularity": "weekly"
        }
    )

    trends = response.json()
    print(f"DPS Trend: {trends['trend_direction']}")
    print(f"Average: {trends['average_value']:,.0f}")
    print(f"Improvement: {trends['trend_strength']:.2f}")

    # Plot data points (requires matplotlib)
    import matplotlib.pyplot as plt
    from datetime import datetime

    timestamps = [datetime.fromisoformat(dp["timestamp"].replace("Z", "+00:00"))
                 for dp in trends["data_points"]]
    values = [dp["value"] for dp in trends["data_points"]]

    plt.figure(figsize=(12, 6))
    plt.plot(timestamps, values, marker='o')
    plt.title(f"DPS Trend for {trends.get('character_name', 'Character')}")
    plt.xlabel("Date")
    plt.ylabel("DPS")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()
    ```

## Step 7: Advanced Features

### Search Characters

Use the search functionality to find characters:

=== "Python"

    ```python
    # Search for characters matching criteria
    search_request = {
        "query": "shaman",
        "scope": "characters",
        "fuzzy_matching": True,
        "limit": 10
    }

    response = requests.post(
        "https://api.example.com/api/v1/search",
        headers=headers,
        json=search_request
    )

    results = response.json()
    print(f"Found {results['total_count']} results in {results['query_time_ms']}ms")

    for result in results["results"]:
        char_data = result["data"]
        print(f"  {char_data['name']} - {char_data['class_name']} ({result['relevance_score']:.2f})")
    ```

### Custom Aggregations

Create custom performance aggregations:

=== "Python"

    ```python
    # Calculate percentiles for DPS across all raiders
    aggregation_request = {
        "metrics": ["dps"],
        "group_by": ["class_name"],
        "filters": {
            "encounter_type": "raid",
            "difficulty": "heroic",
            "days": 30
        },
        "percentiles": [25, 50, 75, 90, 95]
    }

    response = requests.post(
        "https://api.example.com/api/v1/aggregations/custom",
        headers=headers,
        json=aggregation_request
    )

    results = response.json()
    print("DPS Percentiles by Class:")
    for class_data in results["data"]:
        class_name = class_data["class_name"]
        p50 = class_data["dps_p50"]
        p95 = class_data["dps_p95"]
        print(f"  {class_name}: {p50:,.0f} (median) / {p95:,.0f} (95th percentile)")
    ```

## Error Handling

Always implement proper error handling:

=== "Python"

    ```python
    import requests
    from requests.exceptions import RequestException

    def api_request(url, headers, **kwargs):
        try:
            response = requests.get(url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                print("Authentication failed. Check your API key.")
            elif response.status_code == 429:
                print("Rate limit exceeded. Please wait before retrying.")
            elif response.status_code == 404:
                print("Resource not found.")
            else:
                print(f"HTTP error: {e}")
        except RequestException as e:
            print(f"Request failed: {e}")
        return None

    # Usage
    character = api_request(
        "https://api.example.com/api/v1/characters/Thrall",
        headers=headers
    )
    if character:
        print(f"Found character: {character['name']}")
    ```

## Rate Limiting

Monitor your rate limit usage:

```python
response = requests.get(url, headers=headers)

# Check rate limit headers
remaining = response.headers.get('X-RateLimit-Remaining-Minute')
limit = response.headers.get('X-RateLimit-Limit-Minute')
reset_time = response.headers.get('X-RateLimit-Reset')

print(f"Rate limit: {remaining}/{limit} requests remaining")
```

## Next Steps

Now that you're familiar with the basics:

1. **Explore the [API Reference](../api-reference/overview.md)** for complete endpoint documentation
2. **Check out [Examples](../examples/basic-usage.md)** for more complex use cases
3. **Download [Client Libraries](../client-libraries/python.md)** for your preferred language
4. **Join our [Discord Community](https://discord.gg/your-server)** for support and discussions

## Common Issues

### Authentication Problems
- Double-check your API key is correct
- Ensure you're using the `Authorization: Bearer` header format
- Verify your key hasn't expired

### Rate Limiting
- Monitor the `X-RateLimit-*` headers in responses
- Implement exponential backoff for retries
- Consider upgrading your plan for higher limits

### Data Not Found
- Characters must have recent activity to appear in results
- Check server names are spelled correctly
- Verify the time range includes the data you're looking for

For more help, see our [Troubleshooting Guide](../guides/troubleshooting.md) or contact support.