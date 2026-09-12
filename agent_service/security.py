"""Short-lived server-to-server identities; browsers authenticate through Flask."""
import fcntl
import os
import secrets
from pathlib import Path

from itsdangerous import URLSafeTimedSerializer, BadData


def secret_key():
    configured = os.getenv('SECRET_KEY', '').strip()
    if configured and configured != 'dev':
        return configured
    path = Path(os.getenv('APP_SECRET_FILE', 'instance/app-secret.key'))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        value = handle.read().strip()
        if not value:
            value = secrets.token_urlsafe(48)
            handle.write(value)
            handle.flush()
        return value


def issue_identity(role, principal, airline=''):
    return URLSafeTimedSerializer(secret_key(), salt='agent-service-v1').dumps(
        {'role': role, 'principal': principal, 'airline': airline})


def read_identity(token):
    actor = URLSafeTimedSerializer(secret_key(), salt='agent-service-v1').loads(token, max_age=120)
    if not isinstance(actor, dict) or actor.get('role') not in {'customer', 'staff', 'operator'} or not actor.get('principal'):
        raise BadData('Invalid identity')
    return actor
