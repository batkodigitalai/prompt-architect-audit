# Prompt Architect Audit

Jednorázově placený Streamlit SaaS — vizuální a funkční kopie referenčního produktu Radikální autonomie.

**Živá aplikace:** _(nastavit po nasazení)_

## Co aplikace dělá

1. **Bezplatný audit** — deterministická analýza systémového promptu (bez AI, vždy dostupná)
2. **Placený výstup** — ZIP archiv (SKILL.md + tokens.json + test-scenarios.md) generovaný Claude Sonnet

Placený výstup se odemkne **výhradně** po serverovém ověření `payment_status == paid` ze Stripe Checkout.

## Technologie

- Python 3.11+
- Streamlit ≥ 1.35
- Stripe Python SDK ≥ 7.0
- Anthropic API (claude-sonnet-4-6) — pouze pro placený výstup

## Nasazení — Streamlit Community Cloud

1. Fork / push do GitHub repozitáře
2. Přihlásit se na [share.streamlit.io](https://share.streamlit.io)
3. New app → vybrat repo, branch `main`, soubor `prompt_architect_app.py`
4. Advanced settings → Secrets (TOML formát):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
STRIPE_SECRET_KEY = "sk_live_..."
APP_URL           = "https://vas-app.streamlit.app"
PRICE_TEXT        = "990 Kč včetně DPH"
```

5. Deploy → čekat na stav `ready`

## Povinné env proměnné

| Proměnná | Popis |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API klíč |
| `STRIPE_SECRET_KEY` | Stripe secret key (live nebo test) |
| `APP_URL` | Veřejná HTTPS URL aplikace (bez trailing slash) |
| `PRICE_TEXT` | Volitelné, výchozí `990 Kč včetně DPH` |

**Secrets se nastavují VÝHRADNĚ přes Streamlit Cloud UI — nikdy v kódu ani v secrets.toml na GitHubu.**

## Firemní údaje

- **Firma:** BATKO.DIGITAL.AI
- **Kontakt:** Ing. Jaroslav Batko
- **IČO:** 14600153
- **DIČ:** CZ5912280418
