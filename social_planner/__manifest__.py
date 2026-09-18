# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'name': 'Social: Communication Planner',
    'category': 'Marketing/Social Marketing',
    'summary': 'Communication planning, policy, approval workflows and AI-assisted social marketing',
    'version': '1.9',
    'description': """
Social Planner — Kommunikationsplanering för sociala medier
===========================================================

* Kommunikationspolicy — tonalitet, varumärkesröst, publiceringsregler, krisprotokoll
* Kommunikationsplan — flerkanals-kampanjplanering med content-kalender
* Godkännandeflöde — roller (skapare, granskare, publicerare) med policy-validering
* AI-integration — innehållsgenerering, sentimentanalys, "bästa tid att posta"
* Avancerad analys — cross-channel dashboards, ROI-spårning, compliance-rapporter
* Social listening — nyckelords-/hashtag-bevakning
* Mediebibliotek — återanvändbara assets med AI-taggning
    """,
    'website': 'https://vertel.se/app/odoo-social',
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
