# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import os

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SocialBrandCredential(models.Model):
    """Per-brand credentials for login-required social media research.

    The last30days research engine (deployed via the opencode.last30days Salt
    state) reads one credential set per run. It supports an isolated config
    directory through the ``LAST30DAYS_CONFIG_DIR`` environment variable, so
    each brand gets its own ``.env`` file with that brand's logged-in
    accounts (X/Twitter, Bluesky, ScrapeCreators for TikTok/Instagram/Threads,
    Truth Social). This prevents cross-brand leakage and lets research run
    with the correct account for the brand being researched.
    """

    _name = 'social.brand.credential'
    _description = 'Social Brand Credential'
    _order = 'brand_id, platform'

    PLATFORMS = [
        ('x', 'X / Twitter'),
        ('bluesky', 'Bluesky'),
        ('scrapecreators', 'ScrapeCreators (TikTok/Instagram/Threads)'),
        ('truthsocial', 'Truth Social'),
        ('openai', 'OpenAI'),
        ('xai', 'xAI (Grok)'),
        ('google', 'Google / Gemini'),
        ('other', 'Other'),
    ]

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade',
        index=True)
    platform = fields.Selection(PLATFORMS, string='Platform', required=True)
    active = fields.Boolean('Active', default=True)

    # Secret values. Plaintext in the database for now — the hardening path is
    # the keykeep integration already used by social_marketing_linkedin /
    # social_marketing_facebook (account.credential_id._read_encrypted(...)).
    api_key = fields.Char(
        'API Key',
        help='Used for ScrapeCreators (SCRAPECREATORS_API_KEY), OpenAI, xAI '
             'or Google depending on platform.',
        groups='social_marketing.group_social_marketing_manager')
    auth_token = fields.Char(
        'X Auth Token', groups='social_marketing.group_social_marketing_manager')
    ct0 = fields.Char(
        'X ct0', groups='social_marketing.group_social_marketing_manager')
    username = fields.Char(
        'Username', groups='social_marketing.group_social_marketing_manager')
    password = fields.Char(
        'Password', groups='social_marketing.group_social_marketing_manager')
    bsky_handle = fields.Char(
        'Bluesky Handle', groups='social_marketing.group_social_marketing_manager')
    bsky_app_password = fields.Char(
        'Bluesky App Password',
        groups='social_marketing.group_social_marketing_manager')
    truthsocial_token = fields.Char(
        'Truth Social Token',
        groups='social_marketing.group_social_marketing_manager')

    _sql_constraints = [
        ('brand_platform_uniq', 'UNIQUE(brand_id, platform)',
         'A credential for this platform already exists for this brand.'),
    ]

    @api.constrains('platform', 'auth_token', 'ct0')
    def _check_x_pair(self):
        for rec in self:
            if rec.platform == 'x' and bool(rec.auth_token) != bool(rec.ct0):
                raise ValidationError(
                    _('X credentials require both Auth Token and ct0.'))

    # ------------------------------------------------------------------
    # last30days environment mapping
    # ------------------------------------------------------------------

    def _get_env_dict(self):
        """Return the last30days environment variables for this credential.

        Keys match what the engine's ``lib/env.py`` reads
        (see /usr/local/share/opencode/skills/last30days).
        """
        self.ensure_one()
        mapping = {
            'x': {'AUTH_TOKEN': self.auth_token, 'CT0': self.ct0},
            'bluesky': {'BSKY_HANDLE': self.bsky_handle,
                        'BSKY_APP_PASSWORD': self.bsky_app_password},
            'scrapecreators': {'SCRAPECREATORS_API_KEY': self.api_key},
            'truthsocial': {'TRUTHSOCIAL_TOKEN': self.truthsocial_token},
            'openai': {'OPENAI_API_KEY': self.api_key},
            'xai': {'XAI_API_KEY': self.api_key},
            'google': {'GOOGLE_API_KEY': self.api_key},
            'other': {},
        }
        return {k: v for k, v in mapping.get(self.platform, {}).items() if v}

    @api.model
    def _env_base_dir(self):
        """Base directory for per-brand last30days config dirs."""
        return self.env['ir.config_parameter'].sudo().get_param(
            'social_brand.credential_env_dir', '/var/lib/last30days/brands')

    def _env_dir(self):
        """Per-brand config directory (LAST30DAYS_CONFIG_DIR target)."""
        self.ensure_one()
        slug = (self.brand_id.name or 'brand').lower().replace(' ', '-')
        return os.path.join(self._env_base_dir(),
                            '%s-%s' % (self.brand_id.id, slug))

    def action_write_env_file(self):
        """Write this credential's .env into the brand's config directory."""
        for rec in self:
            rec._write_env_file()
        return True

    def _write_env_file(self):
        """Write a 0600 .env with this credential's secrets for the engine."""
        self.ensure_one()
        env_dir = self._env_dir()
        os.makedirs(env_dir, exist_ok=True)
        env_dict = self._get_env_dict()
        lines = ['# Generated by social_marketing_agency: %s / %s'
                 % (self.brand_id.name, self.platform)]
        lines += ['%s=%s' % (key, value)
                  for key, value in sorted(env_dict.items())]
        path = os.path.join(env_dir, '.env')
        with open(path, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        os.chmod(path, 0o600)
        return path

    @api.model
    def write_brand_env_files(self, brand_ids=None):
        """Materialize all active credentials of a brand (or all brands).

        Called after credential changes so the research engine always sees an
        up-to-date per-brand .env.
        """
        domain = [('active', '=', True)]
        if brand_ids:
            domain += [('brand_id', 'in', brand_ids)]
        for rec in self.search(domain):
            rec._write_env_file()
        return True
