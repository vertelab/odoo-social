# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SocialMarketingStreamCompetitor(models.Model):
    """Link streams to competitors (social listening + competitor monitor)."""

    _inherit = 'social_marketing.stream'

    competitor_id = fields.Many2one(
        'social_marketing.competitor', string='Competitor',
        ondelete='set null',
        help='Competitor this stream monitors. Enables the smart button on '
             'the competitor card that opens the stream posts.',
    )

    stream_post_count = fields.Integer(
        'Posts', compute='_compute_stream_post_count',
    )

    @api.depends('stream_post_ids')
    def _compute_stream_post_count(self):
        for stream in self:
            stream.stream_post_count = len(stream.stream_post_ids)

    @api.model
    def refresh_linkedin_company_streams(self):
        """Refresh all LinkedIn company-page/feed streams.

        Called by ir.cron. Keeps scraping frequency low (LinkedIn rate limits).
        Returns dict with counts.
        """
        streams = self.search([
            ('media_id.media_type', '=', 'linkedin'),
            ('stream_type_id.stream_type', 'in', ['linkedin_company_page', 'linkedin_feed']),
        ])
        created_total = 0
        ok = 0
        errors = 0
        for stream in streams:
            try:
                if stream._fetch_stream_data():
                    created_total += 1
                ok += 1
            except Exception as e:
                errors += 1
                _logger.error('LinkedIn stream refresh failed for %s: %s', stream.name, e)
        _logger.info(
            'LinkedIn company streams refresh: %d ok, %d errors, %d with new posts',
            ok, errors, created_total,
        )
        return {'ok': ok, 'errors': errors, 'new_posts_streams': created_total}
