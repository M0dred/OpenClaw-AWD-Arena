from __future__ import annotations

import io
import json
import os
import posixpath
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import database


DIFF_KIND_TO_BUCKET = {
    0: "changed",
    1: "added",
    2: "deleted",
}

EXPORT_PROFILE_LEGACY = "legacy"
EXPORT_PROFILE_REPLAY = "replay"
DEFAULT_EXPORT_PROFILE = EXPORT_PROFILE_REPLAY
LEGACY_SCHEMA_VERSION = 1
REPLAY_SCHEMA_VERSION = 2
RESULT_STATUS_COMPLETE = "complete"
RESULT_STATUS_PARTIAL = "partial"
RESULT_STATUS_FAILED = "failed"

LEGACY_FILTER_REASON_DIRECTORY_PATH = "directory_path"
LEGACY_FILTER_REASON_EXCLUDED_PREFIX = "excluded_prefix"
LEGACY_FILTER_REASON_INVALID_PATH = "invalid_path"
LEGACY_FILTER_REASON_EXTENSION_NOT_ALLOWED = "extension_not_allowed"

FILTER_REASON_DIRECTORY_PATH = "directory_path"
FILTER_REASON_INVALID_PATH = "invalid_path"
FILTER_REASON_HARD_EXCLUDED_PREFIX = "hard_excluded_prefix"
FILTER_REASON_DEFAULT_EXCLUDED_PREFIX = "default_excluded_prefix"
FILTER_REASON_EXTENSION_NOT_ALLOWED = "extension_not_allowed"
FILTER_REASON_SENSITIVE_PATH = "sensitive_path"
FILTER_REASON_SENSITIVE_FILENAME = "sensitive_filename"
FILTER_REASON_SENSITIVE_SUFFIX = "sensitive_suffix"
FILTER_REASON_AGENT_SESSION_DUMP = "agent_session_dump"
FILTER_REASON_AGENT_CACHE = "agent_cache"
FILTER_REASON_AGENT_RUNTIME_ARTIFACT = "agent_runtime_artifact"
FILTER_REASON_BINARY_REVIEW_CANDIDATE = "binary_review_candidate"
FILTER_REASON_TEXT_NOT_REPLAY_MATERIAL = "text_not_replay_material"

CLASSIFICATION_REASON_HIGH_VALUE_PATH = "high_value_path"
CLASSIFICATION_REASON_NO_EXTENSION = "no_extension"
CLASSIFICATION_REASON_PATCH_LIKE_CONTENT = "patch_like_content"
CLASSIFICATION_REASON_TEXT_REVIEW_CANDIDATE = "text_review_candidate"

SKIP_REASON_SENSITIVE_CONTENT = "sensitive_content"
SKIP_REASON_REVIEW_CANDIDATE_LIMIT = "review_candidate_limit"
SKIP_REASON_SKIPPED_LARGE_FILE = "skipped_large_file"

LOG_MISSING_REASON_MISSING_OR_EMPTY = "missing_or_empty"

REPLAY_FILTER_REASONS = (
    FILTER_REASON_DIRECTORY_PATH,
    FILTER_REASON_INVALID_PATH,
    FILTER_REASON_HARD_EXCLUDED_PREFIX,
    FILTER_REASON_DEFAULT_EXCLUDED_PREFIX,
    FILTER_REASON_EXTENSION_NOT_ALLOWED,
    FILTER_REASON_SENSITIVE_PATH,
    FILTER_REASON_SENSITIVE_FILENAME,
    FILTER_REASON_SENSITIVE_SUFFIX,
    FILTER_REASON_AGENT_SESSION_DUMP,
    FILTER_REASON_AGENT_CACHE,
    FILTER_REASON_AGENT_RUNTIME_ARTIFACT,
    FILTER_REASON_BINARY_REVIEW_CANDIDATE,
    FILTER_REASON_TEXT_NOT_REPLAY_MATERIAL,
)
REPLAY_CLASSIFICATION_REASONS = (
    CLASSIFICATION_REASON_HIGH_VALUE_PATH,
    CLASSIFICATION_REASON_NO_EXTENSION,
    CLASSIFICATION_REASON_PATCH_LIKE_CONTENT,
    CLASSIFICATION_REASON_TEXT_REVIEW_CANDIDATE,
)
REPLAY_SKIP_REASONS = (
    SKIP_REASON_SENSITIVE_CONTENT,
    SKIP_REASON_REVIEW_CANDIDATE_LIMIT,
    SKIP_REASON_SKIPPED_LARGE_FILE,
)
LOG_MISSING_REASONS = (LOG_MISSING_REASON_MISSING_OR_EMPTY,)
REASON_ENUMS = {
    "filtered": list(REPLAY_FILTER_REASONS),
    "classification": list(REPLAY_CLASSIFICATION_REASONS),
    "skipped": list(REPLAY_SKIP_REASONS),
    "log_missing": list(LOG_MISSING_REASONS),
}

LEGACY_ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".php",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rs", ".lua", ".sh",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".conf", ".cfg", ".xml",
    ".sql", ".env", ".properties", ".html", ".css",
}

LEGACY_EXCLUDED_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/tmp",
    "/var/tmp",
    "/var/log",
    "/home/node/.openclaw",
)

ALLOWED_EXTENSIONS = LEGACY_ALLOWED_EXTENSIONS
EXCLUDED_PREFIXES = LEGACY_EXCLUDED_PREFIXES

CORE_CODE_EXTENSIONS = LEGACY_ALLOWED_EXTENSIONS
SUPPORTING_MATERIAL_EXTENSIONS = {
    ".txt",
    ".md",
    ".patch",
    ".diff",
    ".bak",
    ".backup",
}
CORE_CODE_FILENAMES = {"Dockerfile", "Makefile", "Procfile", "Gemfile", "Pipfile"}
ARTIFACT_BUCKETS = ("core_code", "supporting_materials", "review_candidates")
HARD_EXCLUDED_PREFIXES = (
    "/proc",
    "/sys",
    "/dev",
)
DEFAULT_EXCLUDED_PREFIXES = (
    "/run",
    "/var/log",
)
HIGH_VALUE_PREFIXES = (
    "/tmp",
    "/var/tmp",
    "/root",
    "/home",
    "/app",
)
HIGH_VALUE_KEYWORDS = (
    "attack",
    "defense",
    "defend",
    "exploit",
    "patch",
    "payload",
    "scan",
    "probe",
    "fix",
    "harden",
    "backup",
)
SOURCE_SPECIFIC_EXCLUDED_PREFIXES = {
    "agent": (
        ("/home/node/.openclaw/agents/main/sessions", FILTER_REASON_AGENT_SESSION_DUMP),
        ("/home/node/.openclaw/cache", FILTER_REASON_AGENT_CACHE),
        ("/home/node/.cache", FILTER_REASON_AGENT_CACHE),
        ("/tmp/jiti", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/tmp/node-compile-cache", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/tmp/openclaw", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/tmp/openclaw-*", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/agents", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/canvas", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/cron", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/devices", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/identity", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/logs", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/openclaw.json", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/update-check.json", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/.git", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/.openclaw", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/AGENTS.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/BOOTSTRAP.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/HEARTBEAT.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/IDENTITY.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/SOUL.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/TOOLS.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
        ("/home/node/.openclaw/workspace/USER.md", FILTER_REASON_AGENT_RUNTIME_ARTIFACT),
    ),
}
SENSITIVE_PATH_FRAGMENTS = (
    "/.ssh/",
    "/.aws/",
    "/.config/gcloud/",
    "/.kube/",
    "/.docker/",
    "/.gnupg/",
)
SENSITIVE_FILENAMES = {
    ".ssh",
    ".aws",
    ".docker",
    ".gnupg",
    ".kube",
    ".npmrc",
    ".openclaw",
    ".pypirc",
    ".git-credentials",
    ".netrc",
    "authorized_keys",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
SENSITIVE_FILTER_REASONS = {
    FILTER_REASON_SENSITIVE_PATH,
    FILTER_REASON_SENSITIVE_FILENAME,
    FILTER_REASON_SENSITIVE_SUFFIX,
    SKIP_REASON_SENSITIVE_CONTENT,
}
REDACTION_ELIGIBLE_SUFFIXES = {
    ".env",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".cfg",
    ".properties",
    ".txt",
    ".md",
    ".py",
    ".sh",
}
MAX_BYTES_BY_BUCKET = {
    "core_code": 5 * 1024 * 1024,
    "supporting_materials": 2 * 1024 * 1024,
    "review_candidates": 1 * 1024 * 1024,
}
MAX_REVIEW_CANDIDATES_PER_CONTAINER = 50
CONTENT_INSPECTION_MAX_BYTES = 256 * 1024
AGENT_SESSION_LOG_MAX_BYTES = 2 * 1024 * 1024

SCRIPT_CONTENT_PATTERN = re.compile(
    r"(^#!)|(^\s*(?:import\s+\w+|from\s+\w+\s+import|def\s+\w+\(|function\s+\w+\(|#!/bin/|#!/usr/bin/|echo\s+|set\s+-e))",
    re.MULTILINE,
)
CONFIG_CONTENT_PATTERN = re.compile(r"^\s*[A-Za-z0-9_.-]+\s*[:=]\s*\S+", re.MULTILINE)
PATCH_CONTENT_PATTERN = re.compile(r"(^diff --git )|(^--- )|(^\+\+\+ )|(^@@ )", re.MULTILINE)
BEARER_TOKEN_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]+\b", re.IGNORECASE)
COMMON_API_KEY_PATTERN = re.compile(
    r"\b(?:sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}|sk-ant-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"
)
SSHPASS_PASSWORD_PATTERN = re.compile(r"(?i)(sshpass\s+-p\s+)(['\"]?)([^'\"\s]+)(\2)")
PASSWORD_PROMPT_PATTERN = re.compile(r"(?im)(\bpassword(?:\s+for\s+[^\n:]+)?\s*[:=]\s*)(['\"]?)([^\"'\n]+)(\2)")
PLATFORM_TARGET_PASSWORD_PATTERN = re.compile(r"\bctf_target_\d+\b")
GENERIC_SECRET_PATTERN = re.compile(
    r"(?im)([\"']?\b[A-Za-z0-9_.-]*(?:api[_-]?key|token|secret|password)[A-Za-z0-9_.-]*\b[\"']?\s*[:=]\s*)([\"']?)([^\"',\n]+)(\2)"
)
PASSWORD_VARIABLE_PATTERN = re.compile(
    r"(?im)(\b(?:PASS|PASSWORD|PASSWD|PASSPHRASE|password|passwd|passphrase)\b\s*=\s*)(['\"])([^\"'\n]+)(\2)"
)
PRIVATE_KEY_BLOCK_PATTERN = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
FLAG_VALUE_PATTERN = re.compile(r"FLAG\{[A-Za-z0-9]{8,}\}")


def get_exports_root() -> Path:
    override = os.getenv("OPENCLAW_EXPORTS_PATH")
    if override:
        return Path(override)
    return Path(database.get_db_path()).resolve().parent / "exports"


def get_player_code_export_path(match_id: str) -> Path:
    return get_exports_root() / match_id / f"match_{match_id}_player_code_export.zip"


def get_player_code_export_profile() -> str:
    profile = str(os.getenv("OPENCLAW_PLAYER_EXPORT_PROFILE") or DEFAULT_EXPORT_PROFILE).strip().lower()
    if profile not in {EXPORT_PROFILE_LEGACY, EXPORT_PROFILE_REPLAY}:
        return DEFAULT_EXPORT_PROFILE
    return profile


def _normalize_export_path(path: str) -> str:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return posixpath.normpath(normalized)


def _matches_prefix(normalized_path: str, prefixes: Sequence[str]) -> bool:
    return any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
        for prefix in prefixes
    )


def _classify_exportable_path(path: str) -> Tuple[bool, Optional[str]]:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    if normalized.endswith("/"):
        return False, LEGACY_FILTER_REASON_DIRECTORY_PATH

    for prefix in EXCLUDED_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return False, LEGACY_FILTER_REASON_EXCLUDED_PREFIX

    basename = posixpath.basename(normalized)
    if not basename or basename in {".", ".."}:
        return False, LEGACY_FILTER_REASON_INVALID_PATH

    suffix = Path(basename).suffix.lower()
    if suffix in ALLOWED_EXTENSIONS or basename == ".env":
        return True, None
    return False, LEGACY_FILTER_REASON_EXTENSION_NOT_ALLOWED


def is_exportable_code_file(path: str, *, profile: Optional[str] = None, source_kind: str = "target") -> bool:
    active_profile = profile or get_player_code_export_profile()
    if active_profile == EXPORT_PROFILE_LEGACY:
        allowed, _ = _classify_exportable_path(path)
        return allowed
    classification = classify_export_artifact(path, source_kind)
    return classification.should_export and classification.bucket == "core_code"


def _relative_container_path(container_path: str) -> str:
    normalized = posixpath.normpath(container_path if container_path.startswith("/") else f"/{container_path}")
    relative = normalized.lstrip("/")
    if not relative:
        raise ValueError("Container path resolves to root")
    safe_parts = [part for part in relative.split("/") if part not in {"", ".", ".."}]
    if not safe_parts:
        raise ValueError(f"Invalid container path: {container_path}")
    return "/".join(safe_parts)


def _read_archive_bytes(stream: Any) -> bytes:
    buffer = io.BytesIO()
    for chunk in stream:
        buffer.write(chunk)
    return buffer.getvalue()


def _archive_mode_type(mode: Any) -> Optional[int]:
    if not isinstance(mode, int):
        return None
    mode_type = mode & 0o170000
    return mode_type or None


def _normalized_archive_member_name(member_name: str) -> str:
    normalized = member_name.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _archive_member_matches_path(member_name: str, container_path: str) -> bool:
    normalized_name = _normalized_archive_member_name(member_name)
    normalized_suffix = _relative_container_path(container_path)
    basename = posixpath.basename(container_path)
    return normalized_name == normalized_suffix or normalized_name == basename


def _archive_member_is_descendant(member_name: str, container_path: str) -> bool:
    normalized_name = _normalized_archive_member_name(member_name)
    normalized_suffix = _relative_container_path(container_path)
    return normalized_name.startswith(f"{normalized_suffix}/")


def _extract_file_bytes_from_archive(archive_bytes: bytes, container_path: str, stat_info: Optional[Dict[str, Any]] = None) -> bytes:
    mode_type = _archive_mode_type((stat_info or {}).get("mode"))
    if mode_type == 0o040000:
        raise IsADirectoryError(container_path)

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as tar:
        members = tar.getmembers()
        preferred = next(
            (member for member in members if member.isfile() and _archive_member_matches_path(member.name, container_path)),
            None,
        )
        if preferred is None:
            exact_member = next(
                (member for member in members if _archive_member_matches_path(member.name, container_path)),
                None,
            )
            if exact_member is not None and exact_member.isdir():
                raise IsADirectoryError(container_path)
            if any(_archive_member_is_descendant(member.name, container_path) for member in members):
                raise IsADirectoryError(container_path)
            raise FileNotFoundError(f"No regular file found in archive for {container_path}")

        extracted = tar.extractfile(preferred)
        if extracted is None:
            raise FileNotFoundError(f"Could not extract archive member for {container_path}")
        return extracted.read()


def read_file_from_container(container: Any, container_path: str) -> bytes:
    stream, stat_info = container.get_archive(container_path)
    archive_bytes = _read_archive_bytes(stream)
    return _extract_file_bytes_from_archive(archive_bytes, container_path, stat_info)


def copy_file_from_container(container: Any, container_path: str, output_path: Path) -> int:
    file_bytes = read_file_from_container(container, container_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(file_bytes)
    return len(file_bytes)


def _decode_text_bytes(file_bytes: bytes, *, limit: Optional[int] = None) -> Optional[str]:
    sample = file_bytes if limit is None else file_bytes[:limit]
    if b"\x00" in sample:
        return None
    for trim in range(0, min(4, len(sample)) + 1):
        candidate = sample if trim == 0 else sample[:-trim]
        if not candidate and sample:
            continue
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return None


def _path_has_high_value_keyword(path: str) -> bool:
    lowered = path.lower()
    return any(keyword in lowered for keyword in HIGH_VALUE_KEYWORDS)


def _is_sensitive_path(normalized_path: str) -> Tuple[bool, Optional[str]]:
    lowered = normalized_path.lower()
    if any(fragment in lowered for fragment in SENSITIVE_PATH_FRAGMENTS):
        return True, FILTER_REASON_SENSITIVE_PATH
    basename = posixpath.basename(lowered)
    if basename in SENSITIVE_FILENAMES:
        return True, FILTER_REASON_SENSITIVE_FILENAME
    if Path(basename).suffix.lower() in SENSITIVE_SUFFIXES:
        return True, FILTER_REASON_SENSITIVE_SUFFIX
    return False, None


def _get_source_specific_exclusion_reason(normalized_path: str, source_kind: str) -> Optional[str]:
    for prefix, reason in SOURCE_SPECIFIC_EXCLUDED_PREFIXES.get(source_kind, ()):
        if prefix.endswith("*"):
            if normalized_path.startswith(prefix[:-1]):
                return reason
            continue
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
            return reason
    return None


def _should_attempt_redaction(container_path: str) -> bool:
    normalized_path = _normalize_export_path(container_path).lower()
    basename = posixpath.basename(normalized_path)
    suffix = Path(basename).suffix.lower()
    if basename == ".env":
        return True
    if basename == ".openclaw":
        return True
    if any(token in basename for token in ("key", "token", "secret", "password")):
        return True
    if "/.openclaw/" in normalized_path and suffix in REDACTION_ELIGIBLE_SUFFIXES:
        return True
    return suffix in REDACTION_ELIGIBLE_SUFFIXES


def _redact_sensitive_text(text: str) -> Tuple[str, int]:
    redaction_count = 0

    def replace_private_key(_match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return "[REDACTED PRIVATE KEY BLOCK]"

    def replace_common_key(_match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return "[REDACTED]"

    def replace_bearer(_match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return "Bearer [REDACTED]"

    def replace_plain_secret(_match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return "[REDACTED]"

    def replace_secret_value(match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        prefix, opening_quote, _value, closing_quote = match.groups()
        if opening_quote or closing_quote:
            quote = opening_quote or closing_quote or '"'
            return f"{prefix}{quote}[REDACTED]{quote}"
        return f"{prefix}[REDACTED]"

    def replace_key_value(match: re.Match[str]) -> str:
        nonlocal redaction_count
        redaction_count += 1
        prefix, opening_quote, _value, closing_quote = match.groups()
        if opening_quote or closing_quote:
            quote = opening_quote or closing_quote or '"'
            return f"{prefix}{quote}[REDACTED]{quote}"
        return f"{prefix}[REDACTED]"

    redacted = PRIVATE_KEY_BLOCK_PATTERN.sub(replace_private_key, text)
    redacted = COMMON_API_KEY_PATTERN.sub(replace_common_key, redacted)
    redacted = BEARER_TOKEN_PATTERN.sub(replace_bearer, redacted)
    redacted = PLATFORM_TARGET_PASSWORD_PATTERN.sub(replace_plain_secret, redacted)
    redacted = SSHPASS_PASSWORD_PATTERN.sub(replace_secret_value, redacted)
    redacted = PASSWORD_PROMPT_PATTERN.sub(replace_secret_value, redacted)
    redacted = PASSWORD_VARIABLE_PATTERN.sub(replace_secret_value, redacted)
    redacted = GENERIC_SECRET_PATTERN.sub(replace_key_value, redacted)
    return redacted, redaction_count


def _redact_sensitive_log_text(text: str) -> Tuple[str, int]:
    redacted, redaction_count = _redact_sensitive_text(text)
    redacted, flag_count = FLAG_VALUE_PATTERN.subn("FLAG{[REDACTED]}", redacted)
    return redacted, redaction_count + flag_count


def _redact_sensitive_bytes(file_bytes: bytes) -> Tuple[bytes, int]:
    decoded = _decode_text_bytes(file_bytes)
    if decoded is None:
        return file_bytes, 0
    redacted_text, redaction_count = _redact_sensitive_text(decoded)
    redacted_text, flag_count = FLAG_VALUE_PATTERN.subn("FLAG{[REDACTED]}", redacted_text)
    total_redaction_count = redaction_count + flag_count
    if total_redaction_count == 0:
        return file_bytes, 0
    return redacted_text.encode("utf-8"), total_redaction_count


def _has_sensitive_file_content(file_bytes: bytes) -> bool:
    decoded = _decode_text_bytes(file_bytes, limit=CONTENT_INSPECTION_MAX_BYTES)
    if decoded is None:
        return False
    return bool(PRIVATE_KEY_BLOCK_PATTERN.search(decoded))


@dataclass
class PlayerDiffSummary:
    player_id: int
    player_name: str
    target_container: str
    added_files: List[Dict[str, Any]] = field(default_factory=list)
    changed_files: List[Dict[str, Any]] = field(default_factory=list)
    deleted_files: List[str] = field(default_factory=list)
    filtered_paths: List[Dict[str, str]] = field(default_factory=list)
    failed_files: List[Dict[str, str]] = field(default_factory=list)
    complete: bool = True

    def to_summary_json(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "target_container": self.target_container,
            "counts": {
                "added": len(self.added_files),
                "changed": len(self.changed_files),
                "deleted": len(self.deleted_files),
                "filtered": len(self.filtered_paths),
                "failed": len(self.failed_files),
            },
            "complete": self.complete,
            "added_files": self.added_files,
            "changed_files": self.changed_files,
            "deleted_files": self.deleted_files,
            "filtered_paths": self.filtered_paths,
            "failed_files": self.failed_files,
        }


@dataclass
class ArtifactClassification:
    should_export: bool
    bucket: Optional[str]
    reason: Optional[str] = None
    requires_content_inspection: bool = False
    requires_redaction: bool = False


@dataclass
class FileContentInspection:
    size_bytes: int
    is_text: bool
    has_shebang: bool = False
    looks_like_patch: bool = False
    looks_like_script: bool = False
    looks_like_config: bool = False


@dataclass
class ArtifactBucketSummary:
    added_files: List[Dict[str, Any]] = field(default_factory=list)
    changed_files: List[Dict[str, Any]] = field(default_factory=list)
    deleted_files: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, diff_kind: str, entry: Dict[str, Any]) -> None:
        if diff_kind == "added":
            self.added_files.append(entry)
        elif diff_kind == "changed":
            self.changed_files.append(entry)
        elif diff_kind == "deleted":
            self.deleted_files.append(entry)

    def counts(self) -> Dict[str, int]:
        return {
            "added": len(self.added_files),
            "changed": len(self.changed_files),
            "deleted": len(self.deleted_files),
        }

    def to_summary_json(self) -> Dict[str, Any]:
        return {
            "counts": self.counts(),
            "added_files": self.added_files,
            "changed_files": self.changed_files,
            "deleted_files": self.deleted_files,
        }


def _default_artifact_bucket_summaries() -> Dict[str, ArtifactBucketSummary]:
    return {bucket: ArtifactBucketSummary() for bucket in ARTIFACT_BUCKETS}


@dataclass
class ContainerExportSummary:
    source_kind: str
    container_name: str
    artifact_buckets: Dict[str, ArtifactBucketSummary] = field(default_factory=_default_artifact_bucket_summaries)
    filtered_paths: List[Dict[str, Any]] = field(default_factory=list)
    skipped_sensitive_files: List[Dict[str, Any]] = field(default_factory=list)
    skipped_large_files: List[Dict[str, Any]] = field(default_factory=list)
    skipped_limit_files: List[Dict[str, Any]] = field(default_factory=list)
    redacted_files: List[Dict[str, Any]] = field(default_factory=list)
    failed_files: List[Dict[str, Any]] = field(default_factory=list)
    complete: bool = True

    def bucket_summary(self, bucket: str) -> ArtifactBucketSummary:
        if bucket not in self.artifact_buckets:
            self.artifact_buckets[bucket] = ArtifactBucketSummary()
        return self.artifact_buckets[bucket]

    def record_filtered(self, entry: Dict[str, Any]) -> None:
        reason = str(entry.get("reason") or "filtered")
        if reason in SENSITIVE_FILTER_REASONS:
            self.skipped_sensitive_files.append(entry)
            return
        self.filtered_paths.append(entry)

    def counts(self) -> Dict[str, Any]:
        return {
            bucket: summary.counts()
            for bucket, summary in self.artifact_buckets.items()
        } | {
            "filtered": len(self.filtered_paths),
            "skipped_sensitive": len(self.skipped_sensitive_files),
            "skipped_large": len(self.skipped_large_files),
            "skipped_limit": len(self.skipped_limit_files),
            "redacted": len(self.redacted_files),
            "failed": len(self.failed_files),
        }

    def to_summary_json(self) -> Dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "container_name": self.container_name,
            "reason_enums": {
                "filtered": list(REPLAY_FILTER_REASONS),
                "classification": list(REPLAY_CLASSIFICATION_REASONS),
                "skipped": list(REPLAY_SKIP_REASONS),
            },
            "counts": self.counts(),
            "complete": self.complete,
            "artifact_buckets": {
                bucket: summary.to_summary_json()
                for bucket, summary in self.artifact_buckets.items()
            },
            "filtered_paths": self.filtered_paths,
            "skipped_sensitive_files": self.skipped_sensitive_files,
            "skipped_large_files": self.skipped_large_files,
            "skipped_limit_files": self.skipped_limit_files,
            "redacted_files": self.redacted_files,
            "failed_files": self.failed_files,
        }

    def to_event_summary(self) -> Dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "container_name": self.container_name,
            "complete": self.complete,
            "counts": self.counts(),
        }


@dataclass
class LogExportSummary:
    complete: bool = True
    available: bool = False
    path: Optional[str] = None
    size_bytes: int = 0
    redacted: bool = False
    redaction_count: int = 0
    truncated: bool = False
    missing_reason: Optional[str] = None
    error: Optional[str] = None

    def to_summary_json(self) -> Dict[str, Any]:
        return {
            "reason_enums": {
                "missing": list(LOG_MISSING_REASONS),
            },
            "complete": self.complete,
            "available": self.available,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "redacted": self.redacted,
            "redaction_count": self.redaction_count,
            "truncated": self.truncated,
            "missing_reason": self.missing_reason,
            "error": self.error,
        }

    def to_event_summary(self) -> Dict[str, Any]:
        return self.to_summary_json()


@dataclass
class PlayerReplayExportSummary:
    player_id: int
    player_name: str
    target_container: str
    agent_container: str
    target: ContainerExportSummary
    agent: ContainerExportSummary
    logs: LogExportSummary

    @property
    def complete(self) -> bool:
        return self.target.complete and self.agent.complete and self.logs.complete

    @property
    def incomplete_sections(self) -> List[str]:
        sections: List[str] = []
        if not self.target.complete:
            sections.append("target")
        if not self.agent.complete:
            sections.append("agent")
        if not self.logs.complete:
            sections.append("logs")
        return sections

    def to_summary_json(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "target_container": self.target_container,
            "agent_container": self.agent_container,
            "complete": self.complete,
            "target": self.target.to_summary_json(),
            "agent": self.agent.to_summary_json(),
            "logs": self.logs.to_summary_json(),
        }

    def to_event_summary(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "target_container": self.target_container,
            "agent_container": self.agent_container,
            "complete": self.complete,
            "result_status": RESULT_STATUS_COMPLETE if self.complete else RESULT_STATUS_PARTIAL,
            "incomplete_sections": self.incomplete_sections,
            "target": self.target.to_event_summary(),
            "agent": self.agent.to_event_summary(),
            "logs": self.logs.to_event_summary(),
        }


def _schema_version_for_profile(export_profile: str) -> int:
    if export_profile == EXPORT_PROFILE_REPLAY:
        return REPLAY_SCHEMA_VERSION
    return LEGACY_SCHEMA_VERSION


def _legacy_incomplete_sections(player: PlayerDiffSummary) -> List[str]:
    return [] if player.complete else ["target"]


def _incomplete_player_summary(player: Any, export_profile: str) -> Optional[Dict[str, Any]]:
    if export_profile == EXPORT_PROFILE_REPLAY and isinstance(player, PlayerReplayExportSummary):
        sections = player.incomplete_sections
        if not sections:
            return None
        return {
            "player_id": player.player_id,
            "player_name": player.player_name,
            "incomplete_sections": sections,
        }

    if isinstance(player, PlayerDiffSummary):
        sections = _legacy_incomplete_sections(player)
        if not sections:
            return None
        return {
            "player_id": player.player_id,
            "player_name": player.player_name,
            "incomplete_sections": sections,
        }

    return None


def build_failed_export_payload(
    match_id: str,
    error: str,
    *,
    generated_at: Optional[str] = None,
    failure_stage: str = "export_generation",
    export_profile: Optional[str] = None,
) -> Dict[str, Any]:
    profile = export_profile or get_player_code_export_profile()
    export_path = get_player_code_export_path(match_id)
    return {
        "status": "failed",
        "result_status": RESULT_STATUS_FAILED,
        "bundle_available": False,
        "partial": False,
        "match_id": match_id,
        "bundle_path": str(export_path),
        "bundle_filename": export_path.name,
        "generated_at": generated_at or datetime.now().isoformat(),
        "complete": False,
        "schema_version": _schema_version_for_profile(profile),
        "export_profile": profile,
        "failure_stage": failure_stage,
        "error": error,
        "players": [],
        "incomplete_player_count": 0,
        "incomplete_players": [],
    }


@dataclass
class ExportResult:
    match_id: str
    bundle_path: str
    bundle_filename: str
    generated_at: str
    players: List[Any]
    complete: bool
    schema_version: int = LEGACY_SCHEMA_VERSION
    export_profile: str = EXPORT_PROFILE_LEGACY

    def to_event_payload(self) -> Dict[str, Any]:
        incomplete_players = [
            item
            for item in (
                _incomplete_player_summary(player, self.export_profile)
                for player in self.players
            )
            if item is not None
        ]
        payload: Dict[str, Any] = {
            "status": "ready",
            "result_status": RESULT_STATUS_COMPLETE if self.complete else RESULT_STATUS_PARTIAL,
            "bundle_available": True,
            "partial": not self.complete,
            "match_id": self.match_id,
            "bundle_path": self.bundle_path,
            "bundle_filename": self.bundle_filename,
            "generated_at": self.generated_at,
            "complete": self.complete,
            "schema_version": self.schema_version,
            "export_profile": self.export_profile,
            "incomplete_player_count": len(incomplete_players),
            "incomplete_players": incomplete_players,
        }
        if self.export_profile == EXPORT_PROFILE_REPLAY:
            payload["players"] = [player.to_event_summary() for player in self.players]
            return payload
        payload["players"] = [
            {
                "player_id": player.player_id,
                "player_name": player.player_name,
                "target_container": player.target_container,
                "counts": player.to_summary_json()["counts"],
                "complete": player.complete,
                "result_status": RESULT_STATUS_COMPLETE if player.complete else RESULT_STATUS_PARTIAL,
                "incomplete_sections": _legacy_incomplete_sections(player),
            }
            for player in self.players
        ]
        return payload


def classify_export_artifact(path: str, source_kind: str) -> ArtifactClassification:
    normalized = path.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    if normalized.endswith("/"):
        return ArtifactClassification(False, None, FILTER_REASON_DIRECTORY_PATH)

    normalized = _normalize_export_path(normalized)
    basename = posixpath.basename(normalized)
    if not basename or basename in {".", ".."}:
        return ArtifactClassification(False, None, FILTER_REASON_INVALID_PATH)

    requires_redaction = _should_attempt_redaction(normalized)

    if _matches_prefix(normalized, HARD_EXCLUDED_PREFIXES):
        return ArtifactClassification(False, None, FILTER_REASON_HARD_EXCLUDED_PREFIX)

    if _matches_prefix(normalized, DEFAULT_EXCLUDED_PREFIXES):
        return ArtifactClassification(False, None, FILTER_REASON_DEFAULT_EXCLUDED_PREFIX)

    source_specific_reason = _get_source_specific_exclusion_reason(normalized, source_kind)
    if source_specific_reason:
        return ArtifactClassification(False, None, source_specific_reason)

    is_sensitive, sensitive_reason = _is_sensitive_path(normalized)
    if is_sensitive:
        return ArtifactClassification(False, None, sensitive_reason)

    suffixes = [suffix.lower() for suffix in Path(basename).suffixes]
    final_suffix = suffixes[-1] if suffixes else ""

    if basename == ".env" or basename in CORE_CODE_FILENAMES or final_suffix in CORE_CODE_EXTENSIONS:
        return ArtifactClassification(True, "core_code", requires_redaction=requires_redaction)

    if final_suffix in SUPPORTING_MATERIAL_EXTENSIONS:
        return ArtifactClassification(True, "supporting_materials", requires_redaction=requires_redaction)

    if final_suffix:
        if _matches_prefix(normalized, HIGH_VALUE_PREFIXES) or _path_has_high_value_keyword(normalized):
            return ArtifactClassification(
                True,
                "review_candidates",
                CLASSIFICATION_REASON_HIGH_VALUE_PATH,
                True,
                requires_redaction,
            )
        return ArtifactClassification(False, None, FILTER_REASON_EXTENSION_NOT_ALLOWED)

    if _matches_prefix(normalized, HIGH_VALUE_PREFIXES) or _path_has_high_value_keyword(normalized):
        return ArtifactClassification(
            True,
            "review_candidates",
            CLASSIFICATION_REASON_NO_EXTENSION,
            True,
            requires_redaction,
        )

    return ArtifactClassification(False, None, FILTER_REASON_EXTENSION_NOT_ALLOWED)


def inspect_file_content(container: Any, path: str) -> FileContentInspection:
    file_bytes = read_file_from_container(container, path)
    text = _decode_text_bytes(file_bytes, limit=CONTENT_INSPECTION_MAX_BYTES)
    if text is None:
        return FileContentInspection(size_bytes=len(file_bytes), is_text=False)

    first_line = text.splitlines()[0] if text.splitlines() else ""
    return FileContentInspection(
        size_bytes=len(file_bytes),
        is_text=True,
        has_shebang=first_line.startswith("#!"),
        looks_like_patch=bool(PATCH_CONTENT_PATTERN.search(text)),
        looks_like_script=bool(SCRIPT_CONTENT_PATTERN.search(text)),
        looks_like_config=bool(CONFIG_CONTENT_PATTERN.search(text)),
    )


def _refine_artifact_classification(
    container_path: str,
    classification: ArtifactClassification,
    inspection: FileContentInspection,
) -> ArtifactClassification:
    if not classification.should_export or not classification.requires_content_inspection:
        return classification

    if not inspection.is_text:
        return ArtifactClassification(
            False,
            None,
            FILTER_REASON_BINARY_REVIEW_CANDIDATE,
            requires_redaction=classification.requires_redaction,
        )

    if inspection.looks_like_patch:
        return ArtifactClassification(
            True,
            "supporting_materials",
            CLASSIFICATION_REASON_PATCH_LIKE_CONTENT,
            requires_redaction=classification.requires_redaction,
        )

    if inspection.has_shebang or inspection.looks_like_script or inspection.looks_like_config:
        return ArtifactClassification(
            True,
            "review_candidates",
            classification.reason or CLASSIFICATION_REASON_TEXT_REVIEW_CANDIDATE,
            requires_redaction=classification.requires_redaction,
        )

    if _matches_prefix(_normalize_export_path(container_path), HIGH_VALUE_PREFIXES) or _path_has_high_value_keyword(container_path):
        return ArtifactClassification(
            True,
            "review_candidates",
            CLASSIFICATION_REASON_TEXT_REVIEW_CANDIDATE,
            requires_redaction=classification.requires_redaction,
        )

    return ArtifactClassification(
        False,
        None,
        FILTER_REASON_TEXT_NOT_REPLAY_MATERIAL,
        requires_redaction=classification.requires_redaction,
    )


def collect_target_container_changes(container: Any) -> Dict[str, List[Dict[str, str]]]:
    collected: Dict[str, List[Dict[str, str]]] = {
        "added": [],
        "changed": [],
        "deleted": [],
        "filtered": [],
    }
    for raw_entry in container.diff():
        path = str(raw_entry.get("Path") or "")
        bucket = DIFF_KIND_TO_BUCKET.get(raw_entry.get("Kind"))
        if not path or bucket is None:
            continue

        allowed, reason = _classify_exportable_path(path)
        if not allowed:
            collected["filtered"].append({"path": path, "reason": reason or "filtered"})
            continue

        collected[bucket].append({"path": path})
    return collected


def collect_container_changes(container: Any, source_kind: str) -> Dict[str, List[Dict[str, Any]]]:
    collected: Dict[str, List[Dict[str, Any]]] = {
        "added": [],
        "changed": [],
        "deleted": [],
        "filtered": [],
        "failed": [],
    }
    for raw_entry in container.diff():
        path = str(raw_entry.get("Path") or "")
        diff_kind = DIFF_KIND_TO_BUCKET.get(raw_entry.get("Kind"))
        if not path or diff_kind is None:
            continue

        classification = classify_export_artifact(path, source_kind)
        if not classification.should_export:
            collected["filtered"].append({"path": path, "reason": classification.reason or "filtered"})
            continue

        if classification.requires_content_inspection and diff_kind != "deleted":
            try:
                inspection = inspect_file_content(container, path)
                classification = _refine_artifact_classification(path, classification, inspection)
            except IsADirectoryError:
                collected["filtered"].append({"path": path, "reason": FILTER_REASON_DIRECTORY_PATH})
                continue
            except Exception as exc:
                collected["failed"].append({
                    "path": path,
                    "error": f"failed to inspect file content: {exc}",
                })
                continue

            if not classification.should_export:
                collected["filtered"].append({"path": path, "reason": classification.reason or "filtered"})
                continue

        collected[diff_kind].append({
            "path": path,
            "bucket": classification.bucket,
            "reason": classification.reason,
            "requires_redaction": classification.requires_redaction,
        })
    return collected


def _player_name_map(match: Any) -> Dict[int, str]:
    players = getattr(getattr(match, "config", None), "players", []) or []
    mapping: Dict[int, str] = {}
    for player in players:
        player_id = getattr(player, "id", None)
        if isinstance(player_id, int):
            mapping[player_id] = str(getattr(player, "name", f"P{player_id}"))
    return mapping


def _zip_directory(source_dir: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(source_dir).as_posix())


def _write_json_file(output_path: Path, data: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_container_artifacts(
    container: Any,
    player_dir: Path,
    source_kind: str,
    container_name: str,
) -> ContainerExportSummary:
    summary = ContainerExportSummary(source_kind=source_kind, container_name=container_name)
    container_dir = player_dir / source_kind
    container_dir.mkdir(parents=True, exist_ok=True)

    changes = collect_container_changes(container, source_kind)
    for filtered in changes["filtered"]:
        summary.record_filtered(filtered)
    for failed in changes["failed"]:
        summary.complete = False
        summary.failed_files.append(failed)

    for deleted in changes["deleted"]:
        bucket = str(deleted.get("bucket") or "review_candidates")
        summary.bucket_summary(bucket).add(
            "deleted",
            {
                "path": deleted["path"],
                "reason": deleted.get("reason"),
            },
        )

    review_candidates_written = 0
    for diff_kind in ("added", "changed"):
        for entry in changes[diff_kind]:
            container_path = str(entry["path"])
            bucket = str(entry.get("bucket") or "review_candidates")
            relative_path = _relative_container_path(container_path)

            if bucket == "review_candidates" and review_candidates_written >= MAX_REVIEW_CANDIDATES_PER_CONTAINER:
                summary.skipped_limit_files.append(
                    {
                        "path": container_path,
                        "relative_path": relative_path,
                        "bucket": bucket,
                        "limit": MAX_REVIEW_CANDIDATES_PER_CONTAINER,
                        "reason": SKIP_REASON_REVIEW_CANDIDATE_LIMIT,
                    }
                )
                continue

            try:
                file_bytes = read_file_from_container(container, container_path)
                original_size = len(file_bytes)

                if _has_sensitive_file_content(file_bytes):
                    summary.skipped_sensitive_files.append(
                        {
                            "path": container_path,
                            "relative_path": relative_path,
                            "bucket": bucket,
                            "reason": SKIP_REASON_SENSITIVE_CONTENT,
                        }
                    )
                    continue

                size_limit = MAX_BYTES_BY_BUCKET.get(bucket, MAX_BYTES_BY_BUCKET["review_candidates"])
                if original_size > size_limit:
                    summary.skipped_large_files.append(
                        {
                            "path": container_path,
                            "relative_path": relative_path,
                            "bucket": bucket,
                            "size_bytes": original_size,
                            "size_limit_bytes": size_limit,
                            "reason": SKIP_REASON_SKIPPED_LARGE_FILE,
                        }
                    )
                    continue

                output_bytes = file_bytes
                redaction_count = 0
                if bucket == "review_candidates" or bool(entry.get("requires_redaction")) or _should_attempt_redaction(container_path):
                    output_bytes, redaction_count = _redact_sensitive_bytes(file_bytes)
                    if redaction_count > 0:
                        summary.redacted_files.append(
                            {
                                "path": container_path,
                                "relative_path": relative_path,
                                "bucket": bucket,
                                "redaction_count": redaction_count,
                            }
                        )

                output_path = container_dir / bucket / diff_kind / Path(relative_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(output_bytes)

                summary.bucket_summary(bucket).add(
                    diff_kind,
                    {
                        "path": container_path,
                        "relative_path": relative_path,
                        "size_bytes": len(output_bytes),
                        "original_size_bytes": original_size,
                        "redacted": redaction_count > 0,
                        "redaction_count": redaction_count,
                    },
                )
                if bucket == "review_candidates":
                    review_candidates_written += 1
            except IsADirectoryError:
                summary.record_filtered(
                    {
                        "path": container_path,
                        "relative_path": relative_path,
                        "bucket": bucket,
                        "reason": FILTER_REASON_DIRECTORY_PATH,
                    }
                )
            except Exception as exc:
                summary.complete = False
                summary.failed_files.append(
                    {
                        "path": container_path,
                        "bucket": bucket,
                        "error": str(exc),
                    }
                )

    _write_json_file(container_dir / "summary.json", summary.to_summary_json())
    return summary


def write_agent_session_log(match: Any, player_id: int, player_dir: Path) -> LogExportSummary:
    logs_dir = player_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    summary = LogExportSummary(path="logs/agent_session.log")

    try:
        player_logs = getattr(match, "agent_logs", {}) or {}
        log_content = player_logs.get(player_id)
        if not isinstance(log_content, str) or not log_content:
            placeholder = "(no agent session log available)\n"
            (logs_dir / "agent_session.log").write_text(placeholder, encoding="utf-8")
            summary.size_bytes = len(placeholder.encode("utf-8"))
            summary.missing_reason = LOG_MISSING_REASON_MISSING_OR_EMPTY
            return summary

        redacted_text, redaction_count = _redact_sensitive_log_text(log_content)
        output_text = redacted_text
        encoded = output_text.encode("utf-8")
        if len(encoded) > AGENT_SESSION_LOG_MAX_BYTES:
            marker = "\n...[TRUNCATED]\n"
            marker_bytes = marker.encode("utf-8")
            allowed_bytes = max(0, AGENT_SESSION_LOG_MAX_BYTES - len(marker_bytes))
            output_text = encoded[:allowed_bytes].decode("utf-8", errors="ignore") + marker
            encoded = output_text.encode("utf-8")
            summary.truncated = True

        (logs_dir / "agent_session.log").write_bytes(encoded)
        summary.available = True
        summary.size_bytes = len(encoded)
        summary.redacted = redaction_count > 0
        summary.redaction_count = redaction_count
        return summary
    except Exception as exc:
        summary.complete = False
        summary.error = str(exc)
        return summary


def build_manifest(match: Any, generated_at: str, players_summary: List[Any], export_profile: str) -> Dict[str, Any]:
    if export_profile == EXPORT_PROFILE_LEGACY:
        return {
            "match_id": match.match_id,
            "generated_at": generated_at,
            "complete": all(player.complete for player in players_summary),
            "schema_version": LEGACY_SCHEMA_VERSION,
            "export_profile": EXPORT_PROFILE_LEGACY,
            "filters": {
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
                "excluded_prefixes": list(EXCLUDED_PREFIXES),
            },
            "players": [player.to_summary_json() for player in players_summary],
        }

    return {
        "match_id": match.match_id,
        "generated_at": generated_at,
        "complete": all(player.complete for player in players_summary),
        "schema_version": REPLAY_SCHEMA_VERSION,
        "export_profile": EXPORT_PROFILE_REPLAY,
        "filters": {
            "core_code_extensions": sorted(CORE_CODE_EXTENSIONS),
            "supporting_material_extensions": sorted(SUPPORTING_MATERIAL_EXTENSIONS),
            "core_code_filenames": sorted(CORE_CODE_FILENAMES),
            "hard_excluded_prefixes": list(HARD_EXCLUDED_PREFIXES),
            "default_excluded_prefixes": list(DEFAULT_EXCLUDED_PREFIXES),
            "sensitive_path_fragments": list(SENSITIVE_PATH_FRAGMENTS),
            "sensitive_filenames": sorted(SENSITIVE_FILENAMES),
            "sensitive_suffixes": sorted(SENSITIVE_SUFFIXES),
            "reason_enums": REASON_ENUMS,
            "source_specific_exclusions": {
                source_kind: [
                    {"prefix": prefix, "reason": reason}
                    for prefix, reason in entries
                ]
                for source_kind, entries in SOURCE_SPECIFIC_EXCLUDED_PREFIXES.items()
            },
            "size_limits": MAX_BYTES_BY_BUCKET,
            "max_review_candidates_per_container": MAX_REVIEW_CANDIDATES_PER_CONTAINER,
            "agent_session_log_max_bytes": AGENT_SESSION_LOG_MAX_BYTES,
        },
        "players": [player.to_summary_json() for player in players_summary],
    }


def _export_match_player_code_legacy(match: Any) -> ExportResult:
    import docker

    generated_at = datetime.now().isoformat()
    export_path = get_player_code_export_path(match.match_id)
    export_dir = export_path.parent
    export_dir.mkdir(parents=True, exist_ok=True)

    player_names = _player_name_map(match)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{match.match_id}_player_code_", dir=str(export_dir)))
    players_summary: List[PlayerDiffSummary] = []

    try:
        client = docker.from_env()

        for player_id in sorted(getattr(match, "players", {}).keys()):
            player = match.players[player_id]
            summary = PlayerDiffSummary(
                player_id=player_id,
                player_name=player_names.get(player_id, f"P{player_id}"),
                target_container=player.target_container,
            )
            player_dir = temp_dir / f"player_{player_id}"

            try:
                container = client.containers.get(player.target_container)
                changes = collect_target_container_changes(container)

                for filtered in changes["filtered"]:
                    summary.filtered_paths.append(filtered)

                for deleted in changes["deleted"]:
                    summary.deleted_files.append(deleted["path"])

                for bucket in ("added", "changed"):
                    for entry in changes[bucket]:
                        container_path = entry["path"]
                        try:
                            relative_path = _relative_container_path(container_path)
                            output_path = player_dir / bucket / Path(relative_path)
                            size_bytes = copy_file_from_container(container, container_path, output_path)
                            target_list = summary.added_files if bucket == "added" else summary.changed_files
                            target_list.append(
                                {
                                    "path": container_path,
                                    "relative_path": relative_path,
                                    "size_bytes": size_bytes,
                                }
                            )
                        except Exception as exc:
                            summary.complete = False
                            summary.failed_files.append({"path": container_path, "error": str(exc)})
            except Exception as exc:
                summary.complete = False
                summary.failed_files.append({
                    "path": player.target_container,
                    "error": f"failed to inspect target container: {exc}",
                })

            player_dir.mkdir(parents=True, exist_ok=True)
            _write_json_file(player_dir / "summary.json", summary.to_summary_json())
            players_summary.append(summary)

        manifest = build_manifest(match, generated_at, players_summary, EXPORT_PROFILE_LEGACY)
        _write_json_file(temp_dir / "manifest.json", manifest)

        temp_zip = export_path.with_suffix(".zip.tmp")
        _zip_directory(temp_dir, temp_zip)
        os.replace(temp_zip, export_path)

        return ExportResult(
            match_id=match.match_id,
            bundle_path=str(export_path),
            bundle_filename=export_path.name,
            generated_at=generated_at,
            players=players_summary,
            complete=all(player.complete for player in players_summary),
            schema_version=LEGACY_SCHEMA_VERSION,
            export_profile=EXPORT_PROFILE_LEGACY,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _export_match_player_code_replay(match: Any) -> ExportResult:
    import docker

    generated_at = datetime.now().isoformat()
    export_path = get_player_code_export_path(match.match_id)
    export_dir = export_path.parent
    export_dir.mkdir(parents=True, exist_ok=True)

    player_names = _player_name_map(match)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{match.match_id}_player_replay_export_", dir=str(export_dir)))
    players_summary: List[PlayerReplayExportSummary] = []

    try:
        client = docker.from_env()

        for player_id in sorted(getattr(match, "players", {}).keys()):
            player = match.players[player_id]
            player_dir = temp_dir / f"player_{player_id}"
            player_dir.mkdir(parents=True, exist_ok=True)

            target_summary = ContainerExportSummary(
                source_kind="target",
                container_name=str(player.target_container),
            )
            agent_summary = ContainerExportSummary(
                source_kind="agent",
                container_name=str(player.container_name),
            )

            try:
                target_container = client.containers.get(player.target_container)
                target_summary = export_container_artifacts(
                    target_container,
                    player_dir,
                    "target",
                    str(player.target_container),
                )
            except Exception as exc:
                target_summary.complete = False
                target_summary.failed_files.append(
                    {
                        "path": str(player.target_container),
                        "error": f"failed to inspect target container: {exc}",
                    }
                )
                _write_json_file(player_dir / "target" / "summary.json", target_summary.to_summary_json())

            try:
                agent_container = client.containers.get(player.container_name)
                agent_summary = export_container_artifacts(
                    agent_container,
                    player_dir,
                    "agent",
                    str(player.container_name),
                )
            except Exception as exc:
                agent_summary.complete = False
                agent_summary.failed_files.append(
                    {
                        "path": str(player.container_name),
                        "error": f"failed to inspect agent container: {exc}",
                    }
                )
                _write_json_file(player_dir / "agent" / "summary.json", agent_summary.to_summary_json())

            logs_summary = write_agent_session_log(match, player_id, player_dir)
            player_summary = PlayerReplayExportSummary(
                player_id=player_id,
                player_name=player_names.get(player_id, f"P{player_id}"),
                target_container=str(player.target_container),
                agent_container=str(player.container_name),
                target=target_summary,
                agent=agent_summary,
                logs=logs_summary,
            )
            _write_json_file(player_dir / "player_summary.json", player_summary.to_summary_json())
            players_summary.append(player_summary)

        manifest = build_manifest(match, generated_at, players_summary, EXPORT_PROFILE_REPLAY)
        _write_json_file(temp_dir / "manifest.json", manifest)

        temp_zip = export_path.with_suffix(".zip.tmp")
        _zip_directory(temp_dir, temp_zip)
        os.replace(temp_zip, export_path)

        return ExportResult(
            match_id=match.match_id,
            bundle_path=str(export_path),
            bundle_filename=export_path.name,
            generated_at=generated_at,
            players=players_summary,
            complete=all(player.complete for player in players_summary),
            schema_version=REPLAY_SCHEMA_VERSION,
            export_profile=EXPORT_PROFILE_REPLAY,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def export_match_player_code(match: Any) -> ExportResult:
    if get_player_code_export_profile() == EXPORT_PROFILE_REPLAY:
        return _export_match_player_code_replay(match)
    return _export_match_player_code_legacy(match)
