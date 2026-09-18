# -*- coding: utf-8 -*-
{
    'name': 'Social: Marketing LinkedIn',
    'summary': 'Manage your LinkedIn accounts and schedule posts',
    'description': 'Manage your LinkedIn accounts and schedule posts',
    'category': 'Marketing/Social Marketing',
    'version': '0.2',
    'depends': ['social_marketing',],
    'external_dependencies': {
        'python': ['linkedin_api', 'playwright'],
    },
    'data': [
        'data/social_media_data.xml',
        'views/social_marketing_post_template_views.xml',
        'views/social_marketing_linkedin_preview.xml',
        'views/social_marketing_stream_posts_views.xml',
        'views/social_marketing_stream_views.xml',
        'views/social_marketing_account_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'assets': {
        'web.assets_backend': [
    #         'social_marketing_linkedin/static/src/js/stream_post_comment.js',
    #         'social_marketing_linkedin/static/src/js/stream_post_comment_list.js',
    #         'social_marketing_linkedin/static/src/js/stream_post_comments.js',
    #         'social_marketing_linkedin/static/src/js/stream_post_comments_reply.js',
    #         'social_marketing_linkedin/static/src/js/stream_post_kanban_record.js',
    #         ('after', 'social_marketing/static/src/js/social_marketing_post_formatter_mixin.js', 'social_marketing_linkedin/static/src/js/social_post_formatter_mixin.js'),
            'social_marketing_linkedin/static/src/scss/social_marketing_linkedin.scss',
    #         'social_marketing_linkedin/static/src/xml/**/*',
        ],
    #     'web.assets_web_dark': [
    #         'social_marketing_linkedin/static/src/scss/social_marketing_linkedin.dark.scss',
    #     ],
    },
    'license': 'AGPL-3',
}
