# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    social_dashboard_negative_sentiment_alert_threshold = fields.Float(
        string="Negative Sentiment Alert Threshold (%)",
        config_parameter="social_dashboard.negative_sentiment_alert_threshold",
        default=15.0,
        help="Trigger a dashboard alert when the share of negative sentiment "
             "exceeds this percentage over the last 30 days.",
    )

    social_dashboard_compliance_alert_enabled = fields.Boolean(
        string="Compliance Rejection Alerts",
        config_parameter="social_dashboard.compliance_alert_enabled",
        default=True,
        help="Notify approvers when a post is rejected by the policy compliance check.",
    )
