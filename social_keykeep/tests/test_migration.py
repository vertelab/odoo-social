# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestCredentialMigration(TransactionCase):

    def _create_account(self, name):
        media = self.env['social_marketing.media'].search(
            [('media_type', '=', 'linkedin')], limit=1)
        if not media:
            media = self.env['social_marketing.media'].search([], limit=1)
        Account = self.env['social_marketing.account']
        # account.create() triggar _compute_statistics() → extern HTTP.
        # Mocka bort den i testmiljön.
        with patch.object(type(Account), '_compute_statistics', lambda self: None):
            return Account.create({
                'name': name,
                'media_id': media.id,
            })

    def test_migrate_linkedin_password(self):
        account = self._create_account('Test LinkedIn Mig')
        account.sudo().write({
            'linkedin_username': 'test@example.com',
            'linkedin_password': 'supersecret',
        })
        self.assertEqual(account.linkedin_password, 'supersecret')
        account._migrate_linkedin_password()
        self.assertTrue(account.credential_id)
        self.assertFalse(account.linkedin_password)
        self.assertEqual(
            account.credential_id._read_encrypted('password', system=True),
            'supersecret')

    def test_migration_idempotent(self):
        account = self._create_account('Test LinkedIn Mig 2')
        account.sudo().write({
            'linkedin_username': 'test2@example.com',
            'linkedin_password': 'secret2',
        })
        account._migrate_linkedin_password()
        cred_id = account.credential_id.id
        # Re-run: no duplicate credential, legacy already cleared
        account._migrate_linkedin_password()
        self.assertEqual(account.credential_id.id, cred_id)
