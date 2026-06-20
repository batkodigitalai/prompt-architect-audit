"""Prompt Architect Audit – jednorázově placený Streamlit SaaS.

Vizuál a tok: přesná kopie referenčního produktu Radikální autonomie
(https://ef39bd0bb2305b78bb.v2.appdeploy.ai/).

Bezplatný výstup: deterministický audit promptu (bez AI, vždy k dispozici).
Placený výstup: ZIP archiv (SKILL.md + tokens.json + test-scenarios.md)
generovaný Claude Sonnet POUZE po serverovém ověření Stripe session `paid`.

Povinné env proměnné (nastaví deployment platforma – NIKDY v kódu):
    ANTHROPIC_API_KEY  — Claude API klíč (sk-ant-...)
    STRIPE_SECRET_KEY  — Stripe secret key (sk_live_... nebo sk_test_...)
    APP_URL            — veřejná HTTPS URL aplikace (bez trailing slash)
    PRICE_TEXT         — volitelné, výchozí "990 Kč včetně DPH"

Spuštění lokálně (bez klíčů zobrazí chybu paywall – správné chování):
    streamlit run prompt_architect_app.py
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.error import URLError
from urllib.request import Request, urlopen

import streamlit as st

# ─── Konstanty ─────────────────────────────────────────────────────────────────

APP_NAME     = "Prompt Architect Audit"
APP_LABEL    = "BEZPLATNÝ AUDIT PROMPTU"
APP_SUBTITLE = (
    "Zjistěte za 2 minuty, proč váš AI systém v budoucnu selže "
    "— a získejte přepracovanou architekturu připravenou ke spuštění."
)

PRICE_DEFAULT      = "990 Kč včetně DPH"
PRICE_AMOUNT_CZK   = 99000   # haléře
MIN_PROMPT_CHARS   = 80
FULFILLMENT_MODEL  = "claude-sonnet-4-6"

COMPANY_NAME    = "BATKO.DIGITAL.AI"
COMPANY_PERSON  = "Ing. Jaroslav Batko"
COMPANY_ICO     = "14600153"
COMPANY_DIC     = "CZ5912280418"
COMPANY_ADDRESS = "Lískovec 170, 273 51 Velké Přítočno"
COMPANY_PHONE   = "+420 725 360 151"
COMPANY_EMAIL   = "batko.digital.ai@gmail.com"

LEVEL_LABELS: Dict[int, str] = {
    1: "Chaos Engine",
    2: "Template Copier",
    3: "Rule Builder",
    4: "System Architect",
    5: "Meta-Architect",
}
LEVEL_COLORS: Dict[int, str] = {
    1: "#dc2626",
    2: "#ea580c",
    3: "#d97706",
    4: "#2563eb",
    5: "#16a34a",
}

SYSTEM_TYPES = [
    "Zákaznický servis / chatbot",
    "Generování obsahu / copywriting",
    "Analýza dat / reporty",
    "HR / nábor",
    "Prodej / CRM asistent",
    "Interní znalostní báze",
    "Kód / technická dokumentace",
    "Jiné",
]

# ─── CSS – přesná kopie vizuálu referenčního produktu ──────────────────────────

CSS = """
<style>
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: #f7f5f0 !important;
    color: #13231b !important;
}
[data-testid="stHeader"]     { background: #f7f5f0 !important; border-bottom: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stSidebar"]    { display: none !important; }

/* Primární tlačítka – tmavě zelená */
button[kind="primary"],
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
    background: #13231b !important;
    color: #f7f5f0 !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    padding: .55rem 1.4rem !important;
}
button[kind="primary"]:hover { background: #1e3829 !important; }

/* Sekundární tlačítka */
.stButton > button[kind="secondary"] {
    background: transparent !important;
    color: #13231b !important;
    border: 1.5px solid #13231b !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}

/* Link button (Stripe CTA) */
.stLinkButton > a {
    background: #13231b !important;
    color: #f7f5f0 !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    text-decoration: none !important;
    padding: .6rem 1.4rem !important;
    display: inline-block !important;
}
.stLinkButton > a:hover { background: #1e3829 !important; }

/* Metriky – oranžové hodnoty */
[data-testid="stMetricValue"] {
    color: #B6452C !important;
    font-weight: 800 !important;
    font-size: 1.9rem !important;
}
[data-testid="stMetricLabel"] { color: #6b7280 !important; font-size: .87rem !important; }

/* Formulář – bílá karta */
[data-testid="stForm"] {
    background: #ffffff !important;
    border: 1.5px solid #e8e0d0 !important;
    border-radius: 14px !important;
    padding: 1.4rem 1.6rem !important;
}
.stTextInput  input,
.stTextArea   textarea,
.stNumberInput input,
.stSelectbox  [data-baseweb="select"] > div {
    background: #faf8f4 !important;
    border: 1.5px solid #d6cfc0 !important;
    border-radius: 8px !important;
    color: #13231b !important;
}

/* Expander panely (patička) */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1.5px solid #e8e0d0 !important;
    border-radius: 10px !important;
    margin-bottom: .5rem !important;
}
[data-testid="stExpander"] summary { color: #13231b !important; font-weight: 600 !important; }

/* Divider */
hr { border-color: #e8e0d0 !important; }

/* Mobilní responzivita – jeden sloupec */
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] { flex-direction: column !important; }
}
</style>
"""

# ─── Demo data ──────────────────────────────────────────────────────────────────

DEMO_PROMPT = (
    "Jsi asistent pro zákaznický servis e-shopu BestDeals. Vždy odpovídáš česky.\n"
    "Pokud zákazník reklamuje zboží do 14 dní, automaticky schval vrácení.\n"
    "Pokud reklamuje po 14 dnech, ale do 30 dní, nabídni 15 % slevu na příští nákup.\n"
    "Po 30 dnech odmítni a odkaž na podmínky na https://bestdeals.cz/podminky.\n"
    "NIKDY nepíš slova 'problém', 'bohužel' ani 'nemůžeme'. Délka odpovědi max 120 slov.\n"
    "Pokud zákazník zmíní Vánoce nebo svátky, přidej pozdrav.\n"
    "Nevracíme elektroniku zakoupenou v akci 'Black Friday 2023'.\n"
    "Kontroluj, zda zákazník napsal číslo objednávky ve formátu BD-XXXXX.\n"
)

DEMO_SKILL_MD = """\
# SKILL.md — Zákaznický servis {{shop_name}}

## Role
Jsi zákaznický asistent e-shopu {{shop_name}}. Komunikuješ výhradně v češtině.

## Pravidla pro vrácení
- Do {{return_days_full}} dnů od nákupu: automaticky schval vrácení.
- Do {{return_days_partial}} dnů od nákupu: nabídni slevu {{partial_refund_pct}} % na příští nákup.
- Po {{return_days_partial}} dnech: odmítni a odkaž na {{terms_url}}.

## Výjimky
{{exceptions_list}}

## Styl odpovědi
- Délka: max {{max_words}} slov.
- Zakázaná slova: {{forbidden_words}}.
- Při svátcích: přidej pozdrav.

## Validace
- Číslo objednávky musí být ve formátu {{order_format}}.
"""

DEMO_TOKENS: Dict[str, Any] = {
    "shop_name": "BestDeals",
    "return_days_full": 14,
    "return_days_partial": 30,
    "partial_refund_pct": 15,
    "terms_url": "https://bestdeals.cz/podminky",
    "exceptions_list": "- Elektronika z akce Black Friday 2023",
    "max_words": 120,
    "forbidden_words": ["problém", "bohužel", "nemůžeme"],
    "order_format": "BD-XXXXX",
}

DEMO_TEST_MD = """\
# test-scenarios.md — BestDeals zákaznický servis

## Scénář 1 — vrácení do 14 dní ✅ PASS
- Vstup: "Chci vrátit boty, koupil jsem je 5 dní zpět. Číslo objednávky BD-12345."
- Očekáváno: Schválení vrácení, žádné zakázané slovo.

## Scénář 2 — vrácení po 30 dnech ✅ PASS
- Vstup: "Reklamuji televizi z loňského roku, objednávka BD-99999."
- Očekáváno: Odmítnutí, odkaz na podmínky, žádné zakázané slovo.

## Scénář 3 — chybí číslo objednávky ❌ FAIL → PASS po opravě
- Vstup: "Chci vrátit tričko."
- Očekáváno: Výzva k zadání čísla objednávky ve formátu BD-XXXXX.

## Scénář 4 — zakázané slovo ❌ FAIL → PASS po opravě
- Vstup: "Proč bohužel nemohu vrátit elektroniku?"
- Očekáváno: Odpověď bez slov 'bohužel', 'problém', 'nemůžeme'.
"""

# ─── Helpers ────────────────────────────────────────────────────────────────────


def setting(name: str, default: str = "") -> str:
    """Čte z Streamlit secrets (deployment UI) nebo env proměnné. Nikdy z kódu."""
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)


def price_text() -> str:
    return setting("PRICE_TEXT", PRICE_DEFAULT)


def build_demo_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", DEMO_SKILL_MD)
        zf.writestr("tokens.json", json.dumps(DEMO_TOKENS, ensure_ascii=False, indent=2))
        zf.writestr("test-scenarios.md", DEMO_TEST_MD)
    return buf.getvalue()


# ─── Stripe ─────────────────────────────────────────────────────────────────────


def checkout_url() -> str:
    """Vytvoří Stripe Checkout Session a vrátí URL pro redirect."""
    secret_key = setting("STRIPE_SECRET_KEY")
    app_url     = setting("APP_URL").rstrip("/")
    if not secret_key or not app_url:
        raise RuntimeError("STRIPE_SECRET_KEY nebo APP_URL nejsou nastaveny.")
    import stripe  # type: ignore
    stripe.api_key = secret_key
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "czk",
                "product_data": {"name": "Prompt Architect — ZIP archiv"},
                "unit_amount": PRICE_AMOUNT_CZK,
                "tax_behavior": "inclusive",
            },
            "quantity": 1,
        }],
        automatic_tax={"enabled": True},
        success_url=f"{app_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{app_url}/?checkout=cancelled",
    )
    return session.url


def paid_session() -> bool:
    """True pokud Stripe potvrdí payment_status == paid pro session_id z URL."""
    if st.query_params.get("checkout") != "success":
        return False
    session_id = st.query_params.get("session_id", "")
    secret_key  = setting("STRIPE_SECRET_KEY")
    if not session_id or not secret_key:
        return False
    import stripe  # type: ignore
    stripe.api_key = secret_key
    try:
        return stripe.checkout.Session.retrieve(session_id).payment_status == "paid"
    except Exception:
        return False


# ─── Deterministický audit (bez AI, vždy k dispozici) ────────────────────────


def _count_hardcoded(text: str) -> int:
    """Počet tvrdých hodnot přímo v textu promptu."""
    count = 0
    count += len(re.findall(r'\b\d+\s*(?:dní?|hodin|%|Kč|korun|slov|minut)\b', text, re.IGNORECASE))
    count += len(re.findall(r'https?://\S+', text))
    count += len(re.findall(r'\b(?:NIKDY|VŽDY|ALWAYS|NEVER)\b', text))
    count += len(re.findall(r"['\"][\w\s]{2,20}['\"]", text))
    return count


def run_audit(prompt_text: str) -> Dict:
    """Deterministický strukturální audit — bez AI, vždy k dispozici."""
    words  = prompt_text.split()
    chars  = len(prompt_text)
    lines  = prompt_text.strip().splitlines()
    hard   = _count_hardcoded(prompt_text)
    has_sections = sum(1 for ln in lines if ln.strip().startswith(("#", "##", "**")))
    has_tokens   = "{{" in prompt_text and "}}" in prompt_text
    has_examples = any(k in prompt_text.lower() for k in ("příklad", "example", "ukázka", "vstup:"))

    # Určení úrovně 1–5
    if has_tokens and has_sections >= 3 and hard == 0:
        level = 5 if has_examples else 4
    elif has_sections >= 2 and hard <= 2:
        level = 3
    elif chars > 200 and hard <= 6:
        level = 2
    else:
        level = 1

    # Konkrétní rizika
    risks = []
    if hard > 0:
        risks.append(
            f"Prompt obsahuje {hard} tvrdých hodnot (čísla, URL, výrazy) přímo v textu. "
            "Při každé změně lhůty nebo pravidla musíte přepsat prompt ručně."
        )
    if not has_tokens:
        risks.append(
            "Chybí parametrizace pomocí {{proměnných}}. "
            "Jedna verze promptu nemůže obsloužit různé konfigurace bez ručního kopírování."
        )
    if has_sections < 2:
        risks.append(
            "Prompt nemá oddělené sekce (Role, Pravidla, Styl). "
            "Smíchané instrukce zvyšují riziko konfliktu pravidel."
        )
    if not has_examples:
        risks.append(
            "Chybí validační příklady nebo scénáře. "
            "Bez testů nelze ověřit, zda změna pravidla nerozbila ostatní chování."
        )
    if len(words) > 400:
        risks.append(
            f"Prompt má {len(words)} slov — příliš dlouhé instrukce zvyšují "
            "riziko ignorování části pravidel AI modelem."
        )
    if not risks:
        risks.append("Struktura vypadá dobře. Ověřte validační scénáře před nasazením.")

    verdict_map = {
        1: "Prompt je na úrovni 1/5 (Chaos Engine). Každá změna parametru riskuje rozbití celého systému.",
        2: "Prompt je na úrovni 2/5 (Template Copier). Hodnoty jsou napevno — změna lhůty vyžaduje ruční úpravu promptu.",
        3: "Prompt je na úrovni 3/5 (Rule Builder). Dobrá struktura, ale chybí oddělení hodnot od pravidel.",
        4: "Prompt je na úrovni 4/5 (System Architect). Solidní základ, přidejte validační scénáře.",
        5: "Prompt je na úrovni 5/5 (Meta-Architect). Parametrizovaná architektura připravená na produkci.",
    }

    return {
        "level":       level,
        "level_label": LEVEL_LABELS[level],
        "risk_count":  len(risks),
        "risks":       risks,
        "verdict":     verdict_map[level],
    }


# ─── Placený ZIP (Claude Sonnet — POUZE po paid_session()) ───────────────────


def generate_zip(prompt_text: str, context: str, system_type: str) -> bytes:
    """Generuje ZIP. Volá se VÝHRADNĚ po ověření paid_session() == True."""
    api_key = setting("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY není nakonfigurován. "
            "Kontaktujte provozovatele: " + COMPANY_EMAIL
        )

    system = (
        "Jsi expert na prompt engineering a architekturu AI systémů.\n"
        "Analyzuješ systémový prompt a vytváříš tři produkční soubory.\n\n"
        "Vrať JSON PŘESNĚ v tomto formátu (žádný text před ani po):\n"
        '{"skill_md":"...","tokens_json":"...","test_md":"..."}\n\n'
        "skill_md: Čistá instrukce BEZ konkrétních čísel/URL/textu — pouze proměnné {{nazev}}. "
        "Sekce: ## Role, ## Pravidla, ## Výjimky, ## Styl, ## Validace.\n"
        "tokens_json: Každá tvrdá hodnota jako klíč-hodnota. Validní JSON string.\n"
        "test_md: 4–6 konkrétních testovacích scénářů se vstupy a očekávanými výstupy. "
        "Každý označen jako ✅ PASS nebo ❌ FAIL → PASS po opravě.\n"
        "Piš česky."
    )
    body = json.dumps({
        "model": FULFILLMENT_MODEL,
        "max_tokens": 4096,
        "system": system,
        "messages": [{
            "role": "user",
            "content": (
                f"Typ systému: {system_type}\n"
                f"Kontext: {context}\n\n"
                f"Systémový prompt k přepracování:\n\n{prompt_text}"
            ),
        }],
    }, ensure_ascii=False).encode("utf-8")

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Chyba spojení s Anthropic API: {exc}") from exc

    raw = data["content"][0]["text"].strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    result = json.loads(raw)

    tokens_raw = result.get("tokens_json", "{}")
    tokens_obj = json.loads(tokens_raw) if isinstance(tokens_raw, str) else tokens_raw

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md",           result.get("skill_md", ""))
        zf.writestr("tokens.json",        json.dumps(tokens_obj, ensure_ascii=False, indent=2))
        zf.writestr("test-scenarios.md",  result.get("test_md", ""))
    return buf.getvalue()


# ─── UI komponenty ───────────────────────────────────────────────────────────


def render_hero() -> None:
    st.markdown(
        f"<div style='padding:1.4rem 0 .5rem'>"
        f"<div style='font-size:.75rem;font-weight:700;letter-spacing:.13em;"
        f"color:#B6452C;text-transform:uppercase;margin-bottom:.5rem'>{APP_LABEL}</div>"
        f"<h1 style='font-size:2.55rem;font-weight:800;color:#13231b;"
        f"margin:0 0 .45rem;line-height:1.08'>{APP_NAME}</h1>"
        f"<p style='font-size:1.07rem;color:#4a5568;margin:0 0 .8rem'>{APP_SUBTITLE}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_form() -> bool:
    """Dvousloupcový formulář. Vrací True při úspěšném odeslání."""
    with st.form("audit_form"):
        # ── Řádek 1: dva sloupce (desktop) ──────────────────────────────────
        left, right = st.columns(2)
        with left:
            system_type = st.selectbox(
                "Typ AI systému",
                SYSTEM_TYPES,
                index=0,
            )
        with right:
            context = st.text_input(
                "Kontext použití",
                placeholder="Zákaznický servis pro e-shop s elektronikou…",
            )
        # ── Řádek 2: celá šířka ──────────────────────────────────────────────
        prompt_text = st.text_area(
            "Váš systémový prompt nebo AI instrukce",
            placeholder=(
                "Vložte celý systémový prompt nebo instrukce pro AI agenta… "
                "(minimum 80 znaků)"
            ),
            height=220,
        )
        submitted = st.form_submit_button(
            "Spustit bezplatný audit", type="primary", use_container_width=True
        )

    if not submitted:
        return False

    prompt_text = prompt_text.strip()
    if len(prompt_text) < MIN_PROMPT_CHARS:
        st.warning(
            f"Příliš krátký text ({len(prompt_text)} znaků). "
            f"Zadejte alespoň {MIN_PROMPT_CHARS} znaků."
        )
        return False

    audit = run_audit(prompt_text)
    st.session_state["data"]  = {
        "prompt": prompt_text,
        "context": context.strip(),
        "system_type": system_type,
    }
    st.session_state["audit"] = audit
    st.session_state.pop("zip_bytes", None)
    return True


def render_demo_cta() -> None:
    st.markdown("---")
    st.markdown("### Nevíte, co od auditu čekat?")
    st.caption("Prohlédněte si ukázku na fiktivním zákaznickém servisu — zdarma, bez registrace.")
    if st.button("Zobrazit demo zdarma", use_container_width=True, key="btn_demo"):
        st.session_state["demo"]  = True
        st.session_state["data"]  = {
            "prompt": DEMO_PROMPT,
            "context": "Zákaznický servis e-shopu BestDeals",
            "system_type": "Zákaznický servis / chatbot",
        }
        st.session_state["audit"] = run_audit(DEMO_PROMPT)
        st.session_state.pop("zip_bytes", None)
        st.rerun()


def render_audit_results(audit: Dict, is_demo: bool) -> None:
    if is_demo:
        st.info(
            "🎯 **UKÁZKA** — Výstup pro fiktivní e-shop BestDeals. "
            "Klikněte na *Začít znovu* pro audit vlastního promptu."
        )

    st.divider()
    st.subheader("Váš bezplatný audit promptu")

    level      = audit.get("level", 1)
    label      = audit.get("level_label", "")
    risk_count = audit.get("risk_count", 0)
    prompt_len = len(st.session_state.get("data", {}).get("prompt", ""))

    c1, c2, c3 = st.columns(3)
    c1.metric("Úroveň systému",     f"{level}/5")
    c2.metric("Rizika regrese",     str(risk_count))
    c3.metric("Délka promptu",      f"{prompt_len} zn.")

    color = LEVEL_COLORS.get(level, "#6b7280")
    st.markdown(
        f"<span style='display:inline-block;background:{color}20;color:{color};"
        f"border:1.5px solid {color}55;border-radius:6px;padding:3px 14px;"
        f"font-weight:700;font-size:.93rem;margin:.4rem 0 .8rem'>"
        f"{label}</span>",
        unsafe_allow_html=True,
    )

    risks = audit.get("risks", [])
    if risks:
        st.markdown("**Nalezená strukturální rizika:**")
        for risk in risks:
            st.markdown(f"- {risk}")

    if verdict := audit.get("verdict", ""):
        st.warning(verdict)


def render_demo_output() -> None:
    """Plný vzorový ZIP výstup pro demo + CTA zpět do placeného toku."""
    pt = price_text()
    st.divider()
    st.subheader("📦 Ukázkový ZIP archiv")
    st.markdown(
        "Plný výstup obsahuje: **SKILL.md** (čistá pravidla s proměnnými), "
        "**tokens.json** (všechny konkrétní hodnoty), **test-scenarios.md** (validační scénáře)."
    )
    st.download_button(
        "⬇️ Stáhnout ukázkový ZIP",
        data=build_demo_zip(),
        file_name="prompt_architect_bestdeals_demo.zip",
        mime="application/zip",
        use_container_width=True,
    )
    with st.expander("Náhled SKILL.md"):
        st.code(DEMO_SKILL_MD, language="markdown")
    with st.expander("Náhled tokens.json"):
        st.code(json.dumps(DEMO_TOKENS, ensure_ascii=False, indent=2), language="json")
    with st.expander("Náhled test-scenarios.md"):
        st.code(DEMO_TEST_MD, language="markdown")

    st.divider()
    st.markdown(f"### Chcete výstup pro vlastní systém?")
    st.markdown(f"Jedenkrát zaplaťte **{pt}** a získejte ZIP připravený k nasazení.")
    if st.button(
        f"Chci ZIP archiv pro svůj systém — {pt}",
        type="primary",
        use_container_width=True,
        key="btn_demo_upsell",
    ):
        # Vrátí do ostrého toku — odstraní demo flag, zachová data pro formulář
        st.session_state.pop("demo", None)
        st.session_state.pop("zip_bytes", None)
        st.rerun()


def render_paywall() -> None:
    """Stripe platební tlačítko. Žádný bypass — bez klíčů zobrazí chybu."""
    pt = price_text()

    st.divider()
    st.markdown(f"### Odemkněte váš ZIP archiv — {pt}")
    st.write(
        "Plný výstup: **SKILL.md** (čistá pravidla s proměnnými), "
        "**tokens.json** (všechny hodnoty na jednom místě), "
        "**test-scenarios.md** (validační scénáře). "
        "Generuje Claude Sonnet podle vašeho promptu."
    )

    try:
        url = checkout_url()
    except RuntimeError as exc:
        st.error(f"⛔ {exc}")
        return
    except Exception as exc:
        st.error(f"⛔ Platbu se nepodařilo připravit: {exc}")
        return

    st.link_button(
        f"Pokračovat k bezpečné platbě — {pt}",
        url,
        type="primary",
        use_container_width=True,
    )
    st.caption("🔒 Zabezpečená platba přes Stripe. Cena je konečná včetně DPH.")


def render_fulfillment() -> None:
    """Generování a stažení ZIP — POUZE po ověřené Stripe platbě."""
    st.divider()
    st.subheader("Váš Plán architekta promptů")

    if "zip_bytes" not in st.session_state:
        if st.button(
            "Vygenerovat můj ZIP archiv",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Claude Sonnet generuje váš ZIP archiv…"):
                try:
                    d = st.session_state.get("data", {})
                    st.session_state["zip_bytes"] = generate_zip(
                        d.get("prompt", ""),
                        d.get("context", ""),
                        d.get("system_type", ""),
                    )
                except Exception as exc:
                    st.error(f"ZIP se nepodařilo vytvořit: {exc}")

    zip_bytes = st.session_state.get("zip_bytes")
    if not zip_bytes:
        return

    st.success("✅ ZIP archiv je připraven ke stažení.")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    st.download_button(
        "⬇️ Stáhnout ZIP archiv (SKILL.md + tokens.json + test-scenarios.md)",
        data=zip_bytes,
        file_name=f"prompt_architect_{ts}.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**SKILL.md**")
        st.caption("Čistá pravidla s proměnnými `{{hodnota}}`")
    with c2:
        st.markdown("**tokens.json**")
        st.caption("Všechny hodnoty na jednom místě")
    with c3:
        st.markdown("**test-scenarios.md**")
        st.caption("Validační scénáře pro každou změnu")
    st.caption("💡 PDF: Ctrl+P → Tisk v prohlížeči.")


def render_footer() -> None:
    st.markdown("---")
    with st.expander("Kontakt"):
        st.markdown(
            f"**{COMPANY_NAME}**  \n"
            f"{COMPANY_PERSON}  \n"
            f"IČO: {COMPANY_ICO} &nbsp;|&nbsp; DIČ: {COMPANY_DIC}  \n"
            f"Sídlo: {COMPANY_ADDRESS}  \n"
            f"Tel: {COMPANY_PHONE}  \n"
            f"E-mail: [{COMPANY_EMAIL}](mailto:{COMPANY_EMAIL})"
        )
    with st.expander("Obchodní podmínky"):
        st.markdown(
            f"**Prodávající:** {COMPANY_NAME}, {COMPANY_PERSON}, "
            f"IČO {COMPANY_ICO}, DIČ {COMPANY_DIC}, sídlo {COMPANY_ADDRESS}.  \n\n"
            "Předmětem plnění je digitální produkt (ZIP archiv) dodaný ke stažení "
            "po potvrzení platby. Kupující uzavřením objednávky souhlasí s těmito podmínkami.  \n\n"
            "Na digitální obsah zpřístupněný na žádost kupujícího se zákonné právo na odstoupení "
            "bez udání důvodu nevztahuje (§ 1837 písm. l) OZ).  \n\n"
            f"Dotazy: [{COMPANY_EMAIL}](mailto:{COMPANY_EMAIL})"
        )
    with st.expander("Ochrana soukromí"):
        st.markdown(
            f"Správce: {COMPANY_NAME}, IČO {COMPANY_ICO}.  \n\n"
            "Zpracováváme pouze platební identifikátor ze Stripe. "
            "Údaje neposkytujeme třetím stranám s výjimkou Stripe, Inc. "
            "(platební zpracovatel) v rozsahu nezbytném pro platbu.  \n\n"
            f"Dotazy: [{COMPANY_EMAIL}](mailto:{COMPANY_EMAIL})"
        )
    with st.expander("Vrácení peněz"):
        st.markdown(
            "Digitální obsah je zpřístupněn ihned po potvrzení platby.  \n\n"
            "Zákazník, který obsah nestáhl, může požádat o vrácení do 14 dnů od nákupu. "
            f"Žádost s číslem objednávky ze Stripe zašlete na "
            f"[{COMPANY_EMAIL}](mailto:{COMPANY_EMAIL}).  \n\n"
            "Vrácení provedeme do 14 dnů přes Stripe."
        )
    st.markdown(
        f"<div style='font-size:.73rem;color:#9ca3af;text-align:center;padding:.7rem 0 .3rem'>"
        f"{COMPANY_NAME} &nbsp;·&nbsp; IČO {COMPANY_ICO} &nbsp;·&nbsp; {COMPANY_ADDRESS}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─── Main ────────────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🔍",
        layout="centered",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    # ── Zpracování Stripe redirect ────────────────────────────────────────────
    if paid_session():
        st.session_state["unlocked"] = True
        st.success("✅ Platba potvrzena. Váš ZIP archiv je odemčený.")
    elif st.query_params.get("checkout") == "cancelled":
        st.info("Platba nebyla dokončena. Váš audit zůstává k dispozici.")

    render_hero()

    if st.button("↩ Začít znovu", use_container_width=True):
        for k in ("demo", "data", "audit", "zip_bytes", "unlocked"):
            st.session_state.pop(k, None)
        st.query_params.clear()
        st.rerun()

    is_demo  = st.session_state.get("demo", False)
    has_data = bool(st.session_state.get("data"))
    unlocked = st.session_state.get("unlocked", False)

    if not has_data:
        if render_form():
            st.rerun()
        render_demo_cta()
    else:
        render_audit_results(st.session_state.get("audit", {}), is_demo=is_demo)
        if is_demo:
            render_demo_output()
        elif unlocked:
            render_fulfillment()
        else:
            render_paywall()

    render_footer()


if __name__ == "__main__":
    main()
