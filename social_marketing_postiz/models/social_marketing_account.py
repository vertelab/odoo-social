# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import json
import logging
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialMarketingAccountPostiz(models.Model):
    """ Postiz bridge account — wraps a Postiz integration as a social_marketing.account.
    All publishing flows through the Postiz Public API, which proxies to
    the actual platform. """

    _inherit = 'social_marketing.account'

    postiz_integration_id = fields.Char('Postiz Integration ID',
        help="The Postiz integration UUID that this account maps to.")

    def _postiz_api_url(self):
        """ Get the Postiz API base URL from settings. """
        base = self.env['ir.config_parameter'].sudo().get_param(
            'social_marketing_postiz.api_url', 'https://api.postiz.com')
        return f"{base.rstrip('/')}/public/v1"

    def _postiz_headers(self):
        """ Get API headers with authentication. """
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'social_marketing_postiz.api_key', '')
        if not api_key:
            raise UserError(_(
                'Postiz API key is not configured. '
                'Go to Settings → Social Marketing → Postiz to set it up.'))
        return {
            'Authorization': api_key,
            'Content-Type': 'application/json',
        }

    def action_sync_postiz_integrations(self):
        """ Fetch integrations from Postiz and create/update Odoo accounts.
        Maps each Postiz integration to a social_marketing.account. """
        try:
            url = f"{self._postiz_api_url()}/integrations"
            response = requests.get(url, headers=self._postiz_headers(), timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(_(
                'Failed to connect to Postiz: %(error)s.\n'
                'Check your API key and URL in Settings.',
                error=str(e)))

        integrations = response.json()
        created = 0
        updated = 0

        for integration in integrations:
            provider = integration.get('identifier', '')
            integration_id = integration.get('id', '')
            name = integration.get('name', provider)
            profile = integration.get('profile', '')
            disabled = integration.get('disabled', False)
            picture = integration.get('picture', '')

            # Find or create the matching media
            media = self._find_or_create_postiz_media(provider)

            # Find existing account by integration_id
            account = self.search([
                ('postiz_integration_id', '=', integration_id),
                ('media_id', '=', media.id),
            ], limit=1)

            if account:
                account.write({
                    'name': name,
                    'active': not disabled,
                    'is_media_disconnected': disabled,
                    'social_account_handle': profile,
                })
                updated += 1
            else:
                self.create({
                    'name': name,
                    'media_id': media.id,
                    'postiz_integration_id': integration_id,
                    'social_account_handle': profile,
                    'active': not disabled,
                    'is_media_disconnected': disabled,
                    'has_account_stats': True,
                })
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Postiz Sync Complete'),
                'message': _('Created %(created)s accounts, updated %(updated)s.',
                           created=created, updated=updated),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _find_or_create_postiz_media(self, provider):
        """ Map Postiz provider to social_marketing.media, creating if needed. """
        # Normalize provider names
        provider_map = {
            'x': 'twitter',
            'linkedin': 'linkedin',
            'linkedin-page': 'linkedin',
            'facebook': 'facebook',
            'instagram': 'instagram',
            'instagram-standalone': 'instagram',
            'youtube': 'youtube',
            'tiktok': 'tiktok',
            'pinterest': 'pinterest',
            'threads': 'threads',
            'bluesky': 'bluesky',
            'mastodon': 'mastodon',
            'reddit': 'reddit',
            'discord': 'discord',
            'slack': 'slack',
            'telegram': 'telegram',
            'twitch': 'twitch',
            'medium': 'medium',
            'devto': 'devto',
            'hashnode': 'hashnode',
            'wordpress': 'wordpress',
            'warpcast': 'warpcast',
            'nostr': 'nostr',
            'vk': 'vk',
            'kick': 'kick',
            'lemmy': 'lemmy',
            'dribbble': 'dribbble',
            'gmb': 'gmb',
            'listmonk': 'listmonk',
        }

        media_type = provider_map.get(provider, provider)
        media_name = dict(self.env['social_marketing.media']._fields['media_type']._description_selection(self.env)).get(media_type, provider.title())

        # Find or create media
        media = self.env['social_marketing.media'].search([
            ('media_type', '=', media_type),
        ], limit=1)

        if not media:
            media = self.env['social_marketing.media'].create({
                'name': f'Postiz: {media_name}',
                'media_type': media_type,
                'postiz_provider': provider,
                'has_streams': False,
                'can_link_accounts': True,
            })

        return media

    def _fetch_inbox_messages(self):
        """ Postiz does not currently support inbox/messaging via Public API. """
        self.ensure_one()
        return 0

    def _send_inbox_reply(self, message, body):
        """ Postiz does not currently support inbox replies via Public API. """
        return False
