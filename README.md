# odoo-social

Social media management for Odoo Community Edition — built by Vertel Sverige AB (AGPL-3).

## Modules

| Module | Description | Auto-install |
|---|---|---|
| `social_marketing` | Core — posts, accounts, streams, UTM tracking | No |
| `social_marketing_linkedin` | LinkedIn — official API, cookie-based, Playwright browser automation | Yes |
| `social_marketing_facebook` | Facebook — Graph API publishing, inbox, stream | No |
| `social_marketing_instagram` | Instagram — Graph API publishing (2-step), inbox, stream | No |
| `social_planner` | Communication planning, policy, approval, AI, competitor analysis, unified inbox | No |
| `social_marketing_postiz` | Postiz bridge — universal API proxy for 32+ platforms | No |
| `social_dashboard` | BI dashboards for `social_marketing` powered by `dashboard_vrtl` | No |
| `social_planner_dashboard` | BI dashboards for `social_planner` (plans, policy, listening, approval) | No |
| `social_marketing_agency` | Agency layer — brands, underlag, customer portal accounts, per-brand dashboards | No |

## Dependencies

```bash
# Core (installed by Odoo)
# requests

# Job queue (required by social_marketing since the publishing pipeline
# integration — OCA/queue, branch 18.0 → clone to /usr/share/odooext-OCA-queue,
# add to addons_path, install the queue_job module)
# OCA/queue, branch 18.0 → clone to /usr/share/odooext-OCA-queue, add to
# addons_path, install the queue_job module

# LinkedIn — cookie-based auth
pip install linkedin-api

# LinkedIn — Playwright browser automation
pip install playwright && playwright install chromium
```

## Branch Compatibility

- **18.0** — Odoo 18 Community Edition

## License

AGPL-3 — Vertel Sverige AB

## Agency layer (`social_marketing_agency`)

Makes the platform a multi-customer agency service. Depends on
`social_marketing`, `social_planner` and `dashboard_vrtl`.

### Concepts

- **Brand** (`social.brand`) — the scoping unit for all customer data. A brand
  belongs to exactly one customer (`res.partner`, the invoiced entity); a
  customer can have zero or more brands.
- **Underlag** (`social.agency.document`) — customer deliverables (strategy,
  briefs, brand guidelines, reports) with types, attachments, status and
  chatter, scoped per brand.
- **Customer users** — contacts of a customer partner are invited as portal
  users (`share=True`). They see only data of their own brands (record rules
  on `brand_id.partner_id = commercial_partner_id`).
- **Rights levels** — per brand, `customer_edit_enabled` decides the group
  assigned on invite:
  - disabled → `group_social_customer_approver` (read + approve + chatter)
  - enabled → `group_social_customer_editor` (full editing of own data)
- **Customer approval step** — a policy `approval_chain` entry with
  `role: 'customer'` sends posts to `awaiting_customer` after internal
  approval; the customer's users approve/reject via buttons and chatter.
  Publishing is blocked until the customer approves.
- **Brand kanban root** — the first menu under Social Agency lists the brands
  the user is assigned to (`res.users.brand_ids`). Clicking a brand sets the
  session brand (`social_brand_id`) and opens the brand workspace (underlag,
  policies, templates, listening, flows) scoped to that brand.
- **Per-brand dashboard** — each brand gets a `dashboard.dashboard` record
  (`access_by='user'`) with KPI charts (awaiting customer approval, underlag,
  listening topics). Dashboard sources in `social_dashboard` /
  `social_planner_dashboard` scope data by brand for customer users and for
  agency users in brand focus.

### Groups

| Group | Purpose |
|---|---|
| `group_social_agency_brand_user` | Internal user working with brands (implies `base.group_user`) |
| `group_social_customer` | Base portal group for customer users |
| `group_social_customer_approver` | Read own brands + approve/reject customer step |
| `group_social_customer_editor` | Full editing of own brands (implies approver) |

## Publishing pipeline (integrated)

The publishing pipeline is integrated into the existing modules — no
separate module. Core dispatch lives in `social_marketing` (pipeline step
model, `queue_job` fan-out, per-media rate limits, aggregation); approval
and policy stages live in `social_planner` (compliance snapshot, re-check
cron, policy write hook). Requires `queue_job` (OCA/queue, 18.0).

### Concepts

- **Pipeline stages** — every stage transition (submitted, compliance
  checked, approved, rejected, awaiting customer, dispatched, published,
  failed, completed, needs recheck) creates a persistent
  `social.publish.pipeline.step` record with timestamp, actor and result.
  The log is shown on the post form under *Publishing Pipeline*.
- **Job-queue fan-out** — `_action_post()` enqueues one `queue.job` per
  live post instead of publishing synchronously. Workers claim jobs with
  `FOR UPDATE SKIP LOCKED`, so running workers on both HA nodes (ska/sto)
  never double-publishes. Transient API errors (429, network) are retried
  with backoff; per-media rate limits delay jobs (`social.publish.rate.limit`
  or the global `social_publish_rate_limit_delay_seconds` default).
- **Compliance snapshot (deterministic)** — at compliance check time the
  post stores `compliance_snapshot` (policy version + verdict + warnings),
  written once and never overwritten. Later policy changes never alter an
  approved decision.
- **Re-check on policy change** — when `communication.policy` content
  changes (version bump), pending/approved/awaiting-customer posts are
  flagged `needs_recheck`; the `ir_cron_publish_recheck` cron re-runs
  compliance and surfaces deviations (failed step + chatter), leaving the
  original snapshot untouched.

### queue_job worker (required)

A worker must run on every Odoo node, otherwise jobs are never processed.
Example systemd unit (`/etc/systemd/system/odoo-queuejobs.service`):

```ini
[Unit]
Description=Odoo queue_job worker
After=odoo.service

[Service]
User=odoo
Group=odoo
ExecStart=/usr/bin/odoo --config /etc/odoo/odoo.conf --workers=0 \
    --no-http --max-children=2
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Size `--max-children` to the expected publish volume. On the Salt master,
register this as a state under `/srv/salt/odoo/` (pattern:
`odoo.repo_apply` for repos, a `odoo-queuejobs` service state for the
worker) and deploy with `repo_apply --site <minion> -r social.repo` after
adding the queue repo to `/srv/salt/odoo/repos/social.repo`:

```
https://github.com/OCA/queue.git /usr/share/odooext-OCA-queue 18.0
```

(and add `queue_job` to the `modules:` list).

### File-descriptor limits (required for HA + job workers)

The `odoo` user's default `ulimit -n` (1024) is too low for a server that
runs the job queue plus production workers — Odoo can fail with
"Failed to allocate directory watch: Too many open files" when restarting
under load or after leftover `--multi-user` test servers hold fds. Raise
the limit for both the Odoo service and the queue worker with a systemd
drop-in (`/etc/systemd/system/odoo.service.d/override.conf` and the same
for the worker unit):

```ini
[Service]
LimitNOFILE=65536
```

Apply with:

```bash
sudo systemctl edit odoo            # add the [Service] LimitNOFILE=65536 block
sudo systemctl daemon-reload
sudo systemctl restart odoo
# repeat for the odoo-queuejobs worker unit
```

Salt-state snippet for `/srv/salt/odoo/` (master side) so it deploys on
the next `state.apply odoo`:

```yaml
/etc/systemd/system/odoo.service.d/override.conf:
  file.managed:
    - source: salt://odoo/files/odoo-service-override.conf
    - makedirs: True
  module.run:
    - systemctl.daemon_reload
    - onchanges: [file]
    - watch_in:
      - service: odoo
```

Also kill leftover `checkmodule --multi-user` test servers (they run an
Odoo on port 4444, e.g. db `test_img_t2`) after such runs:

```bash
ps aux | grep odoo
# kill any process with --http-port=4444
```

(and add `queue_job` to the `modules:` list).

### Agency compatibility

`social.publish.pipeline.step` carries `post_id`; when `social_marketing_agency`
installs and adds `brand_id` to posts, the agency module must add a record
rule for its customer groups on the step model
(`post_id.brand_id.partner_id = user.partner_id.commercial_partner_id`) so
customers see the pipeline log of their own brands. Base access grants read
to `base.group_user` and full rights to social marketing managers.

## LinkedIn-streams (företagssidor + feed) — 2026-08-28

**Mål**: hämta inlägg från LinkedIn-företagssidor (konkurrenter + kunder) in i
`social_marketing.stream.post` (Feed-vyn) via Playwright-skrapning.

### Hur det fungerar
- Stream-typer: `linkedin_company_page` (skrapar `linkedin.com/company/<id>/posts/`)
  och `linkedin_feed` (användarens flöde).
- `_fetch_linkedin_playwright()` (social_marketing_linkedin/models/social_marketing_stream.py):
  kör en Chromium-subprocess **headed under Xvfb** med kontoets
  `linkedin_playwright_session` (storage_state med li_at m.fl.).
- **RLIMIT_AS-fix**: Odoo sätter 4 GB address-space-limit → Chromium kraschar (SIGTRAP).
  Subprocessen körs via `bash -c "ulimit -v unlimited && exec xvfb-run -a python3 ..."`.
- Dedupe på `linkedin_post_urn`. Cron "Social: LinkedIn Company Streams" var 6:e timme.
- Konkurrentkortet (action-512) har smartknappar "Posts" + "Streams".

### Data på social
- Maja Berg (res.user id 10, login maja.berg@vertel.se) = LinkedIn-testkonto.
- LinkedIn-konto id 62 (auth_method playwright, session lagrad).
- Konkurrenter: UCS OneDo (5), Linserv AB (6) + 14 UCS-kunder (7–20, tagg "UCS OneDo kund").
- 16 streams (id 1–16) med competitor_id + linkedin_company_public_id.

### Kända risker
- LinkedIn bot-detection: headless → tom sida; hög frekvens → 429 (cooldown ~30-60 min).
- DOM-selectors kan ändras → isolerade i `_LINKEDIN_PLAYWRIGHT_SCRIPT`.
- Sessionen dör när li_at löper ut → kör "Browser Login — Playwright" på kontot igen.

## Filhantering: p-filer (parallel development)

Detta repo underhålls med **p-file-metodiken**. En `*.p.<ext>`-fil är
källan, och den genererade grenfilen `*.<ext>` skapas FRÅN den av
`odoobranchpfile`/`preprocess`.

```
social_marketing/__manifest__.p.py          ← källan (source of truth)
social_marketing/__manifest__.py            ← genererad, det Odoo laddar
social_marketing/models/__init__.p.py       ← källan
social_marketing/models/__init__.py         ← genererad
```

### Regeln

**Ändra BÅDA filerna i samma commit.** Redigerar du bara den genererade
filen ser det rätt ut i Odoo, men nästa `odoobranchpfile`-körning skriver
över den med innehållet från p-filen och ändringen försvinner tyst.

Detta har hänt tre gånger i detta repo: `0d4f797` strippade registreringen,
`886962f` återställde den, och arbetskopian som blev `18cdd73` var en tredje
återställning. Därför finns en grind.

**Ta inte bort p-filerna.** De är källan per gren. En p-fil utan
preprocessordirektiv (`# #if VERSION >= "18.0"`) är versionsneutral och
preprocessar till sig själv — då ska p-filen och grenfilen vara
**byte-identiska**. En p-fil *med* direktiv skiljer sig med avsikt från varje
gren, eftersom grenfilen är den versionens utvärderade resultat.

### Grinden

```bash
make check-pfiles          # kontrollera (exit 1 vid avvikelse)
make check-pfiles-pairs    # lista alla par och deras status
make install-hooks         # installera pre-commit-hook (en gång per klon)

# granska ett annat repo härifrån
python3 scripts/check_pfile_sync.py --repo /usr/share/odoo-base
```

`scripts/check_pfile_sync.py` läser bara filer — den kräver varken
`preprocess`, `odoobranchpfile` eller något virtualenv, vilket är avsiktligt:
verktygen är inte installerade på någon host, så en grind som kräver dem
skulle aldrig köra.

Hooken i `scripts/git-hooks/pre-commit` installeras till `.git/hooks/` av
`make install-hooks`. Git distribuerar inte hooks med en klon, så en färsk
klon har ingen grind förrän skriptet körs — därför finns samma kontroll även
som `make`-mål. Hoppa över hooken medvetet med `git commit --no-verify`
endast när avvikelsen är avsedd.
