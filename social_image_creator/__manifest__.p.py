# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'name': 'Social Image Creator',
    'category': 'Marketing/Social Marketing',
    'summary': 'Create social images from reusable Fabric.js templates',
    'version': '18.0.1.0.0',
    'description': """Create social images from reusable Fabric.js templates""",
    'website': 'https://vertel.se/app/odoo-social',
    'depends': ['social_marketing'],
    'data': [
        'security/ir.model.access.csv',
        'data/social_image_size_data.xml',
        'views/social_image_template_views.xml',
        'views/social_image_render_wizard_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'social_image_creator/static/src/lib/fabric_loader.js',
            'social_image_creator/static/src/js/dialog/*',
            'social_image_creator/static/src/js/fields/*',
            'social_image_creator/static/src/scss/*',
            'social_image_creator/static/src/xml/**/*',
        ],
    },
    'application': False,
    'installable': True,
    'license': 'AGPL-3',
}
