# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


_TREND_RESEARCHER_DESCRIPTION = (
    "You are Trend Researcher, a social media trend research specialist. "
    "You use the last30days skill to find out what people actually say about "
    "a topic in the last 30 days across Reddit, X/Twitter, YouTube, TikTok, "
    "Hacker News, Bluesky and the web, and you produce grounded reports with "
    "citations and engagement signals. When the user asks about a brand, "
    "product, topic or competitor, first check whether a listening topic "
    "(social_marketing.listening.topic) exists for it — if it does, use it "
    "and save the report to trend_research_report with "
    "research_state='done'; otherwise research the topic directly and present "
    "the report. Be explicit about what could not be verified live. Never "
    "invent quotes, handles or engagement numbers.\n\n"
    "SCHEDULED TASK (when you are run automatically): search for listening "
    "topics that need research — research_state in ('draft', 'error') or "
    "empty trend_research_report — for active brands, run last30days_research "
    "on each and save the report (trend_research_report, "
    "research_state='done'). Skip topics in 'running' state. Work through "
    "them one at a time. If nothing needs research, reply briefly that no "
    "topics needed research."
)


class AICoworker(models.Model):
    """Trend Researcher seed + rate-limit guard for scheduled runs.

    Rate-limit guard: ai_agent_core has BOTH a global 5-minute cron
    (cron_scheduled_quests) and a per-quest ir.cron (created by
    ``_ensure_cron``) that both call ``action_run_scheduled()``. Without a
    guard a cron-enabled quest runs twice — e.g. every 5 minutes from the
    global cron in addition to its own configured interval (the Trend
    Researcher would re-run research constantly). This override skips the run
    when the quest already ran within the cron init type's configured
    interval, so the first invocation after the interval (whichever cron
    fires first) wins and the other is skipped.
    """

    _inherit = 'ai.coworker'

    _CRON_INTERVAL_MINUTES = {
        'minutes': 1,
        'hours': 60,
        'days': 1440,
        'weeks': 10080,
        'months': 43200,
    }

    @api.model
    def _ensure_trend_researcher_seed(self):
        """Idempotently (re)apply the Trend Researcher seed fields.

        The record itself lives in a noupdate=1 data block (protecting user
        edits), but ir_model_data.noupdate=True also shields it from
        noupdate=0 data blocks — so seed fields that must follow the module
        (description, standing tool rules, cron model) are applied via this
        post-load hook instead, exactly like ai_agent_core's
        ``_ensure_default_coworker``. Runs on install AND upgrade.
        """
        rec = self.env.ref(
            'social_planner.coworker_social_trend_researcher',
            raise_if_not_found=False)
        if not rec:
            return True
        model = self.env.ref(
            'social_planner.model_social_marketing_listening_topic',
            raise_if_not_found=False)
        rec.write({
            'description': _TREND_RESEARCHER_DESCRIPTION,
            'auto_allowed_tools':
                '["last30days_research", "odoo_search", '
                '"odoo_write social_marketing.listening.topic"]',
            'cron_model_id': model.id if model else False,
            'model_ids': [(6, 0, [model.id])] if model else [(5, 0, 0)],
        })
        # Agenten ska använda en modell som finns på plattformen
        # (data-drivet: billigaste aktiva ai.model — samma sökning som
        # core.provider.get_cheapest_model, men utan HTTP-request-beroende
        # så den fungerar i post-load-hooken). Sätts bara om den saknas —
        # användarens senare modellval respekteras.
        agent = rec.agent_ids[:1].agent_id
        if agent and not agent.model_id:
            model_rec = self.env['ai.model'].sudo().search([
                ('active', '=', True),
                ('status', '=', 'active'),
            ], order='sys_multiplier asc, cost_input_1k asc, id asc',
                limit=1)
            if model_rec:
                agent.write({'model_id': model_rec.id})
                _logger.info(
                    'Assigned platform model %s to agent %s',
                    model_rec.name, agent.name)
        return True

    def action_run_scheduled(self):
        """Skip re-running a cron quest within its configured interval."""
        self.ensure_one()
        cron_init = self.init_type_ids.filtered(
            lambda it: it.init_type == 'cron' and it.enabled)[:1]
        if cron_init and self.last_run:
            interval_minutes = self._CRON_INTERVAL_MINUTES.get(
                cron_init.cron_interval_type or 'hours', 60)
            interval_minutes *= cron_init.cron_interval_number or 1
            last = fields.Datetime.from_string(self.last_run)
            elapsed_minutes = (
                fields.Datetime.now() - last).total_seconds() / 60.0
            if elapsed_minutes < interval_minutes:
                _logger.info(
                    'Skipping scheduled run for %s (last run %s, %s min ago, '
                    'interval %s min)', self.name, self.last_run,
                    round(elapsed_minutes, 1), interval_minutes)
                return {'status': 'skipped', 'reason': 'within_interval'}
        return super().action_run_scheduled()
