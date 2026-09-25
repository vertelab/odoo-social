# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'website': 'https://vertel.se/apps/odoo-social/social_marketing_instagram',
    'name': 'Social: Marketing Instagram',
    'category': 'Marketing/Social Marketing',
    'summary': 'Manage your Instagram business account and schedule posts.',
    'version': '18.0.1.0.0',
    'description': '''
Marketing Instagram
===================

    Unified inbox: Instagram DMs and comments appear in the social_planner inbox.

    Requires a Facebook App with Instagram Basic Display and Instagram Graph API:
    - instagram_basic
    - instagram_manage_messages
    - instagram_manage_comments

    Features:

        - UI Integration: Extends 3 view(s) in the Odoo interface.
        - Extends Odoo: Builds on social_marketing.account, social_marketing.live.post, social_marketing.media, social_marketing.post.
    ''',
    'depends': ['social_marketing', 'social_marketing_facebook'],
    'data': [
        'security/ir.model.access.csv',
        'data/social_marketing_media_data.xml',
        'views/social_marketing_post_template_views.xml',
        'views/social_marketing_instagram_preview.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': False,
    'installable': True,
    'assets': {
        'web.assets_backend': [
            'social_marketing_instagram/static/src/scss/social_marketing_instagram.scss',
        ],
    },
    'license': 'AGPL-3',
}
