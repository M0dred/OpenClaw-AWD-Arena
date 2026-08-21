import asyncio
import logging
import re
import shlex
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Optional

from agent_client import AgentClient, AgentSession, InitResult, MESSAGE_MODE_NORMAL

from .base import AgentBackendAdapter, BackendContainerSpec, BackendTargetSSHSpec, StreamCallback


logger = logging.getLogger(__name__)

CONTAINER_TIMEZONE = "Asia/Shanghai"
DEFAULT_HERMES_IMAGE = "openclaw/hermes-agent:latest"
HERMES_RUNTIME_VOLUME_PREFIX = "openclaw_hermes_runtime"
HERMES_HOME = "/opt/data"
HERMES_WRAPPER_ROOT = "/opt/runtime/hermes"
HERMES_WRAPPER_PY = f"{HERMES_WRAPPER_ROOT}/openclaw_wrapper.py"
HERMES_WRAPPER_SH = f"{HERMES_WRAPPER_ROOT}/openclaw"
HERMES_TARGET_SSH_KEY_PATH = f"{HERMES_HOME}/home/.ssh/awd_target_key"


class HermesAgentClient(AgentClient):
    HERMES_HOME = HERMES_HOME
    HERMES_SESSION_DIR = f"{HERMES_HOME}/sessions"
    INIT_PROMPT_TIMEOUT = 180

    def build_agent_exec_command(self, session: AgentSession, message_b64: str, timeout: int) -> str:
        wrapper = HERMES_WRAPPER_PY
        return (
            "sh -lc '"
            f"echo {message_b64} | base64 -d > /tmp/hermes_prompt.txt && "
            "if command -v python3 >/dev/null 2>&1; then PYTHON_BIN=python3; else PYTHON_BIN=python; fi && "
            f"\"$PYTHON_BIN\" {wrapper} agent --agent main -m \"$(cat /tmp/hermes_prompt.txt)\" --json --timeout {timeout}"
            "'"
        )

    async def _resolve_session_file(self, session: AgentSession) -> Optional[str]:
        session_file: Optional[str] = None

        if session.session_id:
            candidate_file = f"{self.HERMES_SESSION_DIR}/session_{session.session_id}.json"
            exists = await self._exec(
                session.container_name,
                f"test -f {candidate_file} && printf ok",
            )
            if exists.strip() == "ok":
                session_file = candidate_file
            else:
                logger.warning(
                    f"[Player {session.player_id}] Expected Hermes session log missing for session_id={session.session_id}; "
                    "falling back to latest session_*.json"
                )

        if session_file is None:
            result = await self._exec(
                session.container_name,
                f"sh -lc 'ls -t {self.HERMES_SESSION_DIR}/session_*.json 2>/dev/null | head -1'",
            )

            if not result.strip():
                return None

            session_file = result.strip()

        return session_file

    async def initialize_agent(
        self,
        session: AgentSession,
        system_prompt: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> InitResult:
        session.started_at = datetime.now()
        session.init_error_reason = None
        session.init_error_details = None

        response = await self.send_message(
            session,
            system_prompt,
            timeout=self.INIT_PROMPT_TIMEOUT,
            stream_callback=stream_callback,
            message_kind="init",
            message_mode=MESSAGE_MODE_NORMAL,
        )

        if response is None:
            logger.error(f"[Player {session.player_id}] No response to Hermes init prompt")
            session.init_error_reason = "INIT_PROMPT_NO_RESPONSE"
            session.init_error_details = "Hermes returned no response to the initialization prompt"
            return InitResult(False, session.init_error_reason, session.init_error_details)

        ready_result = self._classify_ready_response(response)
        if ready_result.success:
            session.ready = True
            return ready_result

        if "[HERMES_TIMEOUT]" in response:
            if await self.observe_session_activity(session):
                session.ready = True
                session.init_ready = True
                session.interactive_ready = True
                session.init_error_reason = None
                session.init_error_details = None
                return InitResult(
                    True,
                    "READY_INIT_SESSION_ACTIVITY",
                    "Hermes init timed out but session file activity confirms startup progress",
                )
            if await self.observe_code_activity(session):
                session.ready = True
                session.init_ready = True
                session.interactive_ready = True
                session.init_error_reason = None
                session.init_error_details = None
                return InitResult(
                    True,
                    "READY_INIT_CODE_ACTIVITY",
                    "Hermes init timed out but target code activity confirms startup progress",
                )

        logger.warning(
            f"[Player {session.player_id}] Hermes init response did not satisfy READY detection: {response[:200]}"
        )
        session.init_error_reason = ready_result.reason or "INIT_PROMPT_NO_READY"
        session.init_error_details = ready_result.details or response[:500]
        return InitResult(False, session.init_error_reason, session.init_error_details)


class HermesBackendAdapter(AgentBackendAdapter):
    backend_type = "hermes"

    @staticmethod
    def _sanitize_volume_component(value: Any) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "unknown")).strip("-.")
        return sanitized or "unknown"

    @classmethod
    def _resolve_runtime_volume_name(cls, match_config: Any, player_config: Any) -> str:
        match_id = cls._sanitize_volume_component(getattr(match_config, "match_id", None) or "unknown-match")
        player_id = cls._sanitize_volume_component(getattr(player_config, "id", None) or "unknown-player")
        return f"{HERMES_RUNTIME_VOLUME_PREFIX}_{match_id}_player_{player_id}"

    def build_agent_container_spec(self, match_config: Any, player_config: Any) -> BackendContainerSpec:
        config = getattr(match_config, "config", match_config)
        backend_config = getattr(player_config, "backend_config", None)
        image_override = getattr(backend_config, "image", None) if backend_config is not None else None
        extra_env = getattr(backend_config, "extra_env", None) if backend_config is not None else None
        llm_config = getattr(config, "llm", None)
        llm_api_key = getattr(player_config, "apiKey", None) or getattr(llm_config, "apiKey", "")
        llm_base_url = (getattr(player_config, "baseUrl", None) or "").strip() or getattr(
            llm_config, "baseUrl", ""
        )
        llm_model = getattr(player_config, "model", None) or getattr(llm_config, "model", "")
        llm_proxy = getattr(llm_config, "proxy", "")

        environment = {
            "OPENAI_API_KEY": llm_api_key,
            "OPENAI_BASE_URL": llm_base_url,
            "OPENAI_MODEL": llm_model,
            "HERMES_MODEL": llm_model,
            "HTTPS_PROXY": llm_proxy,
            "HTTP_PROXY": llm_proxy,
            "NO_PROXY": "localhost,127.0.0.1,172.16.0.0/12,10.0.0.0/8,host.docker.internal,.local",
            "TZ": CONTAINER_TIMEZONE,
            "HERMES_HOME": HERMES_HOME,
            "HOME": HERMES_HOME,
        }
        if isinstance(extra_env, dict):
            environment.update({str(key): str(value) for key, value in extra_env.items()})

        runtime_volume_name = self._resolve_runtime_volume_name(match_config, player_config)
        volumes = {
            runtime_volume_name: {"bind": HERMES_HOME, "mode": "rw"},
        }

        return BackendContainerSpec(
            image=image_override or DEFAULT_HERMES_IMAGE,
            environment=environment,
            entrypoint=["/bin/sh"],
            command=["-lc", "mkdir -p /opt/data/sessions /opt/data/logs /opt/data/home && sleep infinity"],
            volumes=volumes,
        )

    def create_client(self, match_config: Any, player_config: Any) -> HermesAgentClient:
        config = getattr(match_config, "config", match_config)
        llm_config = getattr(config, "llm", None)
        player_base_url = (getattr(player_config, "baseUrl", None) or "").strip()
        return HermesAgentClient(
            llm_api_key=getattr(player_config, "apiKey", None) or getattr(llm_config, "apiKey", ""),
            llm_base_url=player_base_url or getattr(llm_config, "baseUrl", ""),
            llm_model=getattr(player_config, "model", None) or getattr(llm_config, "model", "claude-sonnet-4-6"),
            proxy_url=getattr(llm_config, "proxy", "http://host.docker.internal:7897"),
        )

    def resolve_target_ssh_spec(self, match_config: Any, player_config: Any) -> BackendTargetSSHSpec:
        return BackendTargetSSHSpec(
            private_key_path=HERMES_TARGET_SSH_KEY_PATH,
            owner_user="hermes",
            owner_group="hermes",
            helper_path="/usr/local/bin/target-ssh",
        )

    async def initialize_agent(
        self,
        client: HermesAgentClient,
        session: Any,
        system_prompt: str,
        stream_callback: Optional[StreamCallback] = None,
    ) -> Any:
        return await client.initialize_agent(session, system_prompt, stream_callback=stream_callback)

    async def send_message(
        self,
        client: HermesAgentClient,
        session: Any,
        message: str,
        *,
        timeout: Optional[int] = None,
        stream_callback: Optional[StreamCallback] = None,
        message_kind: str = "message",
        message_mode: str = "normal",
        drain_buffered_after: bool = True,
    ) -> Optional[str]:
        return await client.send_message(
            session,
            message,
            timeout=timeout,
            stream_callback=stream_callback,
            message_kind=message_kind,
            message_mode=message_mode,
            drain_buffered_after=drain_buffered_after,
        )

    async def enqueue_buffered_message(
        self,
        client: HermesAgentClient,
        session: Any,
        message: str,
        *,
        message_kind: str,
        timeout: Optional[int] = None,
        stream_callback: Optional[StreamCallback] = None,
        dedupe_key: Optional[str] = None,
        merge_strategy: str = "replace",
        auto_drain: bool = True,
    ) -> str:
        return await client.enqueue_buffered_message(
            session,
            message,
            message_kind=message_kind,
            timeout=timeout,
            stream_callback=stream_callback,
            dedupe_key=dedupe_key,
            merge_strategy=merge_strategy,
            auto_drain=auto_drain,
        )

    async def drain_buffered_messages(self, client: HermesAgentClient, session: Any) -> int:
        return await client.drain_buffered_messages(session)

    def freeze_buffered_messages(self, client: HermesAgentClient, session: Any) -> None:
        client.freeze_buffered_messages(session)

    def unfreeze_buffered_messages(self, client: HermesAgentClient, session: Any) -> None:
        client.unfreeze_buffered_messages(session)

    def is_session_busy(self, client: HermesAgentClient, session: Any) -> bool:
        return client.is_session_busy(session)

    def has_buffered_message_kind(self, client: HermesAgentClient, session: Any, message_kind: str) -> bool:
        return client.has_buffered_message_kind(session, message_kind)

    async def observe_session_activity(self, client: HermesAgentClient, session: Any) -> bool:
        return await client.observe_session_activity(session)

    async def observe_code_activity(self, client: HermesAgentClient, session: Any) -> bool:
        return await client.observe_code_activity(session)

    async def check_session_contains(self, client: HermesAgentClient, session: Any, keyword: str, tail_lines: int = 50) -> bool:
        return await client.check_session_contains(session, keyword, tail_lines=tail_lines)

    async def collect_session_log(self, client: HermesAgentClient, session: Any) -> Optional[str]:
        return await client.get_session_log(session)

    async def cleanup(self, match: Any, player_id: int, session: Any, client: HermesAgentClient) -> None:
        volume_name = self._resolve_runtime_volume_name(match, SimpleNamespace(id=player_id))
        proc = await asyncio.create_subprocess_shell(
            f"docker volume rm {shlex.quote(volume_name)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(
                "[Player %s] Removed Hermes runtime volume: %s",
                player_id,
                volume_name,
            )
            return None

        stderr_text = (stderr.decode(errors="replace") if stderr else "").strip()
        stdout_text = (stdout.decode(errors="replace") if stdout else "").strip()
        detail = stderr_text or stdout_text or f"exit={proc.returncode}"
        logger.warning(
            "[Player %s] Failed to remove Hermes runtime volume %s: %s",
            player_id,
            volume_name,
            detail,
        )
        return None
