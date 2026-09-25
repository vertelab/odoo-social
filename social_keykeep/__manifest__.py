# -*- coding: utf-8 -*-
# Part of Vertel. See LICENSE file for full copyright and licensing details.
{
    'name': 'Social Keykeep — Credential Bridge',
    'version': '18.0.1.0.0',
    'summary': 'Brygga sociala kontons hemligheter till krypterade keykeep.credential.',
    'category': 'Social Marketing',
    'description': '''
Social Keykeep — Credential Bridge
==================================

    Bridge module between odoo-social and keykeep.

    - Adds ``credential_id`` (keykeep.credential) to social_marketing.account.
    - Migrates legacy plaintext (linkedin_password, facebook_password, ...)
      to keykeep credentials.
    ''',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-social/social_keykeep',
    'license': 'AGPL-3',
    'depends': [
        'social_marketing',
        'keykeep',
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
    'application': False,
}
