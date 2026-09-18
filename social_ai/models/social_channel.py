# -*- coding: utf-8 -*-
"""Social channel-adapter — registrerar 'social'-kanalen i ai_agent_core.core.channel.

Följer channel-adapter-kontraktet (core/channel.py):
- NormalizedItem — kanal-neutralt item.
- ChannelAdapter — in-/utåtgående adapter.
- ItemProcessor — domänbunden pipeline (klassificering → disposition →
  HITL → nudge → minne).

`fetch_new` returnerar tills vidare en tom lista (inga plattforms-API:er
är kopplade ännu); kontraktet är redo för framtida plattformsintegration.
"""

import logging

from odoo.addons.ai_agent_core.core.channel import (
    NormalizedItem,
    channel_registry,
)

_logger = logging.getLogger(__name__)


class SocialChannelAdapter:
    """In-/utåtgående adapter för sociala media (kommentarer, mentions, DM)."""

    def __init__(self, env=None):
        self.env = env

    def fetch_new(self, user, since=None):
        """Hämta nya items sedan `since`. Ingen plattforms-API ännu → tom lista."""
        return []

    def normalize(self, raw):
        """Normalisera ett rå-objekt till NormalizedItem."""
        if isinstance(raw, NormalizedItem):
            return raw
        raw = raw or {}
        return NormalizedItem(
            channel='social',
            external_id=str(raw.get('external_id') or ''),
            sender=str(raw.get('sender') or ''),
            content=str(raw.get('content') or ''),
            received_at=str(raw.get('received_at') or ''),
        )

    def dispose(self, item, disposition):
        """Verkställ en disposition. 'create' skapar ett utkast (state=draft)."""
        if disposition == 'create':
            self._create_draft_post(item)

    def _create_draft_post(self, item):
        if not self.env:
            return None
        return self.env['social_marketing.post'].create({
            'message': item.content,
            'state': 'draft',
        })

    def draft_outbound(self, user, item, content):
        """Förbered ett utkast (social-post-skiss)."""
        return {'message': content, 'state': 'draft'}

    def send_outbound(self, user, item, content):
        """Publicera — anropas ENDAST efter HITL-godkännande (se social_publish_hitl)."""
        return None


class SocialItemProcessor:
    """Domänbunden pipeline för sociala inkommande items."""

    def __init__(self, env=None):
        self.env = env

    async def classify(self, item):
        """Klassificera ett item till en disposition.

        Inkommande socialt innehåll blir ett förslag ('draft') som väntar på
        godkännande — aldrig en omedelbar skapelse/publicering.
        """
        return {
            'disposition': 'draft',
            'hitl_required': False,
        }

    def dispose(self, item, disposition):
        """Verkställ dispositionen på det normaliserade itemet."""
        if disposition == 'create' and self.env:
            self.env['social_marketing.post'].create({
                'message': item.content,
                'state': 'draft',
            })

    def hitl(self, item, action_type, context):
        """Begär godkännande via ai.coworker.hitl (asynkront — state='asked')."""
        if not self.env:
            return None
        coworker = self._get_coworker()
        if not coworker:
            return None
        return coworker._request_hitl(
            action_type,
            summary=context.get('summary') or action_type,
            context=context,
            risk_level='high',
        )

    def nudge(self, item, message):
        """Nudge (påminnelse) — tills vidare no-op."""
        return None

    def remember(self, item):
        """Spara till minne (OKF + graf) — tills vidare no-op."""
        return None

    def _get_coworker(self):
        if not self.env:
            return None
        return self.env['ai.coworker'].search(
            [('channel_alias', '=', 'social')], limit=1)


# Registrera social-kanalen (idempotent — registry är en modul-singleton).
social_channel_adapter = SocialChannelAdapter()
social_channel_processor = SocialItemProcessor()
channel_registry.register(
    'social',
    adapter=social_channel_adapter,
    processor=social_channel_processor,
)
