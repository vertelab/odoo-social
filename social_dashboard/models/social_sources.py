# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Data-source adapters exposing social_marketing data to dashboard_vrtl."""

from odoo import _, api, models
from odoo.exceptions import AccessError

from .social_brand_scope import brand_domain


class DashboardSourceSocialEngagement(models.AbstractModel):
    _name = "dashboard.source.social.engagement"
    _inherit = "dashboard.source.mixin"
    _description = "Social Engagement Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Social Engagement",
            "description": "Engagement aggregated per channel from social live posts",
            "category": "Social",
            "measures": [
                {"name": "engagement", "label": "Engagement", "type": "integer"},
                {"name": "post_count", "label": "Posts", "type": "integer"},
            ],
            "dimensions": [
                {"name": "channel", "label": "Channel"},
            ],
            "filters": [
                {"name": "date_from", "label": "From", "type": "date"},
                {"name": "date_to", "label": "To", "type": "date"},
            ],
            "chart_types": ["bar_chart", "column_chart", "kpi", "table"],
            "drill_enabled": True,
            "drill_model": "social_marketing.live.post",
            "security": {
                "respects_ir_rule": True,
                "row_level": True,
                "safe_for_shared_cache": False,
            },
        }

    @api.model
    def get_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get("date_from"):
            domain.append(("post_id.published_date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            domain.append(("post_id.published_date", "<=", filters["date_to"]))
        domain += brand_domain(self.env["social_marketing.live.post"], "social_account_id.brand_id")
        # Cross-chart / global filters (e.g. [['social_account_id.media_type', '=', 'linkedin']])
        if filters.get("domain"):
            domain.extend(filters["domain"])

        group_records = self.env["social_marketing.live.post"]._read_group(
            domain=domain,
            groupby=["social_account_id"],
            aggregates=["engagement:sum", "__count"],
            limit=1000,
        )
        by_channel = {}
        for account, engagement, count in group_records:
            channel = (account.media_type or "other") if account else "other"
            agg = by_channel.setdefault(channel, {"engagement": 0, "count": 0})
            agg["engagement"] += engagement or 0
            agg["count"] += count or 0

        channels = sorted(by_channel)
        return {
            "labels": channels,
            "series": [
                {"name": _("Engagement"), "values": [by_channel[c]["engagement"] for c in channels]},
                {"name": _("Posts"), "values": [by_channel[c]["count"] for c in channels]},
            ],
        }


class DashboardSourceSocialRoi(models.AbstractModel):
    _name = "dashboard.source.social.roi"
    _inherit = "dashboard.source.mixin"
    _description = "Social ROI Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Social ROI",
            "description": "Clicks, leads and orders attributed to social posts via UTM sources",
            "category": "Social",
            "measures": [
                {"name": "clicks", "label": "Clicks", "type": "integer"},
                {"name": "leads", "label": "Leads", "type": "integer"},
                {"name": "orders", "label": "Orders", "type": "integer"},
            ],
            "dimensions": [{"name": "source", "label": "UTM Source"}],
            "filters": [],
            "chart_types": ["table", "bar_chart", "kpi"],
            "drill_enabled": False,
            "security": {
                "respects_ir_rule": True,
                "row_level": True,
                "safe_for_shared_cache": False,
            },
        }

    def _module_installed(self, name):
        return bool(self.env["ir.module.module"].sudo().search(
            [("name", "=", name), ("state", "=", "installed")], limit=1))

    @api.model
    def get_data(self, filters=None):
        filters = filters or {}
        sources = self.env["social_marketing.post"].search(
            [("source_id", "!=", False)] + brand_domain(self.env["social_marketing.post"])).source_id
        if not sources:
            return {"labels": [], "series": [
                {"name": _("Clicks"), "values": []},
                {"name": _("Leads"), "values": []},
                {"name": _("Orders"), "values": []},
            ]}
        source_ids = sources.ids
        clicks = self._clicks_by_source(source_ids)
        leads = self._leads_by_source(source_ids) if self._module_installed("crm") else {}
        orders = self._orders_by_source(source_ids) if self._module_installed("sale") else {}
        return {
            "labels": [s.name or s.handle or str(s.id) for s in sources],
            "series": [
                {"name": _("Clicks"), "values": [clicks.get(s.id, 0) for s in sources]},
                {"name": _("Leads"), "values": [leads.get(s.id, 0) for s in sources]},
                {"name": _("Orders"), "values": [orders.get(s.id, 0) for s in sources]},
            ],
        }

    @api.model
    def get_clicks_total(self, filters=None):
        sources = self.env["social_marketing.post"].search(
            [("source_id", "!=", False)] + brand_domain(self.env["social_marketing.post"])).source_id
        if not sources:
            return {"labels": [_("Clicks")], "series": [{"name": _("Clicks"), "values": [0]}]}
        total = sum(self._clicks_by_source(sources.ids).values())
        return {"labels": [_("Clicks")], "series": [{"name": _("Clicks"), "values": [total]}]}

    def _clicks_by_source(self, source_ids):
        self.env.cr.execute(
            """
            SELECT link.source_id, COUNT(DISTINCT click.id)
              FROM link_tracker_click click
              JOIN link_tracker link ON link.id = click.link_id
             WHERE link.source_id = ANY(%s)
             GROUP BY link.source_id
            """,
            [list(source_ids)],
        )
        return dict(self.env.cr.fetchall())

    def _leads_by_source(self, source_ids):
        try:
            groups = self.env["crm.lead"]._read_group(
                [("source_id", "in", source_ids)],
                groupby=["source_id"], aggregates=["__count"])
            return {source.id: count for source, count in groups if source}
        except AccessError:
            # User has no CRM access: hide the leads column gracefully
            return {}

    def _orders_by_source(self, source_ids):
        if "source_id" not in self.env["sale.order"]._fields:
            return {}
        try:
            groups = self.env["sale.order"]._read_group(
                [("source_id", "in", source_ids)],
                groupby=["source_id"], aggregates=["__count"])
            return {source.id: count for source, count in groups if source}
        except AccessError:
            return {}
