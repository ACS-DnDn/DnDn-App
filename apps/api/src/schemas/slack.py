"""Slack 연동 전용 스키마."""

from __future__ import annotations

from pydantic import BaseModel


class SlackStatusResponse(BaseModel):
    connected: bool
    workspace: str | None
    channel: str | None
    notifyEnabled: bool


class SlackSettingsRequest(BaseModel):
    channel: str | None = None
    notifyEnabled: bool | None = None
