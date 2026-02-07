# Logs Directory

This directory contains application log files:

- `ripper.log` - DVD/CD ripping operations
- `metadata.log` - Metadata extraction and enrichment
- `disc_monitor.log` - Disc detection and monitoring events
- `web_server.log` - Web server requests and errors

Logs are rotated automatically when they exceed 10MB.

## Log Levels

- DEBUG: Detailed information for diagnosing problems
- INFO: Confirmation that things are working as expected
- WARNING: Indication of unexpected events
- ERROR: Serious problems that need attention
- CRITICAL: System failures

## Viewing Logs

View the most recent entries:
```bash
tail -f logs/ripper.log
```

Search for errors:
```bash
grep ERROR logs/*.log
```
