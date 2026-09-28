# Plan: Odoo Social — Modulöversyn & Förbättringsförslag

## Context

Genomgång av hela odoo-social (6 moduler, 100 filer, 465 symboler) för att identifiera
förbättringsområden. Projektet är en social media management-svit för Odoo 18 CE.

## Sammanfattning av fynd

### Kritiska problem
1. **Duplicerade `.p.py`-filer** — `social_marketing_post.p.py`, `social_marketing_account.p.py`, `__manifest__.p.py` är identiska kopior av originalen. Orsakar förvirring och dubbel import-risk.
2. **Säkerhetshål i LinkedIn-lösenord** — `linkedin_password` är en `fields.Char` utan kryptering. Bör vara `fields.Encrypted` eller `fields.Binary`.
3. **Säkerhetshål i Facebook tokens** — `facebook_page_access_token` lagras som `fields.Char(readonly=True)` helt i klartext.
4. **Ingen rate limiting / throttling** — Samtliga API-anrop mot externa tjänster saknar rate limiting. Risk för att bli bannad från Facebook/LinkedIn vid burst.
5. **Inga enhetstester förutom social_planner** — Endast `social_planner/tests/test_models.py` finns. Facebook, Instagram, LinkedIn, Postiz, och core social_marketing har 0 tester.

### Arkitekturella problem
6. **`SocialPlannerDashboard` som AbstractModel** — Dashboard-modellen (`social.planner.dashboard`) är en `models.AbstractModel` med compute-metoder som skriver till `self` (som om det vore en vanlig model). AbstractModel har inga records. Metoderna kommer alltid att misslyckas vid anrop.
7. **`social_marketing_post.p.py` duplicerat arv** — `social_marketing_post.py` både ärver `social_marketing.post.template` OCH har `_inherit = 'social_marketing.post.template'` på samma modell. Dubbelt arv.
8. **Hårdkodade API-versioner** — Facebook: `v21.0`, LinkedIn: `202505`. Dessa kommer att bli inaktuella.
9. **`linkedin_auth_method` blandar auth och posting** — Varje live_post måste kolla `account_id.linkedin_auth_method` och routa till rätt post-metod. Bättre med strategy pattern / polymorfism.
10. **Ingen proper async/queue** — `_action_post()` kör alla live_posts synkront i en loop. Om 10 konton ska postas tar det 10x tiden. Borde använda Odoos `queue.job` eller async.

### Kodkvalitetsproblem
11. **Hårdkodade strängar i JavaScript** — Inga i18n-strängar i JS-koden.
12. **Inga docstrings på många metoder** — T.ex. `_build_postiz_payload`, `_postiz_api_url`.
13. **Blandning av svenska och engelska kommentarer** — "Bygg payload" (Facebook), "Skicka svar via LinkedIn API" (LinkedIn inbox), "Hämta LinkedIn-meddelanden".
14. **`import __import__('logging')` anti-pattern** — `social_marketing_linkedin_inbox.py` och `social_marketing_message.py` använder `__import__('logging')` inline istället för top-level import.
15. **Saknade `company_id` på flera modeller** — `social_marketing.message.tag`, `social_marketing.competitor.tag` saknar company_id för multi-company.
16. **`plan_line_id` på post med `ondelete='set null'`** — Om en plan line raderas blir posten kvar men oanvändbar. Borde ha cascade eller warning.

### Funktionella förbättringsmöjligheter
17. **Postiz saknar `_fetch_inbox_messages` och `_send_inbox_reply`** — Returnerar 0/False hårdkodat. Borde implementeras eller dokumenteras bättre.
18. **Lyssnande (`social_marketing.listening.topic`)** — `_compute_mention_count` returnerar alltid 0 med kommentaren "Full implementation deferred".
19. **AI-integrationen är rudimentär** — `_call_ai_agent` gör en enkel `agent.trigger_prompt()` utan strukturerad output-parsing, retry, eller felhantering.
20. **Konkurrentanalys manuell** — `action_update_metrics` tar manuella värden. Borde ha automatisk fetch via API:er.
21. **Playwright session save async** — `action_open_playwright_login` startar en subprocess men sparar session asynkront via en cron-trigger. Race condition risk.

---

## Approach

Jag rekommenderar att åtgärda problemen i tre faser:

### Fas 1: Kritiska säkerhets- och buggfixar (bör göras först)
- Ta bort `.p.py`-filer
- Kryptera lösenord/tokens
- Fixa `SocialPlannerDashboard` AbstractModel
- Lägg till rate limiting

### Fas 2: Kodkvalitet och tester
- Lägg till tester för alla moduler
- Rensa språkblandning (allt till engelska)
- Fixa `__import__` anti-pattern
- Lägg till docstrings
- Lägg till `company_id` på saknade modeller

### Fas 3: Funktionella förbättringar
- Implementera lyssnande (mention count)
- Förbättra AI-integration med strukturerad output
- Gör Postiz inbox funktionell eller dokumentera begränsningen tydligt
- Strategy pattern för LinkedIn auth
- Async posting via queue.job

---

## Files to modify

### Fas 1 — Ta bort duplicerade filer
- `social_marketing/models/social_marketing_post.p.py` — **DELETE** (duplicate of social_marketing_post.py)
- `social_marketing/models/social_marketing_account.p.py` — **DELETE** (duplicate of social_marketing_account.py)
- `social_marketing/__manifest__.p.py` — **DELETE** (duplicate of __manifest__.py)

### Fas 1 — Kryptera känsliga fält
- `social_marketing_linkedin/models/social_marketing_account.py` — Ändra `linkedin_password` från `fields.Char` → `fields.Binary(string='LinkedIn Password', groups='base.group_system')` med manuell kryptering eller använd `fields.Encrypted` om tillgängligt.
- `social_marketing_facebook/models/social_marketing_account.py` — Ändra `facebook_page_access_token` till `groups='base.group_system'` eller kryptera.

### Fas 1 — Fixa AbstractModel
- `social_planner/models/social_planner_dashboard.py` — Ändra från `AbstractModel` till `TransientModel` ELLER gör compute-metoderna till `@api.model` som returnerar recordset istället för att skriva till self.

### Fas 1 — Rate limiting
- `social_marketing_facebook/models/social_marketing_live_post.py` — Lägg till `time.sleep()` eller rate-limit-decorator
- `social_marketing_facebook/models/social_marketing_account.py` — Rate limit på statistik-fetch
- `social_marketing_linkedin/models/social_marketing_live_post.py` — Rate limit på LinkedIn API-anrop

### Fas 2 — Kodkvalitet
- `social_planner/models/social_marketing_linkedin_inbox.py` — Fixa `__import__('logging')` → `import logging; _logger = logging.getLogger(__name__)`
- `social_planner/models/social_marketing_message.py` — Samma fix för inline import
- `social_marketing_linkedin/models/social_marketing_account.py` — Lägg till `_LINKEDIN_ENDPOINT` som config-parameter istället för hårdkodad i `social_marketing_media`

### Fas 2 — Tester
Skapa testfiler för:
- `social_marketing/tests/test_social_post.py`
- `social_marketing/tests/test_social_account.py`
- `social_marketing_facebook/tests/test_facebook.py`
- `social_marketing_instagram/tests/test_instagram.py`
- `social_marketing_linkedin/tests/test_linkedin.py`
- `social_marketing_postiz/tests/test_postiz.py`

### Fas 3 — Funktionella förbättringar
- `social_planner/models/social_planner_ai.py` — Förbättra med retry, strukturerad output, bättre felhantering
- `social_planner/models/social_marketing_listening_topic.py` — Implementera `_compute_mention_count`
- `social_marketing_postiz/models/social_marketing_account.py` — Förbättra inbox-stubbar
- `social_marketing_linkedin/models/social_marketing_live_post.py` — Strategy pattern för auth

---

## Reuse

Befintlig kod som kan återanvändas:
- `social_marketing_account._compute_trend()` — redan implementerad trend-beräkning
- `social_marketing_post._check_post_access()` — valideringslogik
- `social_marketing_live_post._filter_by_media_types()` — filtreringsmönster
- `social_marketing_message._send_reply_platform()` — dispatch-mönster för inbox
- `social_marketing_postiz._find_or_create_postiz_media()` — provider-mappning

---

## Steps

### Fas 1 — Kritiska fixar

- [ ] 1.1 Ta bort `.p.py` duplikatfiler och verifiera att inga imports pekar på dem
- [ ] 1.2 Kryptera `linkedin_password` (ändra från `fields.Char` till `fields.Binary` med base64 + manuell XOR eller använd `fields.Encrypted`)
- [ ] 1.3 Skydda `facebook_page_access_token` (lägg till `groups='base.group_system'`)
- [ ] 1.4 Fixa `SocialPlannerDashboard` — ändra `AbstractModel` → `TransientModel` och gör compute-metoder statiska
- [ ] 1.5 Lägg till enkel rate limiting wrapper-funktion för API-anrop (t.ex. `@api_rate_limit(calls=10, period=60)`)

### Fas 2 — Kodkvalitet och tester

- [ ] 2.1 Standardisera språk till engelska i alla kommentarer och log-meddelanden
- [ ] 2.2 Fixa `__import__('logging')` → proper `import logging` top-level
- [ ] 2.3 Lägg till `company_id` på `social_marketing.message.tag` och `social_marketing.competitor.tag`
- [ ] 2.4 Gör API-versioner konfigurerbara via `ir.config_parameter` (Facebook v21.0, LinkedIn version)
- [ ] 2.5 Skapa tester för core social_marketing (post, account, live_post, media)
- [ ] 2.6 Skapa tester för social_marketing_facebook
- [ ] 2.7 Skapa tester för social_marketing_linkedin
- [ ] 2.8 Skapa tester för social_marketing_postiz
- [ ] 2.9 Lägg till docstrings på publika metoder i Postiz-modulen

### Fas 3 — Funktionella förbättringar

- [ ] 3.1 Implementera `_compute_mention_count` i listening_topic med faktisk sökning
- [ ] 3.2 Förbättra `_call_ai_agent` med retry-logik och JSON-output-validering
- [ ] 3.3 Implementera strategy pattern för LinkedIn auth (istället för if/elif på `linkedin_auth_method`)
- [ ] 3.4 Implementera async posting via `queue.job` för `_action_post()`
- [ ] 3.5 Förbättra `action_open_playwright_login` — synkronisera session-save utan cron
- [ ] 3.6 Lägg till automatisk konkurrent-data-fetch (via API där möjligt)

---

## Verification

### Efter varje fas:
1. `shazam_verify` — kör LSP + graph-analys, verifiera 0 errors
2. `odoo-bin --test-enable -d <db> --addons-path=... -i social_marketing,social_planner --stop-after-init`
3. Manuell kontroll i UI: skapa ett post, verifiera att krypterade fält inte exponeras i formulär

### Specifika tester:
- **Fas 1.1**: `find . -name "*.p.py"` ska returnera 0 resultat
- **Fas 1.2**: Verifiera att `linkedin_password` inte syns i klartext i databasen: `SELECT linkedin_password FROM social_marketing_account WHERE linkedin_password IS NOT NULL`
- **Fas 1.4**: Öppna dashboard view, verifiera att den laddar utan error
- **Fas 2**: `odoo-bin --test-enable` ska köra ≥100 tester
- **Fas 3**: Posta till LinkedIn via alla tre auth-metoder, verifiera att alla fungerar
