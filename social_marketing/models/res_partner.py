# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class ResPartnerLinkedIn(models.Model):
    """LinkedIn connection fields on res.partner.

    Lets us capture a company's LinkedIn identity (URL, URN, numeric ID)
    once — e.g. when scraping competitor/customer pages — and reuse it for
    streams, competitor monitoring and lead enrichment.
    """

    _inherit = 'res.partner'

    linkedin_url = fields.Char(
        'LinkedIn URL',
        help='Full LinkedIn company/profile URL, e.g. https://www.linkedin.com/company/ucs-onedo/',
    )
    linkedin_urn = fields.Char(
        'LinkedIn URN',
        help='LinkedIn URN, e.g. urn:li:company:ucs-onedo or urn:li:organization:123456',
    )
    linkedin_id = fields.Char(
        'LinkedIn ID',
        help='LinkedIn numeric/vanity identifier (e.g. "ucs-onedo" or "28657311").',
    )
