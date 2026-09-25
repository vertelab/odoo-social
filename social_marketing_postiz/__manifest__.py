# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'name': 'Social: Marketing Postiz Bridge',
    'category': 'Marketing/Social Marketing',
    'summary': 'Use Postiz as universal API proxy for all social media platforms.',
    'version': '18.0.1.0.0',
    'description': '''
Marketing Postiz Bridge
=======================

    Connects Odoo social_planner to a Postiz server (cloud or self-hosted).
    Postiz acts as a universal API proxy providing access to 32+ platforms:

    LinkedIn, Facebook, Instagram, Twitter/X, YouTube, TikTok, Pinterest,
    Reddit, Threads, Bluesky, Mastodon, Discord, Slack, Telegram, Twitch,
    Medium, Dev.to, Hashnode, WordPress, and more.

    **Benefits over direct platform APIs:**
    - Single API endpoint for all platforms
    - Postiz handles OAuth flows, token refresh, rate limiting
    - Browser/Playwright fallback not needed — Postiz maintains platform integrations
    - 32+ platforms without building 32+ Odoo modules

    **Architecture:**
    ```
    Odoo social_planner → social_marketing_postiz → Postiz Server → 32 Platforms
    ```

    **Setup:**
    1. Deploy Postiz (Docker Compose recommended) or use Postiz Cloud
    2. Connect your social accounts in Postiz
    3. Get API key from Postiz Settings → Developers → Public API
    4. Enter the API key + URL in Odoo Settings → Social Marketing

    Features:

        - UI Integration: Extends 2 view(s) in the Odoo interface.
        - Extends Odoo: Builds on social_marketing.account, social_marketing.live.post, social_marketing.media.
    ''',
    'website': 'https://vertel.se/apps/odoo-social/social_marketing_postiz',
    'depends': ['social_marketing', 'social_planner'],
    'data': [
        'security/ir.model.access.csv',
        'data/social_marketing_media_data.xml',
        'views/res_config_settings_views.xml',
        'views/social_marketing_account_views.xml',
    ],
    'external_dependencies': {
        'python': [],
    },
    'auto_install': False,
    'installable': True,
    'license': 'AGPL-3',
}
