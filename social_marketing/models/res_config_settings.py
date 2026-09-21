# coding: utf-8
# Vertel Sverige AB AGPL-3

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_social_marketing_demo = fields.Boolean('Enable Demo Mode', groups="base.group_system")

    social_publish_rate_limit_delay_seconds = fields.Float(
        string='Default Publish Delay (seconds)',
        config_parameter='social_publish_rate_limit_delay_seconds',
        default=1.0,
        help='Default minimum delay between channel publish jobs. '
             'Per-media overrides can be set on the Publish Rate Limits '
             'model.')

    social_marketing_render_service_url = fields.Char(
        string='Render Service URL',
        config_parameter='social_marketing.render_service_url',
        help='Base URL of the Node render service for image templates, '
             'e.g. http://render-odoo:8600')

    social_marketing_dm_retention_days = fields.Integer(
        string='Direct Message Retention (days)',
        config_parameter='social_marketing.dm_retention_days',
        default=90,
        help='How long private inbox items (direct messages) are kept before '
             'the retention cron deletes them. Direct messages are personal '
             'data; keeping them forever is not a neutral default. Set to 0 '
             'to disable the deletion. Public items are never deleted by it.')

    social_marketing_render_service_token = fields.Char(
        string='Render Service Token',
        config_parameter='social_marketing.render_service_token',
        help='Bearer token used to authenticate render service calls. '
             'Stored via ir.config_parameter; set from pillar in production.')


# ────────────────────────────────────────────────────────────────────────
# Background Jobs — cron-administration (samma mönster som ai_agent_core)
# ────────────────────────────────────────────────────────────────────────

SOCIAL_MARKETING_CRON_NAMES = [
    'Social: Publish Scheduled Posts',
    'Social: Delete Expired Direct Messages',
]


class ResConfigSettingsSocialCron(models.TransientModel):
    _inherit = 'res.config.settings'

    social_marketing_cron_line_ids = fields.One2many(
        'social.marketing.cron.line', 'settings_id', string='Cron-rader')

    @api.model
    def get_values(self):
        res = super().get_values()
        crons = self.env['ir.cron'].search(
            [('cron_name', 'in', SOCIAL_MARKETING_CRON_NAMES)], order='cron_name')
        res['social_marketing_cron_line_ids'] = [(0, 0, {
            'cron_id': cron.id,
            'cron_active': cron.active,
            'cron_interval_number': cron.interval_number,
            'cron_interval_type': cron.interval_type,
        }) for cron in crons]
        return res

    def set_values(self):
        super().set_values()
        for line in self.social_marketing_cron_line_ids:
            if line.cron_id:
                line.cron_id.write({
                    'active': line.cron_active,
                    'interval_number': line.cron_interval_number,
                    'interval_type': line.cron_interval_type,
                })


class SocialMarketingCronLine(models.TransientModel):
    """Per-cron konfigurationsrad i Background Jobs-blocket."""
    _name = 'social.marketing.cron.line'
    _description = 'Social Marketing cron configuration line'

    settings_id = fields.Many2one('res.config.settings', ondelete='cascade')
    cron_id = fields.Many2one('ir.cron', string='Cron', required=True,
                              ondelete='cascade')
    cron_name = fields.Char(related='cron_id.cron_name', string='Namn',
                            readonly=True)
    cron_active = fields.Boolean(string='Aktiv', default=True)
    cron_interval_number = fields.Integer(string='Intervall', default=1)
    cron_interval_type = fields.Selection([
        ('minutes', 'Minuter'),
        ('hours', 'Timmar'),
        ('days', 'Dagar'),
        ('weeks', 'Veckor'),
        ('months', 'Månader'),
    ], string='Period', default='days')
    cron_lastcall = fields.Datetime(related='cron_id.lastcall',
                                    string='Senaste körning', readonly=True)
    cron_failure_count = fields.Integer(related='cron_id.failure_count',
                                        string='Fel', readonly=True)
    cron_code = fields.Text(related='cron_id.code', string='Metod',
                            readonly=True)

    def action_run_now(self):
        """Kör cron direkt."""
        self.ensure_one()
        if not self.cron_id:
            return False
        model_name = self.cron_id.model
        code = self.cron_id.code
        if model_name and code:
            model = self.env[model_name]
            if code.startswith('model.'):
                method = code[len('model.'):]
                if hasattr(model, method):
                    getattr(model, method)()
        self.cron_id._trigger(at=fields.Datetime.now())
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cron triggad',
                'message': f'{self.cron_name} körs nu.',
                'type': 'success',
            },
        }
