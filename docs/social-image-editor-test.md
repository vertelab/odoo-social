# Test: social.image.template — editor + server-side render + post integration

Automatiserat E2E (Playwright) + manuellt scenario. Körs mot en test-Odoo
(frisk DB via `checkmodule`, aldrig produktion).

## 1. Automatiserat (editor + widget)

`docs/editor_e2e_test.py` (Playwright, headless chromium):

```
# Förutsättningar: test-Odoo på :4444 med social_marketing installerad
# (admin/admin), samt libasound-stub om headless chromium saknar ljudlib:
#   LD_LIBRARY_PATH=/tmp/asound-stub python3 docs/editor_e2e_test.py

1. Logga in → öppna "Image Templates" → "Ny"
2. Fyll "Name"
3. Vänta på att Fabric laddats (knappen "Add text" enabled)
4. Klicka "Add text" → "Delete selection" ska bli enabled
5. Klicka "Save scene + SVG master" → form-spara
6. Verifiera i DB: social_image_template.scene_json innehåller "Text"-objekt
   och ir_attachment med res_field='svg_master' (mimetype image/svg+xml)
```

Verifierat 2026-08-24 mot Odoo 18.0: canvas mountar, Fabric 6.9.1 laddas,
text läggs till, scene_json + svg_master skrivs (SVG valid, 1200×630).

## 2. Render-tjänstens kärna (utan node-canvas)

```
cd /usr/share/odoo-social/render_service && node test_core.mjs
# ✓ token-substitution, XML-escape, hide-if-empty, image-URL-absolutisering
```

## 3. Python-klient + wizard (mot mock-render)

```
1. Starta mock:  python3 /tmp/mock_render.py  (POST /render -> PNG/SVG, token "test-token")
2. Sätt config:  social_marketing.render_service_url=http://127.0.0.1:8899
                 social_marketing.render_service_token=test-token
3. odoo shell:   skapa mall med platshållare → social.image.render.wizard
                 med context active_id=post.id → action_render()
   Verifiera:    ir.attachment image/png skapad, inlagd i post.image_ids,
                 /web/image/<id> svarar 200 med image/png
```

## 4. Manuellt scenario (när render-tjänsten är deployad)

1. Odoo → Social Marketing → Image Templates → Ny
2. Rita en mall: text med `{{headline}}`, bakgrundsrektangel, ladda en SVG-logo
3. Spara → SVG-master genereras (visas i formen)
4. Social Marketing → Posts → Ny → "Create Image from Template"
5. Välj mallen, fyll "Rubrik", Render → PNG skapas och läggs i postens bilder
6. Öppna posten → bilden syns i preview; `/web/image/<id>` returnerar PNG
7. Testa med tom platshållare → lager med `_hideIfEmpty` försvinner
8. Testa säkerhet: platshållarvärde `<script>alert(1)</script>` → visas som
   text i SVG:en (XML-escaped), ingen script-execution

## Kända blockerare i denna miljö

- Render-tjänsten kräver node-canvas (systemlibs) — körs i container/systemd
  via `odoo.render_service`-staten; kan inte startas på denna host utan Docker.
- Zabbix-healthcheck på render-tjänsten återstår (tillägg i zabbix-staten).
