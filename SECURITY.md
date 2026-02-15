# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |
| 0.2.x   | Security fixes only |
| < 0.2   | No        |

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, please email **ben@medialibrary.local** with:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact assessment
4. Suggested fix (if you have one)

You should receive an acknowledgement within **48 hours**. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Security Measures in Place

### Authentication & Sessions
- Passwords are hashed with `pbkdf2:sha256` via Werkzeug
- Server-side session tokens with configurable expiry (`auth.session_hours`)
- Session invalidation on logout
- First-run setup flow (no default credentials in code or config)
- Role-based access: `admin` and `user`

### HTTP Security Headers
All responses include:
- `Content-Security-Policy`
- `Strict-Transport-Security` (when `SECURE_COOKIES=true`)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`

### Input Validation
- Upload size enforcement via `Content-Length` header and `MAX_CONTENT_LENGTH`
- HTML-escaped article archiving content to prevent XSS
- Shell command arguments sanitised in `send_notification()` via `subprocess.run()`
- CORS restricting WebSocket origins via `CORS_ALLOWED_ORIGINS`

### Secrets Management
- `FLASK_SECRET_KEY` via environment variable (not committed to version control)
- API keys (`TMDB_API_KEY`, `ACOUSTID_API_KEY`, `JELLYFIN_API_KEY`) via `.env`
- `.env` is listed in `.gitignore`

## Best Practices for Deployment

1. **Always set `FLASK_SECRET_KEY`** — without it, sessions are lost on restart
2. **Set `SECURE_COOKIES=true`** when behind HTTPS (e.g., Cloudflare Tunnel)
3. **Restrict `CORS_ALLOWED_ORIGINS`** to your domain in production
4. **Use non-default ports** if exposing to a network
5. **Keep dependencies updated** — run `pip install -U -r requirements.txt` regularly
6. **Review `config.json`** — ensure no plaintext secrets or sensitive paths are committed

## Known Limitations

- SQLite does not support encrypted-at-rest storage. The database file at `MEDIA_ROOT/data/media_ripper.db` contains user credentials (hashed) and session tokens.
- The Flask development server (Werkzeug) is used in Docker with `ALLOW_UNSAFE_WERKZEUG=1`. For high-traffic production deployments, consider a WSGI server like Gunicorn.
- File paths in the database are absolute. Access to the media filesystem implies access to all library content.
