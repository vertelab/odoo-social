# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

import json
import logging
import subprocess

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SocialPlannerAI(models.AbstractModel):
    """ AI-helper för social_planner — integration med ai.coworker (ai_agent_core) för
    innehållsgenerering, sentimentanalys och optimering. """

    _name = 'social.planner.ai'
    _description = 'Social Planner AI Helper'

    @api.model
    def generate_post_content(self, post_id):
        """ Generera innehåll för en social_marketing.post med AI.
        Använder ai.coworker för att skapa innehåll baserat på planens
        målgrupp, policyns tonalitet, och radens tema. """
        post = self.env['social_marketing.post'].browse(post_id)
        if not post.exists():
            return False

        # Bygg prompt från kontext
        system_prompt = self._build_system_prompt(post)
        user_prompt = self._build_user_prompt(post)

        # Försök anropa ai.coworker om tillgängligt
        try:
            generated = self._call_ai_agent(system_prompt, user_prompt)
            if generated:
                post.write({
                    'message': generated,
                    'ai_generated': True,
                    'ai_prompt': f"System: {system_prompt}\n\nUser: {user_prompt}",
                })
                return True
        except Exception as e:
            _logger.warning("AI generation failed for post %s: %s", post.id, str(e))
            # Fallback: markera att AI försöktes men misslyckades
            post.write({
                'ai_generated': False,
                'ai_prompt': f"System: {system_prompt}\n\nUser: {user_prompt}",
            })
        return False

    @api.model
    def _build_system_prompt(self, post):
        """ Bygg systemprompt från policy-kontext. """
        policy = post.policy_id
        plan = post.plan_id
        line = post.plan_line_id

        parts = []
        parts.append("You are a professional social media content creator.")

        if policy:
            parts.append(f"Tone of voice: {policy.tone_of_voice or 'Professional and engaging'}")
            parts.append(f"Brand voice: {policy.brand_voice_guidelines or 'Clear and concise'}")
            if policy.hashtag_policy:
                parts.append(f"Hashtag rules: {policy.hashtag_policy}")
            if policy.prohibited_content:
                parts.append(f"Avoid these words/topics: {policy.prohibited_content}")

        if plan:
            parts.append(f"Target audience: {plan.target_audience or 'General audience'}")

        if line:
            channel = dict(line._fields['channel']._description_selection(self.env)).get(line.channel, line.channel)
            content_type = dict(line._fields['content_type']._description_selection(self.env)).get(line.content_type, line.content_type)
            parts.append(f"Channel: {channel}")
            parts.append(f"Content type: {content_type}")

        return '\n'.join(parts)

    @api.model
    def _build_user_prompt(self, post):
        """ Bygg användarprompt från plan/rad-kontext. """
        plan = post.plan_id
        line = post.plan_line_id

        parts = []

        if plan:
            parts.append(f"Create a social media post for the campaign: '{plan.name}'")
            if plan.goal:
                parts.append(f"Campaign goals: {plan.goal}")

        if line:
            parts.append(f"Theme: {line.theme or 'General update'}")
            if line.notes:
                parts.append(f"Additional notes: {line.notes}")

        if post and post.message:
            parts.append(f"Draft content to refine: {post.message}")

        parts.append("Write engaging, platform-appropriate content ready to post.")
        parts.append("Include relevant emojis if the brand voice allows it.")

        return '\n'.join(parts)

    @api.model
    def _call_ai_agent(self, system_prompt, user_prompt):
        """ Anropa ai.coworker (ai_agent_core) för att generera innehåll.

        Den gamla ai_agent-modulen (ai.agent.trigger_prompt) ersattes av
        ai_agent_core — innehållsgenerering görs via ai.coworker.run(). """
        # Hitta en aktiv AI-coworker att använda
        coworker = self.env['ai.coworker'].search([
            ('active', '=', True),
        ], limit=1)

        if not coworker:
            _logger.warning("No AI coworker found for content generation")
            return False

        try:
            return coworker.run(
                prompt=user_prompt,
                system_prompt=system_prompt,
            )
        except Exception as e:
            _logger.warning("AI coworker call failed: %s", str(e))
            return False

    @api.model
    def analyze_sentiment(self, text):
        """ Analysera sentiment för en text (kommentar/post).
        Returnerar: {'sentiment': 'positive'|'neutral'|'negative', 'score': float} """
        if not text:
            return {'sentiment': 'neutral', 'score': 0.0}

        system_prompt = (
            "You are a sentiment analysis tool. "
            "Classify the sentiment of the following text as 'positive', 'neutral', or 'negative'. "
            "Respond with ONLY a JSON object: {\"sentiment\": \"positive|neutral|negative\", \"score\": 0.0-1.0}"
        )

        try:
            agent = self.env['ai.agent'].search([
                ('generic_agent', '=', True),
            ], limit=1) or self.env['ai.agent'].search([], limit=1)

            if agent:
                result = agent.trigger_prompt(message=f"{system_prompt}\n\nText: {text}")
                if result:
                    try:
                        return json.loads(result)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return {'sentiment': 'neutral', 'score': 0.0}

    @api.model
    def suggest_best_time(self, plan_id):
        """ Föreslå bästa tid att posta baserat på historisk engagement-data.
        Returnerar dict med kanal → tid. """
        plan = self.env['communication.plan'].browse(plan_id)
        if not plan.exists():
            return {}

        # Analysera historisk engagement per kanal (senaste 90 dagar)
        suggestions = {}
        channels = ['linkedin', 'facebook', 'instagram', 'twitter', 'youtube']

        for channel in channels:
            posts = self.env['social_marketing.post'].search([
                ('plan_line_id.plan_id.policy_id', '=', plan.policy_id.id),
                ('state', '=', 'posted'),
                ('create_date', '>=', fields.Datetime.now() - fields.Datetime.timedelta(days=90)),
            ])

            if not posts:
                suggestions[channel] = 10.0  # Default 10:00
                continue

            # Enkel heuristik — hitta timmen med högst average engagement
            # (I verklig produktion skulle detta vara mer sofistikerat)
            engagement_by_hour = {}
            for post in posts:
                hour = post.scheduled_date.hour if post.scheduled_date else 10
                engagement_by_hour[hour] = engagement_by_hour.get(hour, 0) + post.engagement

            if engagement_by_hour:
                best_hour = max(engagement_by_hour, key=engagement_by_hour.get)
                suggestions[channel] = float(best_hour)
            else:
                suggestions[channel] = 10.0

        return suggestions

    @api.model
    def suggest_hashtags(self, post_id):
        """ Föreslå hashtags baserat på innehåll och policy. """
        post = self.env['social_marketing.post'].browse(post_id)
        if not post.exists() or not post.message:
            return []

        system_prompt = (
            "You are a social media hashtag expert. "
            "Based on the post content and brand guidelines, suggest 3-5 relevant hashtags. "
            "Respond with ONLY a JSON array: [\"#tag1\", \"#tag2\", ...]"
        )

        user_prompt = f"Content: {post.message}\n"
        if post.policy_id and post.policy_id.hashtag_policy:
            user_prompt += f"Hashtag rules: {post.policy_id.hashtag_policy}"

        try:
            agent = self.env['ai.agent'].search([
                ('generic_agent', '=', True),
            ], limit=1) or self.env['ai.agent'].search([], limit=1)

            if agent:
                result = agent.trigger_prompt(message=f"{system_prompt}\n\n{user_prompt}")
                if result:
                    try:
                        hashtags = json.loads(result)
                        if isinstance(hashtags, list):
                            return hashtags
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return []

    # ------------------------------------------------------------------
    # Trend research via the last30days skill
    # ------------------------------------------------------------------

    @api.model
    def research_trends(self, topic):
        """ Run a last30days trend research for a listening topic.

        Uses the pi CLI headless (with the last30days skill installed in
        /usr/local/share/pi/skills) to produce a grounded 30-day research
        report. The command is configurable via the ir.config_parameter
        ``social_planner.research_command`` (default: ``pi -p --mode json``),
        so it can be pointed at opencode/hermes or a remote runner.

        Falls back to the ai.agent trigger_prompt when the CLI is not
        available or fails.

        :param topic: social_marketing.listening.topic record
        :return: report text (HTML) or False
        """
        self.ensure_one()
        if isinstance(topic, int):
            topic = self.env['social_marketing.listening.topic'].browse(topic)
        if not topic.exists():
            return False

        prompt = self._build_research_prompt(topic)
        command = self._get_research_command()

        report = self._run_research_command(command, prompt)
        if report:
            return report

        # Fallback: ai.agent (plain LLM — no live sources, only methodology)
        _logger.warning("Research CLI unavailable, falling back to ai.agent for topic %s", topic.name)
        system_prompt = (
            "You are a social media trend researcher. Use the last30days methodology: "
            "search Reddit, X/Twitter, YouTube, Hacker News, Bluesky and the web for "
            "what people actually say about the topic in the last 30 days, then produce "
            "a grounded summary ranked by engagement signals. Be explicit about what "
            "could not be verified live."
        )
        return self._call_ai_agent(system_prompt, prompt)

    @api.model
    def _get_research_command(self):
        """ Return the research CLI command (list) from ir.config_parameter. """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'social_planner.research_command', 'pi -p --mode json')
        parts = raw.split()
        if not parts:
            return ['pi', '-p', '--mode', 'json']
        return parts

    @api.model
    def _build_research_prompt(self, topic):
        """ Build the last30days prompt from the topic. """
        keywords = (topic.keywords or '').strip()
        exclude = (topic.exclude_keywords or '').strip()

        parts = []
        parts.append('Use the last30days skill to research what people actually say '
                     'about this topic over the last 30 days.')
        parts.append('Topic: %s' % topic.name)
        if keywords:
            parts.append('Keywords:\n%s' % keywords)
        if exclude:
            parts.append('Exclude these keywords:\n%s' % exclude)
        if topic.policy_id:
            parts.append('Brand context: %s' % (topic.policy_id.name or ''))
        parts.append('Return the research report as structured text with sections and citations.')
        return '\n\n'.join(parts)

    @api.model
    def _run_research_command(self, command, prompt):
        """ Run the research CLI headless and capture the report.

        Supports --mode json output (pi): the report is extracted from the
        JSON response (message/result), otherwise raw stdout is used.
        """
        try:
            proc = subprocess.run(
                command + [prompt],
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError:
            _logger.warning("Research command not found: %s", command[0])
            return False
        except subprocess.TimeoutExpired:
            _logger.warning("Research command timed out: %s", command[0])
            return False
        except Exception as e:
            _logger.warning("Research command error: %s", str(e))
            return False

        if proc.returncode != 0:
            _logger.warning("Research command exited %s: %s", proc.returncode, (proc.stderr or '')[:500])
            # pi returns non-zero on some agent errors; keep stdout if present
            if not proc.stdout.strip():
                return False

        out = (proc.stdout or '').strip()
        if not out:
            return False

        # Try to extract report from JSON output (pi --mode json)
        if '--mode' in command and 'json' in command:
            try:
                data = json.loads(out)
                # pi json mode: the assistant text is usually in .message or .result
                for key in ('message', 'result', 'text', 'output'):
                    if isinstance(data, dict) and data.get(key):
                        return '<pre>%s</pre>' % data[key]
                if isinstance(data, dict) and data.get('messages'):
                    msgs = data['messages']
                    last = msgs[-1] if isinstance(msgs, list) else None
                    if isinstance(last, dict) and last.get('content'):
                        content = last['content']
                        if isinstance(content, str):
                            return '<pre>%s</pre>' % content
                        if isinstance(content, list):
                            text = '\n'.join(c.get('text', '') for c in content if isinstance(c, dict))
                            if text:
                                return '<pre>%s</pre>' % text
            except json.JSONDecodeError:
                pass

        # Plain text output — escape for HTML field
        return '<pre>%s</pre>' % out
