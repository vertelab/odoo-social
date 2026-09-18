# -*- coding: utf-8 -*-
# Part of Vertel. See LICENSE file for full copyright and licensing details.
{
    'name': 'Social AI — Bridge',
    'version': '18.0.1.0.1',
    'summary': 'Social coach coworker för Odoo Mind Workspace (social_marketing)',
    'category': 'AI Orchestration',
    'description': """
        Bridge mellan odoo-social och ai_agent_core (task 10.5).

        Lägger till social-coach-coworkern som data XML:
        - läser social_marketing.post, account, post.template och
          ai.okf.concept
        - drar inläggsförslag → Workspace-agendan (godkända →
          social_marketing.post schemalagd, inte publicerad omedelbart)
        - HITL via workspace.activity.suggestion (godkännandekön)
    """,
    'author': 'Vertel Sverige AB',
    'license': 'AGPL-3',
    'depends': [
        'ai_agent_core',
        'social_marketing',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/social_coach.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
