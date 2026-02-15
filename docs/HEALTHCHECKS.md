# Healthchecks.io Integration

[Healthchecks.io](https://healthchecks.io/) monitors your CI pipeline and scheduled tasks, alerting you when runs are late or failing.

## Quick Setup

1. Create a free account at <https://healthchecks.io/>
2. Create a new check named **MediaLibrary CI**
3. Copy the **ping URL** (e.g. `https://hc-ping.com/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
4. Add it as a GitHub repository secret:

   ```
   Settings → Secrets and variables → Actions → New repository secret
   Name:  HEALTHCHECKS_PING_URL
   Value: https://hc-ping.com/<your-uuid>
   ```

## What Gets Pinged

### CI Pipeline (automatic)

The GitHub Actions workflow (`.github/workflows/ci.yml`) pings Healthchecks.io after every successful test run on `main`:

| Event | Endpoint | Meaning |
|-------|----------|---------|
| Tests pass | `$PING_URL` | All good |
| Tests fail | `$PING_URL/fail` | Pipeline broken |

If the secret is not set, the ping step is silently skipped.

### Scheduled Monitoring (optional)

You can also add pings for long-running daemons. Add checks for:

| Check Name | Schedule | Purpose |
|------------|----------|---------|
| Disc Monitor | Every 5 min | Confirms `--mode monitor` is alive |
| Podcast Checker | Every 1 hr | Confirms feed polling is running |
| Job Worker | Every 5 min | Confirms encode queue is being processed |

#### Example: Cron-based ping

```bash
# In crontab or launchd, wrap the daemon with a health ping:
curl -fsS -m 10 --retry 5 https://hc-ping.com/<uuid>/start
media-server-full
curl -fsS -m 10 --retry 5 https://hc-ping.com/<uuid>
```

#### Example: In-app ping (Python)

Add to any periodic loop (e.g. `disc_monitor.py` poll cycle):

```python
import os, requests

def ping_healthcheck(status: str = "") -> None:
    url = os.getenv("HEALTHCHECKS_PING_URL")
    if not url:
        return
    suffix = f"/{status}" if status else ""
    try:
        requests.get(f"{url}{suffix}", timeout=5)
    except Exception:
        pass  # Non-critical — don't crash the monitor
```

Call `ping_healthcheck()` on success, `ping_healthcheck("fail")` on error.

## Alert Channels

Configure notifications under **Integrations** in the Healthchecks.io dashboard:

- **Email** — built-in, no setup required
- **Slack** — webhook URL
- **Discord** — webhook URL
- **PagerDuty** — for critical production alerts
- **Ntfy / Pushover** — mobile push notifications

## Recommended Check Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Period | 1 day | CI runs at least daily |
| Grace | 2 hours | Allow for slow runners / GitHub outages |
| Timezone | UTC | Matches CI runner timezone |
| Tags | `ci`, `medialibrary` | Easy filtering |
