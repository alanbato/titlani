# Rate Limiting

The Titlani server supports token bucket rate limiting via tlacacoca's `RateLimiter` middleware.

## Enable in Config

Add a `[rate_limit]` section to your TOML config:

```toml
[rate_limit]
enable = true
capacity = 10
refill_rate = 1.0
retry_after = 30
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable` | bool | `false` | Enable rate limiting |
| `capacity` | int | `10` | Maximum tokens in the bucket |
| `refill_rate` | float | `1.0` | Tokens added per second |
| `retry_after` | int | `30` | Seconds to suggest in slow-down response |

## How It Works

The rate limiter uses a token bucket algorithm:

1. Each client (identified by IP) gets a bucket with `capacity` tokens
2. Each request consumes one token
3. Tokens refill at `refill_rate` per second
4. When the bucket is empty, the server responds with status **44** (slow down)

## Tuning

**Permissive** — Allow bursts, quick refill:

```toml
[rate_limit]
enable = true
capacity = 50
refill_rate = 5.0
retry_after = 10
```

**Restrictive** — Small bursts, slow refill:

```toml
[rate_limit]
enable = true
capacity = 3
refill_rate = 0.1
retry_after = 60
```

## Client Behavior

When rate limited, clients receive:

```
44 Slow down
```

Well-behaved clients should wait at least `retry_after` seconds before retrying. Titlani's `MisfinClient` does not automatically retry on status 44 — the caller should implement retry logic as needed.
