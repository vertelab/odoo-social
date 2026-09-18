# -*- coding: utf-8 -*-
"""social_keykeep — installationshakar."""


def post_init_hook(env):
    """Migrera legacy-klartext till keykeep.credential vid installation."""
    env['social_marketing.account']._migrate_legacy_credentials()
