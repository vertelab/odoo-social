# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'name': 'Social: Communication Planner',
    'category': 'Marketing/Social Marketing',
    'summary': 'Communication planning, policy, approval workflows and AI-assisted social marketing.',
    'version': '18.0.1.9.0',
    'description': '''
Communication Planner
=====================

    Social Planner - Communication planning for social media.

    - Communication policy: tone of voice, brand voice, publishing rules.
    - Content planning and approval flows.
    ''',
    'website': 'https://vertel.se/apps/odoo-social/social_planner',
    'depends': [
        'social_marketing',
        'social_marketing_linkedin',
        'social_marketing_facebook',
        'social_marketing_instagram',
        'ai_agent_core',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/communication_policy_data.xml',
        'data/communication_plan_data.xml',
        'data/competitor_demo_data.xml',
        'data/last30days_coworker.xml',
        'data/cron.xml',
        'views/communication_policy_views.xml',
        'views/communication_plan_views.xml',
        'views/content_calendar_views.xml',
        'views/social_marketing_post_views.xml',
        'views/social_listening_views.xml',
        'views/social_marketing_competitor_views.xml',
        'views/social_marketing_message_views.xml',
        'views/menu_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [],
    'application': True,
    'installable': True,
    'auto_install': False,
    'license': 'AGPL-3',
}
