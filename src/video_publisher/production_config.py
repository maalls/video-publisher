"""Fixed deployment names for the proposed private-state production path.

No grants, secrets or resources are created by importing this module.
"""
STATE_REPOSITORY = "maalls/video-publisher-state"
STATE_BRANCH = "main"
STATE_FILE = "state.enc"
ACTIONS_ENVIRONMENT = "publisher-production"
STATE_TOKEN_SECRET = "VP_STATE_TOKEN"
STATE_KEY_SECRET = "VP_STATE_KEY"


def load_state_session(environ):
    from .durable_state import GitHubStateStore, StateCodec, StateError, StateSession
    if (environ.get("GITHUB_REPOSITORY") != "maalls/video-publisher"
            or environ.get("GITHUB_REF") != "refs/heads/main"
            or environ.get("GITHUB_EVENT_NAME") not in {"schedule", "workflow_dispatch"}):
        raise StateError("Contexte de production non autorisé")
    token = environ.get(STATE_TOKEN_SECRET, "")
    key = environ.get(STATE_KEY_SECRET, "")
    if not token or not key:
        raise StateError("Secrets d'état non configurés")
    return StateSession(GitHubStateStore(STATE_REPOSITORY, token), StateCodec(key))
