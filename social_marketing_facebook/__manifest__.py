# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'website': 'https://vertel.se/apps/odoo-social/social_marketing_facebook',
    'name': 'Social: Marketing Facebook',
    'category': 'Marketing/Social Marketing',
    'summary': 'Manage your Facebook pages and schedule posts.',
    'version': '18.0.1.0.0',
    'description': '''
Marketing Facebook
==================

    Unified inbox: Facebook DMs and comments appear in the social_planner inbox.

    Requires a Facebook App with:
    - pages_manage_posts
    - pages_read_engagement
    - pages_manage_metadata
    - pages_messaging (for DMs)

    Features:

        - UI Integration: Extends 3 view(s) in the Odoo interface.
        - Extends Odoo: Builds on social_marketing.account, social_marketing.live.post, social_marketing.media, social_marketing.post.
    ''',
    'depends': ['social_marketing'],
    'data': [
        'security/ir.model.access.csv',
        'data/social_marketing_media_data.xml',
        'views/social_marketing_post_template_views.xml',
        'views/social_marketing_facebook_preview.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': False,
    'installable': True,
    'assets': {
        'web.assets_backend': [
            'social_marketing_facebook/static/src/scss/social_marketing_facebook.scss',
        ],
    },
    'license': 'AGPL-3',
}
