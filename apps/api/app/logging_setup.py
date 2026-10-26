import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from traceback import walk_tb

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
# A per-request mutable record shared with the synchronous route's worker thread.
score_query_log: ContextVar[dict | None] = ContextVar("score_query_log", default=None)

EVENT_MESSAGES = {
    "api_started": "API started with the configured request limits and cache settings",
    "api_stopped": "API stopped",
    "request_started": "Request received",
    "request_completed": "Request completed successfully",
    "request_failed": "Unexpected application error; see the safe code locations",
    "request_rejected": "Request could not be fulfilled",
    "scores_query_started": "Score query started",
    "scores_query_completed": "Score query completed",
    "scores_cache_lookup": "Score cache checked; MISS may require a fresh osu! lookup",
    "scores_cache_invalid": "Cached scores are invalid; fresh scores will be requested",
    "negative_cache_hit": "A recent lookup already confirmed that this player does not exist",
    "negative_cache_written": "Player-not-found result cached to avoid repeated upstream lookups",
    "negative_cache_write_failed": "Could not save the player-not-found cache",
    "negative_cache_delete_failed": "Could not remove a stale player-not-found entry",
    "scores_fetch_busy": "Another score query is using the upstream connection",
    "scores_cache_written": "Fresh scores saved to the shared cache",
    "scores_cache_write_failed": "Could not cache scores; returning the fetched data directly",
    "cache_read_failed": "Could not read a cache file; treating it as a cache miss",
    "cache_entry_invalid": "A cache file is corrupt or invalid; treating it as a cache miss",
    "cache_cleanup_failed": "Could not remove an expired cache file",
    "scores_ready": "Scores ready to return to the browser",
    "usage_write_failed": "Could not update usage statistics; the score response is unaffected",
    "audit_write_failed": "Could not save the administrator request audit record",
    "admin_cleanup_failed": "Could not remove expired administrator audit records",
    "admin_login_failed": "Administrator login was rejected",
    "osu_query_started": "Starting osu! lookup; checking capacity for all required HTTP requests",
    "oauth_token_reused": "Reusing the site OAuth token; no new token request is needed",
    "oauth_token_requested": "Requesting an OAuth token using the selected credentials",
    "oauth_token_ready": "OAuth token obtained; token contents are not logged",
    "oauth_token_invalidated": "Cached site token rejected; the next query will obtain a new one",
    "osu_mode_resolved": "Player profile loaded and game mode resolved",
    "osu_query_completed": "osu! player profile and best scores loaded",
    "osu_query_failed": "osu! lookup failed; see the error type and safe code locations",
    "osu_http_started": "Sending an HTTP request to osu!",
    "osu_http_completed": "osu! HTTP request completed",
    "osu_http_failed": "osu! HTTP request failed before a response was available",
    "local_rate_limited": "Site request limit reached; wait retry_after seconds before retrying",
    "upstream_wait": "Upstream capacity unavailable; wait retry_after seconds before retrying",
    "upstream_pacing": "Spacing upstream requests to avoid a burst",
    "upstream_rate_limited": "Upstream returned HTTP 429; its request budget is now cooling down",
    "image_cache_lookup": "Artwork cache checked",
    "image_http_completed": "Artwork download completed",
    "image_http_failed": "Artwork download failed",
    "image_fetch_wait": "Artwork is waiting for upstream capacity",
    "image_queue_timeout": "Artwork queue exceeded its 75-second deadline",
    "image_cache_write_failed": "Could not save artwork; returning the downloaded image",
    "images_enqueued": "Artwork prefetch queue updated",
    "image_warm_completed": "Background artwork caching completed",
    "image_warm_failed": "Background artwork caching skipped an unavailable image",
}

ERROR_DETAILS = {
    "INVALID_REQUEST": (
        "Request parameters or credential headers are invalid",
        "Check parameter types, mode, limit and credential headers",
    ),
    "INVALID_PLAYER": (
        "Player input is invalid",
        "Use a username or numeric ID of 1-32 characters",
    ),
    "INVALID_CREDENTIALS": (
        "Personal API credentials are incomplete or were rejected",
        "Check both the OAuth Client ID and Client Secret",
    ),
    "PLAYER_NOT_FOUND": (
        "osu! could not find the requested player",
        "Check the username or numeric ID",
    ),
    "RATE_LIMITED": (
        "A site IP or player request limit was reached",
        "Wait retry_after seconds before trying again",
    ),
    "SERVER_BUSY": (
        "Another score lookup is already running",
        "Wait retry_after seconds; the browser retries automatically",
    ),
    "UPSTREAM_BUSY": (
        "The osu! request budget is exhausted or cooling down",
        "Wait retry_after seconds; personal credentials use the same site budget",
    ),
    "NOT_CONFIGURED": (
        "No usable OAuth credentials were provided",
        "Configure site credentials or supply personal API credentials",
    ),
    "UPSTREAM_ERROR": (
        "An osu! request, authentication step or response processing failed",
        "Check the osu_http events with the same request_id for phase, status and timing",
    ),
    "INTERNAL_ERROR": (
        "An unexpected application error occurred",
        "Check request_failed with the same request_id and its error_trace",
    ),
    "INVALID_IMAGE": (
        "The artwork URL is not supported",
        "Use an allowed osu! avatar or beatmap cover URL",
    ),
    "IMAGE_UNAVAILABLE": (
        "Artwork could not be downloaded or validated",
        "Check image_http events and retry the export",
    ),
    "IMAGE_BUSY": (
        "Artwork could not be fetched within the queue deadline",
        "Wait retry_after seconds and retry the export",
    ),
}

REASON_DETAILS = {
    "budget_exhausted": "The per-minute request budget has been used up",
    "upstream_cooldown": "The upstream HTTP 429 cooldown is still active",
    "invalid_structure": "The cache file has an unexpected data structure",
    "invalid_timestamp": "The cache timestamp is invalid or in the future",
    "missing_timezone": "Cached scores have no timezone on their fetch timestamp",
    "http_status": "The image server returned an unsuccessful HTTP status",
    "unsupported_type": "The image server returned an unsupported content type",
    "image_too_large": "The image exceeded the 5 MiB size limit",
    "empty_image": "The image server returned an empty response",
}


def safe_error_fields(error: BaseException) -> dict:
    # Record application code locations, never exception text, source lines or local values.
    root = Path(__file__).resolve().parent
    frames = []
    for frame, line in walk_tb(error.__traceback__):
        path = Path(frame.f_code.co_filename)
        if path.is_relative_to(root):
            frames.append(f"{path.relative_to(root)}:{line}:{frame.f_code.co_name}")
    fields = {"error_type": type(error).__name__}
    if frames:
        fields["error_trace"] = frames[-10:]
    if isinstance(error, OSError) and error.errno is not None:
        fields["error_errno"] = error.errno
    return fields


def record_data(record: logging.LogRecord) -> dict:
    event = record.getMessage()
    data = {
        "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
        "level": record.levelname,
        "event": event,
        "message": EVENT_MESSAGES.get(event, event),
        "logger": record.name,
    }
    if current_id := request_id.get():
        data["request_id"] = current_id
    data.update(getattr(record, "fields", {}))
    if event == "request_completed" and data.get("status", 200) >= 400:
        data["message"] = "Request completed with an error"
    if event == "scores_query_completed" and data.get("status", 200) >= 400:
        data["message"] = "Score query completed with an error"
    if event == "osu_http_completed" and data.get("status", 200) >= 400:
        data["message"] = "osu! HTTP request was rejected"
        if data.get("phase") == "oauth" and data["status"] in (400, 401):
            data["error_reason"] = "OAuth credentials were rejected by osu!"
            data["next_step"] = "Check the Client ID and Client Secret for the selected credentials"
    if details := ERROR_DETAILS.get(data.get("error_code")):
        data["error_reason"], data["next_step"] = details
    if explanation := REASON_DETAILS.get(data.get("reason")):
        data["reason_detail"] = explanation
    return data


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Deliberately omit exception text and tracebacks: upstream errors can contain credentials.
        return json.dumps(record_data(record), ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = record_data(record)
        prefix = f"{data.pop('time')} {data.pop('level'):<7} [{data.pop('logger')}]"
        if identifier := data.pop("request_id", None):
            prefix += f" request_id={identifier}"
        message = data.pop("message")
        fields = []
        for key, value in data.items():
            simple = isinstance(value, (int, float, bool)) or (
                isinstance(value, str) and value and not any(char.isspace() for char in value)
            )
            rendered = str(value) if simple else json.dumps(value, ensure_ascii=False)
            fields.append(f"{key}={rendered}")
        return f"{prefix} {message} | {' '.join(fields)}"


def configure_logging(log_format: str = "text", level: str = "INFO") -> None:
    logger = logging.getLogger("app")
    logger.setLevel(level)
    logger.propagate = False
    handler = next((item for item in logger.handlers if item.name == "app_console"), None)
    if handler is None:
        handler = logging.StreamHandler()
        handler.set_name("app_console")
        logger.addHandler(handler)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    logging.getLogger("ossapi").setLevel(logging.WARNING)
