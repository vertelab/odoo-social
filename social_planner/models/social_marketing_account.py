# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import models

_logger = __import__('logging').getLogger(__name__)


class SocialMarketingAccount(models.Model):
    """ Add inbox fetch/reply hooks to social_marketing.account.
    Each platform module overrides _fetch_inbox_messages() to fetch
    DMs/comments via the platform API. """

    _inherit = 'social_marketing.account'

    def _fetch_inbox_messages(self):
        self.ensure_one()
        _logger.debug("No inbox handler for %s (%s)", self.display_name, self.media_type)
        return 0

    def _send_inbox_reply(self, message, body):
        self.ensure_one()
        _logger.debug("No reply handler for %s (%s)", self.display_name, self.media_type)
        return False
