from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass

from flask import Request

from app.application.audit import RequestMetadata
from app.application.settings import SettingsService


@dataclass(frozen=True, slots=True)
class RequestSecurity:
    client_ip: str
    secure: bool


class RequestSecurityResolver:
    def __init__(self, settings: SettingsService) -> None:
        self.settings = settings

    def resolve(self, request: Request) -> RequestSecurity:
        direct_ip = self._parse_ip(request.remote_addr) or ipaddress.ip_address("127.0.0.1")
        trusted_networks = self._trusted_networks()
        trusted_direct_peer = any(direct_ip in network for network in trusted_networks)
        client_ip = direct_ip
        secure = request.is_secure

        if trusted_direct_peer:
            forwarded_chain = self._forwarded_chain(request.headers.get("X-Forwarded-For", ""))
            chain = [*forwarded_chain, direct_ip]
            while len(chain) > 1 and any(chain[-1] in network for network in trusted_networks):
                chain.pop()
            client_ip = chain[-1]
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[-1].strip().lower()
            if forwarded_proto in {"http", "https"}:
                secure = forwarded_proto == "https"

        return RequestSecurity(client_ip=str(client_ip), secure=secure)

    def metadata(self, request: Request) -> RequestMetadata:
        state = self.resolve(request)
        return RequestMetadata(
            client_ip=state.client_ip,
            user_agent=request.headers.get("User-Agent", "")[:512],
            method=request.method[:10],
            path=(request.url_rule.rule if request.url_rule is not None else request.path)[:300],
            request_id=request.environ.setdefault("fcc.request_id", uuid.uuid4().hex),
        )

    def _trusted_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        raw = self.settings.get("security.trusted_proxy_cidrs", [])
        if not isinstance(raw, list):
            return []
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for value in raw:
            try:
                networks.append(ipaddress.ip_network(str(value), strict=False))
            except ValueError:
                continue
        return networks

    @staticmethod
    def _forwarded_chain(value: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        result: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for part in value.split(","):
            parsed = RequestSecurityResolver._parse_ip(part.strip())
            if parsed is not None:
                result.append(parsed)
        return result

    @staticmethod
    def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        if not value:
            return None
        try:
            return ipaddress.ip_address(value)
        except ValueError:
            return None
