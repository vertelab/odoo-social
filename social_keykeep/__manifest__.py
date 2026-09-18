# -*- coding: utf-8 -*-
# Part of Vertel. See LICENSE file for full copyright and licensing details.
{
    'name': 'Social Keykeep — Credential Bridge',
    'version': '18.0.1.0.0',
    'summary': 'Brygga sociala kontons hemligheter till krypterade keykeep.credential',
    'category': 'Social Marketing',
    'description': """
        Bryggmodul mellan odoo-social och keykeep.

        - Lägger till `credential_id` (keykeep.credential) på social_marketing.account.
        - Migrerar legacy-klartext (linkedin_password, facebook_page_access_token)
          till krypterade keykeep.credential (Fernet) och rensar källfälten.
        - Publicering läser hemligheten via keykeeps systemväg
          (`_read_encrypted(..., system=True)`), aldrig klartext.
    """,
    'author': 'Vertel Sverige AB',
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
