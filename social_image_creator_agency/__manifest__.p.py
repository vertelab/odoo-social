# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

{
    'name': 'Social Image Creator Agency Glue',
    'category': 'Marketing/Social Marketing',
    'summary': 'Brand scoping and brand kits for social image templates',
    'version': '18.0.1.0.0',
    'description': """
Glue module between social_image_creator and social_marketing_agency
(design decision D8): brand-scoped image templates, a brand kit (color
palette and uploaded fonts) on social.brand, brand-aware editor asset
providers and brand-constrained binding record pickers.
""",
    'website': 'https://vertel.se/app/odoo-social',
    'depends': ['social_image_creator', 'social_marketing_agency'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/social_brand_views.xml',
        'views/social_image_template_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'social_image_creator_agency/static/src/js/*',
        ],
    },
    'application': False,
    'installable': True,
    'license': 'AGPL-3',
}
