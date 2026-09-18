# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Data-source adapters exposing social_planner data to dashboard_vrtl."""

from datetime import timedelta

from odoo import _, api, fields, models

try:
    from odoo.addons.social_dashboard.models.social_brand_scope import brand_domain
except ImportError:
    # social_dashboard is not installed (it is optional): no brand scoping
    def brand_domain(model, brand_path="brand_id"):
        return []


class DashboardSourceSocialCompetitor(models.AbstractModel):
    _name = "dashboard.source.social.competitor"
    _inherit = "dashboard.source.mixin"
    _description = "Social Competitor Benchmark Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Competitor Benchmark",
            "description": "Follower counts and engagement rates per competitor",
            "category": "Social",
            "measures": [
                {"name": "followers", "label": "Followers", "type": "integer"},
                {"name": "engagement_rate", "label": "Engagement Rate", "type": "percentage"},
            ],
            "dimensions": [{"name": "competitor", "label": "Competitor"}],
            "filters": [],
            "chart_types": ["bar_chart", "column_chart", "table"],
            "drill_enabled": True,
            "drill_model": "social_marketing.competitor",
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_data(self, filters=None):
        competitors = self.env["social_marketing.competitor"].search(
            [("active", "=", True)] + brand_domain(self.env["social_marketing.competitor"]))
        return {
            "labels": [c.name for c in competitors],
            "series": [
                {"name": _("Followers"), "values": [c.follower_count for c in competitors]},
                {"name": _("Engagement Rate %"), "values": [c.engagement_rate for c in competitors]},
            ],
        }


class DashboardSourceSocialSentiment(models.AbstractModel):
    _name = "dashboard.source.social.sentiment"
    _inherit = "dashboard.source.mixin"
    _description = "Social Sentiment Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Sentiment",
            "description": "Sentiment distribution of incoming social stream posts",
            "category": "Social",
            "measures": [
                {"name": "count", "label": "Count", "type": "integer"},
            ],
            "dimensions": [{"name": "sentiment", "label": "Sentiment"}],
            "filters": [
                {"name": "date_from", "label": "From", "type": "date"},
                {"name": "date_to", "label": "To", "type": "date"},
            ],
            "chart_types": ["doughnut_chart", "pie_chart", "bar_chart", "kpi"],
            "drill_enabled": True,
            "drill_model": "social_marketing.stream.post",
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_data(self, filters=None):
        filters = filters or {}
        domain = []
        if filters.get("date_from"):
            domain.append(("published_date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            domain.append(("published_date", "<=", filters["date_to"]))
        domain += brand_domain(self.env["social_marketing.stream.post"], "stream_id.brand_id")
        # Cross-chart / global filters (e.g. [['sentiment', '=', 'negative']])
        if filters.get("domain"):
            domain.extend(filters["domain"])
        groups = self.env["social_marketing.stream.post"]._read_group(
            domain=domain, groupby=["sentiment"], aggregates=["__count"])
        counts = {"positive": 0, "neutral": 0, "negative": 0}
        for sentiment, count in groups:
            counts[sentiment or "neutral"] = count
        return {
            "labels": [_("Positive"), _("Neutral"), _("Negative")],
            # Stored selection keys so cross-chart filtering uses the real value
            "values": ["positive", "neutral", "negative"],
            "series": [{
                "name": _("Sentiment"),
                "values": [counts["positive"], counts["neutral"], counts["negative"]],
            }],
        }

    @api.model
    def get_negative_exceeded(self, filters=None):
        threshold = float(self.env["ir.config_parameter"].sudo().get_param(
            "social_dashboard.negative_sentiment_alert_threshold", "15.0"))
        since = fields.Datetime.now() - timedelta(days=30)
        groups = self.env["social_marketing.stream.post"]._read_group(
            domain=[("published_date", ">=", since)] + brand_domain(self.env["social_marketing.stream.post"], "stream_id.brand_id"),
            groupby=["sentiment"], aggregates=["__count"])
        total = 0
        negative = 0
        for sentiment, count in groups:
            total += count
            if sentiment == "negative":
                negative = count
        share = (negative / total * 100.0) if total else 0.0
        exceeded = 1 if share > threshold else 0
        return {
            "labels": [_("Negative share")],
            "series": [{"name": _("Exceeded"), "values": [exceeded]}],
        }


class DashboardSourceSocialBestTime(models.AbstractModel):
    _name = "dashboard.source.social.best_time"
    _inherit = "dashboard.source.mixin"
    _description = "Social Best Time Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Best Time to Post",
            "description": "Suggested best hour to post per channel",
            "category": "Social",
            "measures": [{"name": "hour", "label": "Best Hour", "type": "float"}],
            "dimensions": [{"name": "channel", "label": "Channel"}],
            "filters": [],
            "chart_types": ["table", "bar_chart"],
            "drill_enabled": False,
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_data(self, filters=None):
        plan = self.env["communication.plan"].search(
            [("active", "=", True)] + brand_domain(self.env["communication.plan"]), limit=1)
        if not plan:
            return {"labels": [], "series": []}
        suggestions = self.env["social.planner.ai"].suggest_best_time(plan.id)
        labels = list(suggestions.keys())
        return {
            "labels": labels,
            "series": [{"name": _("Best Hour"), "values": [suggestions[k] for k in labels]}],
        }


class DashboardSourceSocialPlan(models.AbstractModel):
    _name = "dashboard.source.social.plan"
    _inherit = "dashboard.source.mixin"
    _description = "Social Plan Progress Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Plan Progress",
            "description": "Completion percentage per communication plan",
            "category": "Social",
            "measures": [{"name": "completion", "label": "Completion %", "type": "percentage"}],
            "dimensions": [{"name": "plan", "label": "Plan"}],
            "filters": [],
            "chart_types": ["bar_chart", "column_chart", "table"],
            "drill_enabled": True,
            "drill_model": "communication.plan",
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_data(self, filters=None):
        plans = self.env["communication.plan"].search(
            [("active", "=", True)] + brand_domain(self.env["communication.plan"]))
        return {
            "labels": [p.name for p in plans],
            "series": [{
                "name": _("Completion %"),
                "values": [p.completion_percentage for p in plans],
            }],
        }


class DashboardSourceSocialCompliance(models.AbstractModel):
    _name = "dashboard.source.social.compliance"
    _inherit = "dashboard.source.mixin"
    _description = "Social Compliance Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Policy Compliance",
            "description": "Compliance pass rate and rejections for social posts",
            "category": "Social",
            "measures": [
                {"name": "pass_rate", "label": "Pass Rate", "type": "percentage"},
                {"name": "rejected", "label": "Rejected", "type": "integer"},
            ],
            "dimensions": [],
            "filters": [],
            "chart_types": ["kpi"],
            "drill_enabled": False,
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_pass_rate(self, filters=None):
        checked = self.env["social_marketing.post"].search([
            ("approval_state", "in", ["approved", "rejected"]),
        ] + brand_domain(self.env["social_marketing.post"]))
        if not checked:
            rate = 0.0
        else:
            passed = len(checked.filtered(lambda p: p.compliance_check_passed))
            rate = (passed / len(checked)) * 100.0
        return {
            "labels": [_("Compliance pass rate")],
            "series": [{"name": _("Pass rate %"), "values": [rate]}],
        }

    @api.model
    def get_rejected_today(self, filters=None):
        enabled = self.env["ir.config_parameter"].sudo().get_param(
            "social_dashboard.compliance_alert_enabled", "True").lower() in ("true", "1", "yes")
        if not enabled:
            count = 0
        else:
            count = self.env["social_marketing.post"].search_count([
                ("approval_state", "=", "rejected"),
                ("write_date", ">=", fields.Datetime.now() - timedelta(days=1)),
            ] + brand_domain(self.env["social_marketing.post"]))
        return {
            "labels": [_("Rejected")],
            "series": [{"name": _("Rejected"), "values": [count]}],
        }


class DashboardSourceSocialApprovalQueue(models.AbstractModel):
    _name = "dashboard.source.social.approval_queue"
    _inherit = "dashboard.source.mixin"
    _description = "Social Approval Queue Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Approval Queue",
            "description": "Posts pending approval for the content approver",
            "category": "Social",
            "measures": [],
            "dimensions": [
                {"name": "id", "label": "ID"},
                {"name": "name", "label": "Post"},
                {"name": "plan", "label": "Plan"},
                {"name": "approval_state", "label": "Approval State"},
            ],
            "filters": [],
            "chart_types": ["kanban", "table"],
            "drill_enabled": True,
            "drill_model": "social_marketing.post",
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_data(self, filters=None):
        posts = self.env["social_marketing.post"].search([
            ("approval_state", "=", "pending_approval"),
        ] + brand_domain(self.env["social_marketing.post"]), order="create_date desc", limit=50)
        return self._posts_to_kanban(posts)

    @api.model
    def get_my_posts(self, filters=None):
        domain = [("create_uid", "=", self.env.user.id)]
        if filters and filters.get("approval_state"):
            domain.append(("approval_state", "=", filters["approval_state"]))
        domain += brand_domain(self.env["social_marketing.post"])
        posts = self.env["social_marketing.post"].search(domain, order="create_date desc", limit=50)
        return self._posts_to_kanban(posts)

    def _posts_to_kanban(self, posts):
        columns = ["id", "name", "plan", "approval_state", "state", "create_date"]
        rows = []
        for post in posts:
            rows.append({
                "id": post.id,
                "name": post.display_name,
                "plan": post.plan_id.name or "",
                "approval_state": post.approval_state,
                "state": post.state,
                "create_date": post.create_date.strftime("%Y-%m-%d %H:%M") if post.create_date else "",
            })
        return {"columns": columns, "rows": rows, "units": {}}


class DashboardSourceSocialInbox(models.AbstractModel):
    _name = "dashboard.source.social.inbox"
    _inherit = "dashboard.source.mixin"
    _description = "Social Inbox Source"

    @api.model
    def get_schema(self):
        return {
            "name": "Unified Inbox",
            "description": "Unread social messages for the community manager",
            "category": "Social",
            "measures": [],
            "dimensions": [
                {"name": "id", "label": "ID"},
                {"name": "from_name", "label": "From"},
                {"name": "body", "label": "Message"},
                {"name": "media_type", "label": "Platform"},
                {"name": "priority", "label": "Priority"},
            ],
            "filters": [],
            "chart_types": ["kanban", "table"],
            "drill_enabled": True,
            "drill_model": "social_marketing.message",
            "security": {"respects_ir_rule": True, "row_level": True, "safe_for_shared_cache": False},
        }

    @api.model
    def get_data(self, filters=None):
        messages = self.env["social_marketing.message"].search([
            ("state", "=", "unread"),
        ] + brand_domain(self.env["social_marketing.message"], "social_account_id.brand_id"), order="create_date desc", limit=50)
        columns = ["id", "from_name", "body", "media_type", "priority", "create_date"]
        rows = []
        for msg in messages:
            rows.append({
                "id": msg.id,
                "from_name": msg.from_name,
                "body": (msg.body or "")[:80],
                "media_type": msg.media_type,
                "priority": msg.priority,
                "create_date": msg.create_date.strftime("%Y-%m-%d %H:%M") if msg.create_date else "",
            })
        return {"columns": columns, "rows": rows, "units": {}}
