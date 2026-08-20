# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

from odoo import _, api, fields, models


class SocialMarketingListeningTopic(models.Model):
    """ Keyword/hashtag monitoring for social listening.

    Since 1.1: Trend research via the last30days skill — the topic can be
    researched through the pi/opencode agent (which has the last30days
    skill installed) and the grounded 30-day report is stored on the record.
    """

    _name = 'social_marketing.listening.topic'
    _description = 'Social Listening Topic'
    _order = 'name'

    name = fields.Char('Topic Name', required=True)
    active = fields.Boolean('Active', default=True)
    keywords = fields.Text('Keywords',
        help="Keywords or phrases to monitor, one per line. Supports hashtags with #.")
    exclude_keywords = fields.Text('Exclude Keywords')
    policy_id = fields.Many2one('communication.policy', string='Policy')
    stream_ids = fields.Many2many('social_marketing.stream', string='Streams')
    company_id = fields.Many2one('res.company', string='Company',
        default=lambda self: self.env.company)
    mention_count = fields.Integer('Mentions (24h)', compute='_compute_mention_count')
    last_checked = fields.Datetime('Last Checked')

    # --- Trend research (last30days skill) ---
    research_state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], string='Research State', default='draft', readonly=True, copy=False)
    trend_research_report = fields.Html('Trend Research Report (30 days)', readonly=True, copy=False)
    last_researched = fields.Datetime('Last Researched', readonly=True, copy=False)
    research_duration_minutes = fields.Integer('Research Duration (min)', readonly=True, copy=False)

    @api.depends('stream_ids')
    def _compute_mention_count(self):
        for topic in self:
            topic.mention_count = 0  # Full implementation deferred

    def action_research_trends(self):
        """ Run a last30days trend research for this topic via the AI agent
        (pi headless with the last30days skill) and store the report. """
        ai_helper = self.env['social.planner.ai']
        for topic in self:
            if topic.research_state == 'running':
                continue
            topic.write({'research_state': 'running'})
            try:
                report = ai_helper.research_trends(topic)
                if report:
                    topic.write({
                        'trend_research_report': report,
                        'research_state': 'done',
                        'last_researched': fields.Datetime.now(),
                    })
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Trend research complete'),
                            'message': _('The last30days research report for "%s" is ready.', topic.name),
                            'type': 'success',
                            'next': {'type': 'ir.actions.act_window_reload'},
                        },
                    }
                topic.write({'research_state': 'error'})
            except Exception as e:
                topic.write({'research_state': 'error'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Trend research failed'),
                        'message': _('Could not research "%s": %s', topic.name, str(e)),
                        'type': 'danger',
                    },
                }
        return True

    def action_clear_report(self):
        """ Clear the stored research report. """
        self.write({
            'trend_research_report': False,
            'research_state': 'draft',
            'last_researched': False,
        })
