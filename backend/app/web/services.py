from __future__ import annotations

from dataclasses import dataclass

from app.application.auth import AuthService
from app.application.bootstrap import BootstrapService
from app.application.features import FeatureService
from app.application.identity import IdentityService
from app.application.runs import RunService
from app.application.schedules import ScheduleService
from app.application.settings import SettingsService
from app.application.system_settings import SystemSettingsService
from app.application.system_operations import SystemOperationsService
from app.application.system_updates import SystemUpdateService
from app.domain.time import Clock
from app.infrastructure.database import Database
from app.infrastructure.instance_manager import InstanceManager
from app.infrastructure.paths import AppPaths
from app.security.crypto import PreAuthCsrf


@dataclass(frozen=True, slots=True)
class Services:
    paths: AppPaths
    database: Database
    settings: SettingsService
    auth: AuthService
    bootstrap: BootstrapService
    identity: IdentityService
    features: FeatureService
    runs: RunService
    schedules: ScheduleService
    system_settings: SystemSettingsService
    system_operations: SystemOperationsService
    system_updates: SystemUpdateService
    instance: InstanceManager
    preauth_csrf: PreAuthCsrf
    clock: Clock
