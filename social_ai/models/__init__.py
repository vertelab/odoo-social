# -*- coding: utf-8 -*-
"""social_ai — bridge mellan odoo-social och ai_agent_core.

Domänbridge per Vertel-konvention: `<domän>_ai`.
Kopplar social-coach-coworkern (skills/agents) till Workspace-agendan,
channel-adapter-kontraktet och record-baserad HITL (social_publish).
Manifestet beror ENDAST på ai_agent_core + social_marketing (ingen
domänmodul skrivs direkt; kärnan förblir core-ren).
"""

from . import social_channel
from . import social_publish_hitl
