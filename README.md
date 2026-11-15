# odoo-social — gren 19.0

> **Denna gren är avsiktligt tom.** Modulerna är INTE portade till Odoo 19.
> Grenen finns så att dev-miljöer (`hansolo19`) kan klona den utan att falla,
> men den påstår ingenting om att koden är portad.

## Baseline

| | |
|---|---|
| Källa | `20.0` |
| Moduler | **17** |
| Grenar i repot | `14.0`, `16.0`, `18.0`, `20.0`, `main` |

## Moduler

- `social_ai`
- `social_dashboard`
- `social_image_creator`
- `social_image_creator_agency`
- `social_keykeep`
- `social_marketing`
- `social_marketing_agency`
- `social_marketing_blog`
- `social_marketing_crm`
- `social_marketing_facebook`
- `social_marketing_instagram`
- `social_marketing_linkedin`
- `social_marketing_mass_mailing`
- `social_marketing_postiz`
- `social_marketing_sale`
- `social_planner`
- `social_planner_dashboard`

## Blockerare

**2 externa beroenden saknas** i Odoo 19-kärnan och OCA 19.0:

| Beroende | Behövs av |
|---|---|
| `dashboard_vrtl` | `social_dashboard`, `social_marketing_agency`, `social_planner_dashboard` |
| `queue_job` | `social_marketing` |

### Prioritering

Ett beroende som blockerar många moduler ger mest nytta att lösa först:

- `dashboard_vrtl` — frisläpper **3** modul(er)
- `queue_job` — frisläpper **1** modul(er)

## Nästa steg

Portering sker på `*-pfile`-maskin med versionsagnostisk kod
(`.p.py` / `.p.xml`). Se `/skill:odoo-pfiles`.
