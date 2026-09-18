# -*- coding: utf-8 -*-
"""social_keykeep — brygga sociala konton till krypterade keykeep.credential."""

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SocialAccountKeykeep(models.Model):
    _inherit = 'social_marketing.account'

    credential_id = fields.Many2one(
        'keykeep.credential', string='Keykeep Credential',
        help='Krypterad credential (keykeep) som håller kontots hemlighet.')

    def _get_keykeep_secret(self, field_name):
        """Läs hemlighet via systemvägen (read() returnerar chiffertext)."""
        self.ensure_one()
        if self.credential_id:
            return self.credential_id._read_encrypted(field_name, system=True)
        return None

    def _migrate_legacy_credentials(self):
        """Migrera legacy-klartext till keykeep.credential (idempotent, fail-safe)."""
        Account = self.env['social_marketing.account']
        if 'linkedin_password' in Account._fields:
            for account in Account.search([
                ('linkedin_password', '!=', False),
                ('credential_id', '=', False),
            ]):
                account._migrate_linkedin_password()
        if 'facebook_page_access_token' in Account._fields:
            for account in Account.search([
                ('facebook_page_access_token', '!=', False),
                ('credential_id', '=', False),
            ]):
                account._migrate_facebook_token()

    def _get_or_create_platform_subscription(self, platform_name):
        """Hitta eller skapa en keykeep.subscription för en plattform."""
        self.ensure_one()
        company = self.company_id or self.env.company
        subscription = self.env['keykeep.subscription'].search([
            ('name', '=', platform_name),
            ('company_id', '=', company.id),
        ], limit=1)
        if not subscription:
            subscription = self.env['keykeep.subscription'].create({
                'name': platform_name,
                'company_id': company.id,
                'currency_id': company.currency_id.id,
                'renewal_frequency': 'yearly',
            })
        return subscription

    def _migrate_linkedin_password(self):
        self.ensure_one()
        if self.credential_id or not self.linkedin_password:
            return
        try:
            subscription = self._get_or_create_platform_subscription('LinkedIn')
            credential = self.env['keykeep.credential'].create({
                'name': 'LinkedIn — %s' % (
                    self.name or self.social_account_handle or 'konto'),
                'subscription_id': subscription.id,
                'credential_type': 'login',
                'username': self.linkedin_username,
                'password': self.linkedin_password,
            })
            self.write({'credential_id': credential.id,
                        'linkedin_password': False})
        except Exception as e:
            _logger.warning(
                'social_keykeep: LinkedIn-migrering misslyckades (%s): %s',
                self.id, e)

    def _migrate_facebook_token(self):
        self.ensure_one()
        if self.credential_id or not self.facebook_page_access_token:
            return
        try:
            subscription = self._get_or_create_platform_subscription('Facebook')
            credential = self.env['keykeep.credential'].create({
                'name': 'Facebook — %s' % (
                    self.name or self.social_account_handle or 'konto'),
                'subscription_id': subscription.id,
                'credential_type': 'token',
                'key_value': self.facebook_page_access_token,
            })
            self.write({'credential_id': credential.id})
            # facebook_page_access_token är readonly → rensa via SQL.
            self.env.cr.execute(
                'UPDATE social_marketing_account '
                'SET facebook_page_access_token = NULL WHERE id = %s',
                (self.id,))
        except Exception as e:
            _logger.warning(
                'social_keykeep: Facebook-migrering misslyckades (%s): %s',
                self.id, e)
