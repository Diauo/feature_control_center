from __future__ import annotations

import hmac
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.audit import RequestMetadata, add_audit
from app.application.errors import AuthenticationError
from app.application.settings import SettingsService
from app.domain.identity import UserRole, normalize_username
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.models import LoginRateLimitModel, SessionModel, UserModel
from app.security.crypto import derive_key, digest_value, generate_opaque_token, user_agent_digest
from app.security.passwords import PasswordService


@dataclass(frozen=True, slots=True)
class AuthContext:
    session_id: str
    user_id: str
    username: str
    display_name: str
    role: UserRole
    must_change_password: bool
    csrf_token: str
    reauthenticated_at: int | None


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    csrf_token: str
    absolute_expires_at: int
    context: AuthContext


class AuthService:
    _RATE_WINDOW_SECONDS = 900
    _TOUCH_INTERVAL_SECONDS = 300

    def __init__(
        self,
        database: Database,
        settings: SettingsService,
        passwords: PasswordService,
        clock: Clock,
        instance_key: bytes,
    ) -> None:
        self.database = database
        self.settings = settings
        self.passwords = passwords
        self.clock = clock
        self._session_digest_key = derive_key(instance_key, b"session-token")
        self._rate_limit_key = derive_key(instance_key, b"login-rate")

    def login(
        self,
        *,
        username: str,
        password: str,
        request: RequestMetadata,
    ) -> IssuedSession:
        try:
            username_normalized = normalize_username(username)
        except ValueError:
            username_normalized = username.strip().casefold()[:64]
        now = self.clock.now()
        rate_keys = self._rate_keys(username_normalized, request.client_ip)
        failure: AuthenticationError | None = None
        issued: IssuedSession | None = None

        with self.database.session() as db:
            retry_after = self._retry_after(db, rate_keys, now)
            if retry_after > 0:
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="auth.login",
                    outcome="blocked",
                    details={"reason": "rate_limited"},
                )
                failure = AuthenticationError(
                    "LOGIN_RATE_LIMITED",
                    "登录尝试过于频繁，请稍后再试",
                    status=429,
                    details={"retryAfterSeconds": retry_after},
                )
            else:
                user = db.scalar(select(UserModel).where(UserModel.username_normalized == username_normalized))
                valid = False
                if user is None or not user.is_active:
                    self.passwords.verify_unknown_user(password)
                else:
                    valid = self.passwords.verify(user.password_hash, password)

                if not valid or user is None:
                    self._record_failure(db, rate_keys, now)
                    add_audit(
                        db,
                        now=now,
                        request=request,
                        action="auth.login",
                        outcome="denied",
                        target_type="user",
                        target_id=user.id if user is not None else None,
                        details={"reason": "invalid_credentials"},
                    )
                    failure = AuthenticationError("INVALID_CREDENTIALS", "账号或密码错误", status=401)
                else:
                    if self.passwords.needs_rehash(user.password_hash):
                        user.password_hash = self.passwords.hash(password)
                    user.last_login_at = now
                    user.updated_at = now
                    self._clear_rate_limits(db, rate_keys)
                    issued = self._issue_session(db, user, request, now, reauthenticated=True)
                    add_audit(
                        db,
                        now=now,
                        request=request,
                        action="auth.login",
                        outcome="success",
                        actor_user_id=user.id,
                        session_id=issued.context.session_id,
                    )

        if failure is not None:
            raise failure
        if issued is None:
            raise AuthenticationError("LOGIN_FAILED", "登录失败", status=401)
        return issued

    def authenticate(self, token: str | None) -> AuthContext | None:
        if not token:
            return None
        digest = digest_value(self._session_digest_key, token)
        now = self.clock.now()
        result: AuthContext | None = None
        with self.database.session() as db:
            session = db.scalar(select(SessionModel).where(SessionModel.token_digest == digest))
            if session is None or session.revoked_at is not None:
                return None
            user = session.user
            expired = session.idle_expires_at <= now or session.absolute_expires_at <= now
            invalid_user = not user.is_active or session.user_security_version != user.security_version
            if expired or invalid_user:
                session.revoked_at = now
                session.revoked_reason = "expired" if expired else "security_changed"
                return None

            settings = self.settings.security()
            if now - session.last_seen_at >= self._TOUCH_INTERVAL_SECONDS:
                session.last_seen_at = now
                session.idle_expires_at = min(now + settings.idle_seconds, session.absolute_expires_at)
            result = self._context(session, user)
        return result

    def logout(self, context: AuthContext, request: RequestMetadata) -> None:
        now = self.clock.now()
        with self.database.session() as db:
            session = db.get(SessionModel, context.session_id)
            if session is not None and session.revoked_at is None:
                session.revoked_at = now
                session.revoked_reason = "logout"
            add_audit(
                db,
                now=now,
                request=request,
                action="auth.logout",
                outcome="success",
                actor_user_id=context.user_id,
                session_id=context.session_id,
            )

    def reauthenticate(self, context: AuthContext, password: str, request: RequestMetadata) -> AuthContext:
        now = self.clock.now()
        failure = False
        updated: AuthContext | None = None
        with self.database.session() as db:
            session = db.get(SessionModel, context.session_id)
            user = db.get(UserModel, context.user_id)
            if session is None or user is None or not self.passwords.verify(user.password_hash, password):
                failure = True
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="auth.reauthenticate",
                    outcome="denied",
                    actor_user_id=context.user_id,
                    session_id=context.session_id,
                )
            else:
                session.reauthenticated_at = now
                updated = self._context(session, user)
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="auth.reauthenticate",
                    outcome="success",
                    actor_user_id=context.user_id,
                    session_id=context.session_id,
                )
        if failure or updated is None:
            raise AuthenticationError("INVALID_PASSWORD", "当前密码错误", status=401)
        return updated

    def change_password(
        self,
        context: AuthContext,
        current_password: str,
        new_password: str,
        request: RequestMetadata,
    ) -> IssuedSession:
        self.passwords.validate(new_password)
        now = self.clock.now()
        failure = False
        issued: IssuedSession | None = None
        with self.database.session() as db:
            user = db.get(UserModel, context.user_id)
            if user is None or not self.passwords.verify(user.password_hash, current_password):
                failure = True
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="auth.password.change",
                    outcome="denied",
                    actor_user_id=context.user_id,
                    session_id=context.session_id,
                    target_type="user",
                    target_id=context.user_id,
                )
            else:
                user.password_hash = self.passwords.hash(new_password)
                user.must_change_password = False
                user.security_version += 1
                user.updated_at = now
                self._revoke_user_sessions(db, user.id, now, "password_changed")
                issued = self._issue_session(db, user, request, now, reauthenticated=True)
                add_audit(
                    db,
                    now=now,
                    request=request,
                    action="auth.password.change",
                    outcome="success",
                    actor_user_id=user.id,
                    session_id=issued.context.session_id,
                    target_type="user",
                    target_id=user.id,
                )
        if failure or issued is None:
            raise AuthenticationError("INVALID_PASSWORD", "当前密码错误", status=401)
        return issued

    def require_recent_auth(self, context: AuthContext) -> None:
        reauthenticated_at = context.reauthenticated_at
        if reauthenticated_at is None or self.clock.now() - reauthenticated_at > self.settings.security().reauth_seconds:
            raise AuthenticationError("REAUTHENTICATION_REQUIRED", "此操作需要重新验证密码", status=428)

    def verify_csrf(self, context: AuthContext, supplied: str | None) -> bool:
        return bool(supplied) and hmac.compare_digest(context.csrf_token, supplied)

    def revoke_all_for_user(
        self,
        *,
        actor: AuthContext,
        user_id: str,
        reason: str,
        request: RequestMetadata,
    ) -> int:
        now = self.clock.now()
        with self.database.session() as db:
            count = self._revoke_user_sessions(db, user_id, now, reason)
            add_audit(
                db,
                now=now,
                request=request,
                action="admin.user.sessions.revoke",
                outcome="success",
                actor_user_id=actor.user_id,
                session_id=actor.session_id,
                target_type="user",
                target_id=user_id,
                details={"count": count},
            )
            return count

    def issue_session_in_transaction(
        self,
        db: Session,
        user: UserModel,
        request: RequestMetadata,
        now: int,
        *,
        reauthenticated: bool,
    ) -> IssuedSession:
        return self._issue_session(db, user, request, now, reauthenticated=reauthenticated)

    def _issue_session(
        self,
        db: Session,
        user: UserModel,
        request: RequestMetadata,
        now: int,
        *,
        reauthenticated: bool,
    ) -> IssuedSession:
        settings = self.settings.security()
        raw_token = generate_opaque_token()
        csrf_token = secrets.token_urlsafe(32)
        absolute_expires_at = now + settings.absolute_seconds
        session = SessionModel(
            id=uuid.uuid4().hex,
            token_digest=digest_value(self._session_digest_key, raw_token),
            user_id=user.id,
            user_security_version=user.security_version,
            csrf_secret=csrf_token.encode("ascii"),
            created_at=now,
            last_seen_at=now,
            idle_expires_at=min(now + settings.idle_seconds, absolute_expires_at),
            absolute_expires_at=absolute_expires_at,
            reauthenticated_at=now if reauthenticated else None,
            revoked_at=None,
            revoked_reason=None,
            created_ip=request.client_ip[:64],
            user_agent_hash=user_agent_digest(request.user_agent),
        )
        db.add(session)

        active_sessions = list(
            db.scalars(
                select(SessionModel)
                .where(
                    SessionModel.user_id == user.id,
                    SessionModel.revoked_at.is_(None),
                    SessionModel.absolute_expires_at >= now,
                )
                .order_by(SessionModel.created_at.desc())
            )
        )
        for old_session in active_sessions[settings.max_sessions - 1 :]:
            old_session.revoked_at = now
            old_session.revoked_reason = "session_limit"

        context = self._context(session, user)
        return IssuedSession(
            token=raw_token,
            csrf_token=csrf_token,
            absolute_expires_at=absolute_expires_at,
            context=context,
        )

    @staticmethod
    def _context(session: SessionModel, user: UserModel) -> AuthContext:
        return AuthContext(
            session_id=session.id,
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=UserRole(user.role),
            must_change_password=user.must_change_password,
            csrf_token=session.csrf_secret.decode("ascii"),
            reauthenticated_at=session.reauthenticated_at,
        )

    def _rate_keys(self, username_normalized: str, client_ip: str) -> tuple[bytes, bytes]:
        return (
            digest_value(self._rate_limit_key, f"account:{username_normalized}"),
            digest_value(self._rate_limit_key, f"ip:{client_ip}"),
        )

    @staticmethod
    def _retry_after(db: Session, rate_keys: tuple[bytes, bytes], now: int) -> int:
        limits = db.scalars(
            select(LoginRateLimitModel).where(LoginRateLimitModel.bucket_key.in_(rate_keys))
        )
        return max(0, max((limit.locked_until - now for limit in limits), default=0))

    def _record_failure(self, db: Session, rate_keys: tuple[bytes, bytes], now: int) -> None:
        for key in rate_keys:
            limit = db.get(LoginRateLimitModel, key)
            if limit is None or now - limit.window_started_at > self._RATE_WINDOW_SECONDS:
                limit = LoginRateLimitModel(
                    bucket_key=key,
                    failures=1,
                    window_started_at=now,
                    last_failure_at=now,
                    locked_until=now,
                )
                db.add(limit)
            else:
                limit.failures += 1
                limit.last_failure_at = now
            if limit.failures >= 5:
                exponent = min(limit.failures - 5, 5)
                limit.locked_until = now + min(900, 30 * (2**exponent))

    @staticmethod
    def _clear_rate_limits(db: Session, rate_keys: tuple[bytes, bytes]) -> None:
        db.execute(delete(LoginRateLimitModel).where(LoginRateLimitModel.bucket_key.in_(rate_keys)))

    @staticmethod
    def _revoke_user_sessions(db: Session, user_id: str, now: int, reason: str) -> int:
        sessions = list(
            db.scalars(
                select(SessionModel).where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            )
        )
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = reason
        return len(sessions)
