# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

""" Report model behind the brand performance PDF.

All the work sits on the wizard. This model only turns the selected wizards
into the list of blocks the template walks, and it does so as the requesting
user so the brand restrictions still hold at rendering time.
"""

from odoo import api, models


class ReportSocialBrandPerformance(models.AbstractModel):
    _name = 'report.social_marketing_agency.report_social_brand_performance'
    _description = 'Brand Performance Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['social.brand.report.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'social.brand.report.wizard',
            'docs': wizards,
            'reports': [wizard._report_data() for wizard in wizards],
        }
