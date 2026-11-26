"""Generate the static XLANORA site (EN and AR) from build/content.py.

Run:  python3 build/build.py
Output: site/en/*.html and site/ar/*.html, plus site/_headers for static hosts.

Five page types per language:
  home      index.html
  services  services.html          (list of services)
  service   services/<slug>.html   (detail page, one per service, 3 pages)
  about     about.html
  contact   contact.html           (form, posts to the configured backend)
"""
import os

import html
import json
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from content import BRAND, CONTACT_EMAIL, PAYPAL_EMAIL, SERVICES, TEXT  # noqa: E402
from content_auth import AUTH_TEXT, SPECIALTY_LABELS  # noqa: E402
from content_reviews import FEEDBACK_EMAIL  # noqa: E402

for _lang in ('en', 'ar'):
    TEXT[_lang].update(AUTH_TEXT[_lang])

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
LANGS = ("en", "ar")


def e(value: str) -> str:
    return html.escape(value, quote=True)


def href(lang: str, key: str) -> str:
    return f"/{lang}/{key}.html"


def other(lang: str) -> str:
    return "ar" if lang == "en" else "en"


def nav_html(lang: str, key: str) -> str:
    t = TEXT[lang]
    items = [("index", t["nav_home"], ""), ("services", t["nav_freelancers"], ""),
             ("portfolio", t["nav_portfolio"], ' class="nav-freelancer" hidden'),
             ("wishlist", t["nav_saved"], ' class="nav-client" hidden'),
             ("about", t["nav_about"], ""), ("contact", t["nav_contact"], "")]
    links = []
    for k, label, extra in items:
        active = k == key or (k == "services" and key in ("services", "freelancer"))
        current = ' aria-current="page"' if active else ""
        links.append(f'<a href="{href(lang, k)}"{extra}{current}>{e(label)}</a>')
    return "".join(links)


def header_html(lang: str, key: str) -> str:
    t = TEXT[lang]
    profile_current = ' aria-current="page"' if key == "profile" else ""
    return f"""
  <header class="site-header">
    <div class="container bar">
      <a class="brand" href="{href(lang, 'index')}" aria-label="{BRAND}">
        <img class="brand-logo" src="/assets/img/logo-full.webp" alt="{BRAND}" width="720" height="632">
      </a>
      <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="site-nav"
              data-label-open="{e(t['mobile_menu_open'])}" data-label-close="{e(t['mobile_menu_close'])}">
        <span class="sr-only">{e(t['nav_menu'])}</span>
        <span class="bars" aria-hidden="true"></span>
      </button>
      <nav id="site-nav" class="site-nav" aria-label="{e(t['nav_menu'])}">
        {nav_html(lang, key)}
        <a class="nav-auth" href="{href(lang, 'login')}" data-signin="{e(t['nav_signin'])}"
           data-dashboard="{e(t['nav_dashboard'])}" data-dashboard-href="{href(lang, 'dashboard')}"{' aria-current="page"' if key == 'dashboard' else ''}>{e(t['nav_signin'])}</a>
        <a class="nav-signed-in" href="{href(lang, 'profile')}"{profile_current} hidden>{e(t['nav_profile'])}</a>
        <button class="nav-signout nav-signed-in" id="nav-signout" type="button" hidden>{e(t['nav_logout'])}</button>
        <a class="btn btn-small" href="{href(lang, 'contact')}">{e(t['cta_quote'])}</a>
        <a class="lang-link" lang="{other(lang)}" hreflang="{other(lang)}" href="{href(other(lang), key)}">{e(t['other_lang'])}</a>
      </nav>
    </div>
  </header>"""


def footer_html(lang: str) -> str:
    t = TEXT[lang]
    return f"""
  <footer class="site-footer">
    <div class="container footer-inner">
      <div>
        <p class="footer-brand">{BRAND}</p>
        <p class="muted">{e(t['footer_tag'])}</p>
      </div>
      <div>
        <p class="footer-label">{e(t['footer_contact'])}</p>
        <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
        <p class="muted footer-support">{e(t['footer_paypal'])} <a href="mailto:{PAYPAL_EMAIL}">{PAYPAL_EMAIL}</a></p>
      </div>
      <div class="footer-copy">
        <p>&copy; 2026 {BRAND}. {e(t['footer_rights'])}</p>
        <a class="lang-link" lang="{other(lang)}" hreflang="{other(lang)}" href="{href(other(lang), 'index')}">{e(t['other_lang'])}</a>
      </div>
    </div>
  </footer>"""


def shell(lang: str, key: str, title: str, description: str, main: str, extra_head: str = "", extra_body: str = "") -> str:
    t = TEXT[lang]
    dir_ = "rtl" if lang == "ar" else "ltr"
    alternates = "".join(f'<link rel="alternate" hreflang="{l}" href="{href(l, key)}">' for l in LANGS)
    alternates += f'<link rel="alternate" hreflang="x-default" href="{href("en", key)}">'
    return f"""<!doctype html>
<html lang="{lang}" dir="{dir_}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(title if title == BRAND else f"{title} | {BRAND}")}</title>
  <meta name="description" content="{e(description)}">
  <link rel="canonical" href="{href(lang, key)}">
  {alternates}
  <link rel="icon" href="/assets/img/logo-mark.webp" type="image/webp">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700&amp;family=Noto+Sans+Arabic:wght@400;600;700&amp;display=swap">
  <link rel="stylesheet" href="/assets/css/main.css">
  {extra_head}
</head>
<body data-page="{key.replace('/', '-')}">
  <a class="skip-link" href="#main">{e(t['skip'])}</a>
{header_html(lang, key)}
  <main id="main">
{main}
  </main>
{footer_html(lang)}
  <script src="/assets/js/nav.js" defer></script>
  <script src="/assets/js/config.js" defer></script>
  <script src="/assets/js/auth.js" defer></script>
{extra_body}
</body>
</html>
"""


def service_card(lang: str, s: dict) -> str:
    t = TEXT[lang]
    return f"""
        <article class="card">
          <img src="/assets/img/{s['image']}.webp" alt="{e(s['alt'][lang])}" width="800" height="450" loading="lazy" decoding="async">
          <div class="card-body">
            <h3>{e(s['title'][lang])}</h3>
            <p>{e(s['short'][lang])}</p>
            <a class="text-link" href="{href(lang, 'services/' + s['slug'])}">{e(t['view_service'])} <span class="arrow" aria-hidden="true">&rarr;</span></a>
          </div>
        </article>"""


def home_page(lang: str) -> str:
    t = TEXT[lang]
    cards = "".join(service_card(lang, s) for s in SERVICES)
    why = "".join(f"<li><h3>{e(title)}</h3><p>{e(text)}</p></li>" for title, text in t["why_points"])
    main = f"""
    <section class="hero hero-band">
      <div class="container hero-grid">
        <div>
          <h1>{e(t['hero_title'])}</h1>
          <p class="lead">{e(t['hero_lead'])}</p>
          <div class="actions">
            <a class="btn" href="{href(lang, 'portfolio')}">{e(t['hero_cta'])}</a>
            <a class="btn btn-ghost" href="{href(lang, 'register')}">{e(t['hero_become'])}</a>
            <a class="btn btn-ghost" href="{href(lang, 'services')}">{e(t['hero_explore'])}</a>
          </div>
        </div>
        <figure class="hero-figure">
          <img class="hero-mark" src="/assets/img/logo-mark.webp" alt="{BRAND}" width="800" height="565" fetchpriority="high">
        </figure>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <h2>{e(t['home_services_title'])}</h2>
        <p class="section-lead">{e(t['home_services_lead'])}</p>
        <div class="card-grid">{cards}
        </div>
      </div>
    </section>

    <section class="section section-tint">
      <div class="container">
        <h2>{e(t['why_title'])}</h2>
        <ul class="feature-list">{why}
        </ul>
      </div>
    </section>"""
    return shell(lang, "index", BRAND, t["hero_lead"], main)


def services_page(lang: str) -> str:
    """The Freelancers page: a searchable directory, loaded by freelancers.js from the database."""
    t = TEXT[lang]
    cats = "".join(f'<option value="{e(slug)}">{e(label)}</option>' for slug, label in SPECIALTY_LABELS[lang].items())
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['services_title'])}</h1>
        <p class="lead">{e(t['services_lead'])}</p>
      </div>
    </section>
    <section class="section">
      <div class="container">
        <form id="fl-search" class="booking-filters" role="search">
          <label class="field"><span>{e(t['fl_search_text'])}</span>
            <input type="search" name="q" maxlength="80" placeholder="{e(t['fl_search_placeholder'])}"></label>
          <label class="field"><span>{e(t['fl_specialty'])}</span>
            <select name="category"><option value="">{e(t['fl_all_specialties'])}</option>{cats}</select></label>
          <button class="btn" type="submit">{e(t['fl_search_button'])}</button>
        </form>
        <p id="fl-status" class="form-status" role="status" aria-live="polite"></p>
        <p id="fl-alert" class="form-status" role="status" aria-live="polite" hidden></p>
        <div id="fl-results" class="freelancer-grid"></div>
      </div>
    </section>"""
    extra = auth_i18n(lang) + '\n  <script src="/assets/js/freelancers.js" defer></script>'
    return shell(lang, "services", t["services_title"], t["services_lead"], main, extra_body=extra)


def service_page(lang: str, s: dict) -> str:
    t = TEXT[lang]
    title = s["title"][lang]
    points = "".join(f"<li>{e(p)}</li>" for p in s["points"][lang])
    extra = ""
    if s.get("extra_image"):
        extra = f"""
    <section class="section section-tint">
      <div class="container">
        <figure class="wide-figure">
          <img src="/assets/img/{s['extra_image']}.webp" alt="{e(s['extra_alt'][lang])}" width="800" height="686" loading="lazy" decoding="async">
        </figure>
      </div>
    </section>"""
    main = f"""
    <section class="page-intro page-band service-intro">
      <div class="container service-grid">
        <div>
          <p class="crumbs"><a href="{href(lang, 'services')}">{e(t['nav_services'])}</a></p>
          <h1>{e(title)}</h1>
          <p class="lead">{e(s['body'][lang])}</p>
          <div class="actions">
            <a class="btn" href="{href(lang, 'contact')}?service={s['slug']}">{e(t['detail_request'])}</a>
          </div>
        </div>
        <figure class="service-figure">
          <img src="/assets/img/{s['image']}.webp" alt="{e(s['alt'][lang])}" width="800" height="450" fetchpriority="high">
        </figure>
      </div>
    </section>

    <section class="section">
      <div class="container narrow">
        <h2>{e(t['detail_included'])}</h2>
        <ul class="check-list">{points}
        </ul>
        <p class="back-link"><a class="text-link" href="{href(lang, 'services')}">{e(t['back_services'])} <span class="arrow" aria-hidden="true">&rarr;</span></a></p>
      </div>
    </section>{extra}"""
    return shell(lang, f"services/{s['slug']}", title, s["short"][lang], main)


def about_page(lang: str) -> str:
    t = TEXT[lang]
    values = "".join(f"<li>{e(v)}</li>" for v in t["about_values"])
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['about_title'])}</h1>
        <p class="lead">{e(t['about_lead'])}</p>
      </div>
    </section>

    <section class="section">
      <div class="container narrow">
        <h2>{e(t['about_story_title'])}</h2>
        <p>{e(t['about_story'])}</p>
      </div>
    </section>

    <section class="section section-tint">
      <div class="container">
        <h2>{e(t['about_team_title'])}</h2>
        <p>{e(t['about_direct'])}</p>
      </div>
    </section>

    <section class="section">
      <div class="container narrow">
        <h2>{e(t['about_values_title'])}</h2>
        <ul class="check-list">{values}
        </ul>
      </div>
    </section>

    <section class="section section-tint" id="feedback">
      <div class="container narrow">
        <h2>{e(t['fb_title'])}</h2>
        <p>{e(t['fb_lead'])}</p>
        <p><strong>{e(t['fb_email_label'])}</strong>
          <a href="mailto:{FEEDBACK_EMAIL}?subject=XLANORA%20feedback">{FEEDBACK_EMAIL}</a></p>
        <p class="muted">{e(t['fb_note'])}</p>
        <p><a class="btn" href="mailto:{FEEDBACK_EMAIL}?subject=XLANORA%20feedback">{e(t['fb_button'])}</a></p>
      </div>
    </section>"""
    return shell(lang, "about", t["about_title"], t["about_lead"], main)


def contact_page(lang: str) -> str:
    t = TEXT[lang]
    service_options = "".join(
        f'<option value="{s["slug"]}">{e(s["title"][lang])}</option>' for s in SERVICES
    )
    msgs = {
        "errors": {
            "name": t["err_name"],
            "email": t["err_email"],
            "phone": t["err_phone"],
            "service": t["err_service"],
            "message": t["err_message"],
        },
        "generic": t["form_error_generic"],
        "network": t["form_error_network"],
        "success": t["form_success"],
        "sending": t["form_sending"],
    }
    i18n = f'<script type="application/json" id="i18n">{json.dumps(msgs, ensure_ascii=False)}</script>'
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['contact_title'])}</h1>
        <p class="lead">{e(t['contact_lead'])}</p>
      </div>
    </section>

    <section class="section">
      <div class="container contact-grid">
        <form id="contact-form" class="form" novalidate>
          <div class="field">
            <label for="name">{e(t['form_name'])}</label>
            <input id="name" name="name" type="text" autocomplete="name" required minlength="2" maxlength="80">
            <p class="field-error" id="name-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="email">{e(t['form_email'])}</label>
            <input id="email" name="email" type="email" autocomplete="email" required maxlength="254" dir="ltr">
            <p class="field-error" id="email-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="phone">{e(t['form_phone'])}</label>
            <input id="phone" name="phone" type="tel" autocomplete="tel" maxlength="30" inputmode="tel" dir="ltr">
            <p class="field-error" id="phone-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="service">{e(t['form_service'])}</label>
            <select id="service" name="service">
              <option value="">{e(t['form_service_choose'])}</option>{service_options}
              <option value="unsure">{e(t['form_service_unsure'])}</option>
            </select>
            <p class="field-error" id="service-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="message">{e(t['form_message'])}</label>
            <textarea id="message" name="message" rows="6" required minlength="10" maxlength="2000"></textarea>
            <p class="field-error" id="message-error" role="alert"></p>
          </div>
          <div class="hp" aria-hidden="true">
            <label>Website <input type="text" name="website" tabindex="-1" autocomplete="off"></label>
          </div>
          <p id="form-status" class="form-status" role="status" aria-live="polite"></p>
          <button class="btn" type="submit">{e(t['form_submit'])}</button>
        </form>

        <aside class="contact-info">
          <h2>{e(t['contact_email_label'])}</h2>
          <p><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
        </aside>
      </div>
    </section>"""
    extra_body = f'{i18n}\n  <script src="/assets/js/contact.js" defer></script>'
    return shell(lang, "contact", t["contact_title"], t["contact_lead"], main, extra_body=extra_body)


def auth_i18n(lang: str) -> str:
    """Messages for the account pages, read by auth.js (no inline script, CSP-safe)."""
    t = TEXT[lang]
    msgs = {
        "errors": {
            "full_name": t["auth_error_name"], "email": t["auth_error_email"],
            "password": t["auth_error_password"], "role": t["auth_error_role"],
            "specialty": t["auth_error_specialty"],
        },
        "generic": t["auth_error_generic"],
        "network": t["auth_error_network"],
        "invalid_login": t["auth_error_invalid_login"],
        "email_taken": t["auth_error_email_taken"],
        "rate": t["auth_error_rate"],
        "success_register": t["auth_success_register"],
        "success_login": t["auth_success_login"],
        "signed_out": t["auth_signed_out"],
        "submitting": t["submitting"],
        "go_signin": t["dashboard_go_signin"],
        "empty_client": t["dashboard_empty_client"],
        "empty_freelancer": t["dashboard_empty_freelancer"],
        "lead_client": t["dashboard_client_lead"],
        "lead_freelancer": t["dashboard_freelancer_lead"],
        "signed_as": t["dashboard_signed_in_as"],
        "role_client": t["dashboard_role_client"],
        "role_freelancer": t["dashboard_role_freelancer"],
        "request_for": t["dashboard_request_for"],
        "contact": t["dashboard_contact"],
        "received": t["dashboard_received"],
        "not_sure": TEXT[lang]["form_service_unsure"],
        "specialties": SPECIALTY_LABELS[lang],
        "logout": t["nav_logout"],
        "go_contact": t["dashboard_go_contact"],
        "signin": t["nav_signin"],
        "dashboard": t["nav_dashboard"],
        "loading": t["dashboard_loading"],
        "locale": lang,
        "bk": {k: v for k, v in t.items() if k.startswith("bk_")},
        "pf": {k: v for k, v in t.items() if k.startswith("pf_")},
        "pr": {k: v for k, v in t.items() if k.startswith("profile_")},
        "pc": {k: v for k, v in t.items() if k.startswith("pc_")},
        "fl": {k: v for k, v in t.items() if k.startswith("fl_")},
        "wl": {k: v for k, v in t.items() if k.startswith("wl_")},
        "rv": {k: v for k, v in t.items() if k.startswith(("rv_", "al_", "vf_"))},
        "od": {k: v for k, v in t.items() if k.startswith("od_")},
        "adm": {k: v for k, v in t.items() if k.startswith("adm_")},
    }
    # Messages for the change-password form on the profile page (password.js).
    msgs["pw"] = {k: t[k] for k in ("bk_password_invalid", "bk_password_wrong", "bk_password_saved",
                                    "bk_err_generic", "bk_err_network")}
    return f'<script type="application/json" id="i18n">{json.dumps(msgs, ensure_ascii=False)}</script>'


def login_page(lang: str) -> str:
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container narrow">
        <h1>{e(t['login_title'])}</h1>
        <p class="lead">{e(t['login_lead'])}</p>
      </div>
    </section>
    <section class="section">
      <div class="container narrow">
        <form id="login-form" class="form" novalidate>
          <div class="field">
            <label for="email">{e(t['auth_email'])}</label>
            <input id="email" name="email" type="email" autocomplete="email" required maxlength="254" dir="ltr">
            <p class="field-error" id="email-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="password">{e(t['auth_password'].split(' (')[0])}</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required maxlength="128">
            <p class="field-error" id="password-error" role="alert"></p>
          </div>
          <p id="form-status" class="form-status" role="status" aria-live="polite"></p>
          <button class="btn" type="submit">{e(t['login_submit'])}</button>
        </form>
        <p class="form-foot">{e(t['login_no_account'])} <a href="{href(lang, 'register')}">{e(t['register_submit'])}</a></p>
      </div>
    </section>"""
    return shell(lang, "login", t["login_title"], t["login_lead"], main, extra_body=auth_i18n(lang))


def register_page(lang: str) -> str:
    t = TEXT[lang]
    options = "".join(
        f'<option value="{slug}">{e(label)}</option>' for slug, label in SPECIALTY_LABELS[lang].items()
    )
    main = f"""
    <section class="page-intro page-band">
      <div class="container narrow">
        <h1>{e(t['register_title'])}</h1>
        <p class="lead">{e(t['register_lead'])}</p>
      </div>
    </section>
    <section class="section">
      <div class="container narrow">
        <form id="register-form" class="form" novalidate>
          <div class="field">
            <label for="name">{e(t['auth_name'])}</label>
            <input id="name" name="full_name" type="text" autocomplete="name" required minlength="2" maxlength="80">
            <p class="field-error" id="name-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="email">{e(t['auth_email'])}</label>
            <input id="email" name="email" type="email" autocomplete="email" required maxlength="254" dir="ltr">
            <p class="field-error" id="email-error" role="alert"></p>
          </div>
          <div class="field">
            <label for="password">{e(t['auth_password'])}</label>
            <input id="password" name="password" type="password" autocomplete="new-password" required minlength="8" maxlength="128">
            <p class="field-error" id="password-error" role="alert"></p>
          </div>
          <fieldset class="field role-field">
            <legend>{e(t['auth_role'])}</legend>
            <label class="radio"><input type="radio" name="role" value="client" checked> <span>{e(t['role_client'])}</span></label>
            <label class="radio"><input type="radio" name="role" value="freelancer"> <span>{e(t['role_freelancer'])}</span></label>
            <p class="field-error" id="role-error" role="alert"></p>
          </fieldset>
          <div class="field" id="specialty-wrap" hidden>
            <label for="specialty">{e(t['auth_specialty'])}</label>
            <select id="specialty" name="specialty">
              <option value="">{e(t['form_service_choose'])}</option>{options}
            </select>
            <p class="field-error" id="specialty-error" role="alert"></p>
          </div>
          <p id="form-status" class="form-status" role="status" aria-live="polite"></p>
          <button class="btn" type="submit">{e(t['register_submit'])}</button>
        </form>
        <p class="form-foot">{e(t['register_has_account'])} <a href="{href(lang, 'login')}">{e(t['nav_signin'])}</a></p>
      </div>
    </section>"""
    return shell(lang, "register", t["register_title"], t["register_lead"], main, extra_body=auth_i18n(lang))


def verify_page(lang: str) -> str:
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band" id="vf-page">
      <div class="container narrow">
        <h1>{e(t['vf_title'])}</h1>
        <p class="lead">{e(t['vf_lead'])}</p>
        <p id="vf-result" class="form-status" role="status" aria-live="polite"></p>
        <p><a class="btn" href="{href(lang, 'dashboard')}">{e(t['vf_go_dashboard'])}</a></p>
      </div>
    </section>
    """
    extra = (auth_i18n(lang) + '\n  <script src="/assets/js/verify.js" defer></script>')
    return shell(lang, "verify", t["vf_title"], t["vf_lead"], main, extra_body=extra)


def dashboard_page(lang: str) -> str:
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['dashboard_title'])}</h1>
        <p class="muted" id="dash-who"></p>
        <p class="lead" id="dash-lead"></p>
        <div class="actions">
          <a class="btn" href="{href(lang, 'contact')}">{e(t['dashboard_go_contact'])}</a>
          <button class="btn btn-ghost" id="logout-btn" type="button" hidden>{e(t['nav_logout'])}</button>
        </div>
      </div>
    </section>
    <div class="container"><p id="vf-banner" class="notice" hidden>{e(t['vf_banner'])}
      <button class="btn btn-small" id="vf-resend" type="button">{e(t['vf_resend'])}</button>
      <span id="vf-status" class="form-status" role="status" aria-live="polite"></span></p></div>
    <div class="dash-grid">
    <section class="section">
      <div class="container">
        <p id="dash-status" class="form-status" role="status" aria-live="polite"></p>
        <div id="requests" class="requests"></div>
      </div>
    </section>
    {profile_card(lang)}
    {booking_panels(lang)}
    </div>
    """
    extra = (auth_i18n(lang) + '\n  <script src="/assets/js/bookings.js" defer></script>\n'
             '  <script src="/assets/js/profile.js" defer></script>\n'
             '  <script src="/assets/js/verify.js" defer></script>')
    return shell(lang, "dashboard", t["dashboard_title"], t["dashboard_client_lead"], main, extra_body=extra)


def portfolio_page(lang: str) -> str:
    """Portfolio: for freelancers only. Visitors see who may use it; a freelancer manages their own work samples."""
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['pf_title'])}</h1>
        <p class="lead">{e(t['pf_lead'])}</p>
      </div>
    </section>
    <section class="section" id="pf-gate">
      <div class="container narrow">
        <p>{e(t['pf_freelancers_only'])}</p>
        <div class="actions">
          <a class="btn" href="{href(lang, 'register')}">{e(t['pf_gate_register'])}</a>
          <a class="btn btn-ghost" href="{href(lang, 'login')}">{e(t['pf_gate_signin'])}</a>
        </div>
      </div>
    </section>
    {portfolio_manage_panel(lang)}"""
    extra = auth_i18n(lang) + '\n  <script src="/assets/js/portfolio.js" defer></script>'
    return shell(lang, "portfolio", t["pf_title"], t["pf_lead"], main, extra_body=extra)


def freelancer_page(lang: str) -> str:
    """One freelancer's public profile. freelancer.js reads ?id= and fills the page from the database."""
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <p class="crumbs"><a href="{href(lang, 'services')}">{e(t['fl_back'])}</a></p>
        <h1>{e(t['fl_profile_title'])}</h1>
        <p id="fp-status" class="lead" role="status" aria-live="polite">{e(t['fl_loading_profile'])}</p>
      </div>
    </section>
    <section class="section" id="fp-body" hidden>
      <div class="container">
        <div id="fp-head" class="fp-head"></div>
        <div class="fp-block">
          <h2>{e(t['fl_services_title'])}</h2>
          <div id="fp-services" class="fp-services"></div>
        </div>
        <div class="fp-block">
          <h2>{e(t['fl_portfolio_title'])}</h2>
          <div id="fp-portfolio" class="work-grid"></div>
        </div>
        <div class="fp-block" id="fp-reviews-block">
          <h2>{e(t['rv_title'])}</h2>
          <p id="fp-rating" class="freelancer-meta"></p>
          <div id="fp-review-form" class="review-form" hidden>
            <h3>{e(t['rv_form_title'])}</h3>
            <p class="muted">{e(t['rv_form_lead'])}</p>
            <form id="rv-form" novalidate>
              <fieldset class="star-picker">
                <legend>{e(t['rv_rating_label'])}</legend>
                <div id="rv-stars" class="star-row"></div>
              </fieldset>
              <label for="rv-comment">{e(t['rv_comment_label'])}</label>
              <textarea id="rv-comment" name="comment" rows="4" maxlength="600"></textarea>
              <p class="muted small">{e(t['rv_comment_hint'])}</p>
              <p><button class="btn" type="submit">{e(t['rv_submit'])}</button></p>
              <p id="rv-status" class="form-status" role="status" aria-live="polite"></p>
            </form>
          </div>
          <div id="fp-reviews" class="review-list"></div>
        </div>
      </div>
    </section>"""
    extra = auth_i18n(lang) + '\n  <script src="/assets/js/freelancers.js" defer></script>'
    return shell(lang, "freelancer", t["fl_profile_title"], t["fl_profile_title"], main, extra_body=extra)


def wishlist_page(lang: str) -> str:
    """Saved freelancers for clients. freelancers.js loads the list; visitors and freelancers see a note."""
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['wl_title'])}</h1>
        <p class="lead">{e(t['wl_lead'])}</p>
      </div>
    </section>
    <section class="section" id="wl-gate">
      <div class="container narrow">
        <p>{e(t['wl_gate'])}</p>
        <div class="actions"><a class="btn" href="{href(lang, 'login')}">{e(t['wl_gate_signin'])}</a></div>
      </div>
    </section>
    <section class="section" id="wl-body" hidden>
      <div class="container">
        <p id="wl-status" class="form-status" role="status" aria-live="polite"></p>
        <div id="wl-results" class="freelancer-grid"></div>
      </div>
    </section>"""
    extra = auth_i18n(lang) + '\n  <script src="/assets/js/freelancers.js" defer></script>'
    return shell(lang, "wishlist", t["wl_title"], t["wl_lead"], main, extra_body=extra)



def password_section(lang: str) -> str:
    """Change-password form. It lives only on the signed-in user's own profile page; password.js shows it
    to a signed-in user and the server changes only that user's password (the session decides who)."""
    t = TEXT[lang]
    return f"""
      <section class="section account-section" id="password-section" hidden aria-labelledby="password-title">
        <h2 id="password-title">{e(t['bk_password_title'])}</h2>
        <form id="password-form" novalidate>
          <label class="field"><span>{e(t['bk_current_password'])}</span>
            <input type="password" name="current_password" autocomplete="current-password" required></label>
          <label class="field"><span>{e(t['bk_new_password'])}</span>
            <input type="password" name="new_password" autocomplete="new-password" minlength="8" maxlength="128" required></label>
          <div class="actions"><button class="btn" type="submit">{e(t['bk_password_submit'])}</button></div>
        </form>
        <p id="password-status" class="form-status" role="status" aria-live="polite"></p>
      </section>
"""


def profile_page(lang: str) -> str:
    """Account page for every signed-in user: photo (profile.js), name and, for freelancers, a headline."""
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['profile_page_title'])}</h1>
        <p class="lead">{e(t['profile_page_lead'])}</p>
      </div>
    </section>
    <section class="section" id="pp-gate">
      <div class="container narrow">
        <p>{e(t['profile_gate'])}</p>
        <div class="actions"><a class="btn" href="{href(lang, 'login')}">{e(t['profile_gate_link'])}</a></div>
      </div>
    </section>
    <div id="pp-body" hidden>
      {profile_card(lang)}
      <section class="section" id="pc-panel" hidden>
        <div class="container">
          <div class="pc-card">
            <h2 id="pc-title">{e(t['pc_title'])}</h2>
            <p class="muted">{e(t['pc_lead'])}</p>
            <div class="pc-progress" role="progressbar" aria-labelledby="pc-title" aria-valuemin="0" aria-valuemax="4" aria-valuenow="0">
              <span id="pc-bar"></span>
            </div>
            <p id="pc-count" class="muted"></p>
            <ol class="pc-steps">
              <li id="pc-photo" class="pc-step"></li>
              <li id="pc-headline" class="pc-step"></li>
              <li id="pc-service" class="pc-step"></li>
              <li id="pc-portfolio" class="pc-step"></li>
            </ol>
          </div>
        </div>
      </section>
      <section class="section">
        <div class="container">
          <h2>{e(t['profile_details_title'])}</h2>
          <form id="profile-form" class="profile-form" novalidate>
            <label class="field"><span>{e(t['profile_name_label'])}</span>
              <input type="text" name="full_name" maxlength="80" autocomplete="name" required></label>
            <label class="field" id="pp-headline-field" hidden><span>{e(t['profile_headline_label'])}</span>
              <textarea name="headline" rows="3" maxlength="160" aria-describedby="pp-headline-hint"></textarea>
              <small id="pp-headline-hint" class="muted">{e(t['profile_headline_hint'])}</small></label>
            <dl class="profile-facts">
              <dt>{e(t['profile_email_label'])}</dt><dd id="pp-email"></dd>
              <dt>{e(t['profile_role_label'])}</dt><dd id="pp-role"></dd>
            </dl>
            <div class="actions">
              <button class="btn" type="submit">{e(t['profile_save_details'])}</button>
              <a id="pp-public" class="btn btn-ghost" href="#" hidden>{e(t['profile_view_public'])}</a>
            </div>
          </form>
          <p id="pp-status" class="form-status" role="status" aria-live="polite"></p>
        </div>
      </section>
      {password_section(lang)}
    </div>"""
    extra = (auth_i18n(lang) + '\n  <script src="/assets/js/profile.js" defer></script>\n'
             '  <script src="/assets/js/profile-page.js" defer></script>\n'
             '  <script src="/assets/js/password.js" defer></script>')
    return shell(lang, "profile", t["profile_page_title"], t["profile_page_lead"], main, extra_body=extra)


def profile_card(lang: str) -> str:
    """Profile photo and name on the dashboard, for every signed-in role. Hidden until profile.js shows it."""
    t = TEXT[lang]
    return f"""
    <section class="section profile-panel" id="profile-panel" hidden>
      <div class="container">
        <h2>{e(t['profile_title'])}</h2>
        <div class="profile-card">
          <div class="profile-photo">
            <img id="profile-avatar" class="avatar" alt="" width="112" height="112" hidden>
            <span id="profile-initial" class="avatar avatar-initial" aria-hidden="true"></span>
          </div>
          <div class="profile-info">
            <p class="profile-name" id="profile-name"></p>
            <p class="muted" id="profile-role"></p>
            <form id="avatar-form" class="avatar-form" novalidate>
              <label class="file-button">
                <span>{e(t['profile_choose'])}</span>
                <input type="file" id="avatar-file" name="avatar" accept="image/jpeg,image/png,image/webp">
              </label>
              <button class="btn" type="submit" id="avatar-save" disabled>{e(t['profile_save_photo'])}</button>
            </form>
            <p class="muted small">{e(t['profile_photo_hint'])}</p>
            <p id="avatar-status" class="form-status" role="status" aria-live="polite"></p>
          </div>
        </div>
      </div>
    </section>"""


def portfolio_manage_panel(lang: str) -> str:
    """Freelancer's own work samples, on the Portfolio page. Hidden until portfolio.js sees a freelancer."""
    t = TEXT[lang]
    return f"""
    <section class="section booking-panel" id="portfolio-manage" hidden>
      <div class="container">
        <h2>{e(t['pf_manage_title'])}</h2>
        <p class="muted">{e(t['pf_manage_lead'])}</p>
        <p id="pf-status" class="form-status" role="status" aria-live="polite"></p>
        <div id="pf-list" class="booking-list"></div>
        <h3 id="pf-form-title">{e(t['pf_add'])}</h3>
        <form id="pf-form" class="booking-form-grid" novalidate>
          <input type="hidden" name="id" value="">
          <label class="field field-wide"><span>{e(t['pf_item_title'])}</span>
            <input type="text" name="title" maxlength="100" required></label>
          <label class="field field-wide"><span>{e(t['pf_item_description'])}</span>
            <textarea name="description" rows="3" maxlength="1000" required></textarea></label>
          <div class="field field-wide upload-field">
            <span class="field-label">{e(t['pf_upload_label'])}</span>
            <div class="upload-box">
              <img id="pf-preview" class="upload-preview" alt="" width="160" height="90" hidden>
              <div class="upload-body">
                <input type="file" id="pf-file" name="image_file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime">
                <p class="muted small">{e(t['pf_upload_hint'])}</p>
              </div>
            </div>
          </div>
          <label class="field field-wide"><span>{e(t['pf_or_link'])}</span>
            <input type="url" name="image_url" maxlength="500" inputmode="url" dir="ltr"></label>
          <label class="field field-wide"><span>{e(t['pf_project_url'])}</span>
            <input type="url" name="project_url" maxlength="500" inputmode="url" dir="ltr"></label>
          <div class="actions field-wide">
            <button class="btn" type="submit">{e(t['pf_save'])}</button>
            <button class="btn btn-ghost" type="button" id="pf-cancel" hidden>{e(t['pf_cancel'])}</button>
          </div>
        </form>
      </div>
    </section>"""


def admin_page(lang: str) -> str:
    """Administrator inbox: contact messages. Only accounts marked as administrators see the list;
    the server checks that on every request (this page is hidden from search engines)."""
    t = TEXT[lang]
    main = f"""
    <section class="page-intro page-band">
      <div class="container">
        <h1>{e(t['adm_title'])}</h1>
        <p class="lead">{e(t['adm_lead'])}</p>
      </div>
    </section>
    <section class="section admin-panel">
      <div class="container">
        <p id="adm-gate" class="form-status" role="status" hidden></p>
        <div id="adm-main" hidden>
          <h2>{e(t['adm_contacts_title'])}</h2>
          <p id="adm-status" class="form-status" role="status" aria-live="polite"></p>
          <div class="table-wrap"><table class="fin-table">
            <thead><tr>
              <th scope="col">{e(t['adm_col_date'])}</th><th scope="col">{e(t['adm_col_name'])}</th>
              <th scope="col">{e(t['adm_col_email'])}</th><th scope="col">{e(t['adm_col_service'])}</th>
              <th scope="col">{e(t['adm_col_message'])}</th>
            </tr></thead>
            <tbody id="adm-contacts"></tbody>
          </table></div>
        </div>
      </div>
    </section>"""
    extra = (auth_i18n(lang) + '\n  <script src="/assets/js/admin.js" defer></script>')
    return shell(lang, "admin", t["adm_title"], t["adm_lead"], main, extra_head=(
        '<meta name="robots" content="noindex, nofollow">'), extra_body=extra)


def booking_panels(lang: str) -> str:
    """Booking, services, weekly hours and password panels. Hidden until bookings.js shows the ones for the role."""
    t = TEXT[lang]
    cats = "".join(f'<option value="{e(slug)}">{e(label)}</option>' for slug, label in SPECIALTY_LABELS[lang].items())
    sorts = "".join(
        f'<option value="{v}">{e(t["bk_sort_" + k])}</option>'
        for k, v in (("newest", "newest"), ("price_asc", "price_asc"), ("price_desc", "price_desc"), ("name", "name")))
    durations = "".join(f'<option value="{m}">{m} {e(t["bk_duration"].split("{minutes}")[1].strip())}</option>'
                        for m in range(30, 481, 30))
    days = "".join(f"""
            <div class="hours-row">
              <label class="check"><input type="checkbox" name="open{i}"> <span>{e(day)}</span></label>
              <label class="field"><span>{e(t['bk_from'])}</span><select name="start{i}"></select></label>
              <label class="field"><span>{e(t['bk_to'])}</span><select name="end{i}"></select></label>
            </div>""" for i, day in enumerate(t["bk_weekdays"]))
    return f"""
    <section class="section booking-panel" id="client-panel" hidden>
      <div class="container">
        <h2>{e(t['bk_find_title'])}</h2>
        <form id="search-form" class="booking-filters" role="search">
          <label class="field"><span>{e(t['bk_search_text'])}</span>
            <input type="search" name="q" maxlength="80" placeholder="{e(t['bk_search_placeholder'])}"></label>
          <label class="field"><span>{e(t['bk_category'])}</span>
            <select name="category"><option value="">{e(t['bk_all_categories'])}</option>{cats}</select></label>
          <label class="field"><span>{e(t['bk_max_price'])}</span>
            <input type="number" name="max_price" min="0" max="100000" step="1" inputmode="numeric"></label>
          <label class="field"><span>{e(t['bk_sort'])}</span><select name="sort">{sorts}</select></label>
          <button class="btn" type="submit">{e(t['bk_search_button'])}</button>
        </form>
        <p id="search-status" class="form-status" role="status" aria-live="polite"></p>
        <div id="service-results" class="booking-results"></div>
      </div>
    </section>
    <section class="section booking-panel" id="book-panel" hidden>
      <div class="container narrow">
        <h2>{e(t['bk_book_title'])}</h2>
        <p class="lead" id="book-service-name"></p>
        <form id="book-form" novalidate>
          <label class="field"><span>{e(t['bk_date'])}</span><input type="date" name="date" required></label>
          <fieldset class="slot-fieldset">
            <legend>{e(t['bk_choose'])}</legend>
            <p class="muted" id="slot-hint">{e(t['bk_pick_date'])}</p>
            <div id="slot-list" class="slot-list"></div>
          </fieldset>
          <label class="field"><span>{e(t['bk_note'])}</span><textarea name="note" rows="3" maxlength="500"></textarea></label>
          <div class="actions">
            <button class="btn" type="submit" id="book-submit" disabled>{e(t['bk_confirm'])}</button>
            <button class="btn btn-ghost" type="button" id="book-back">{e(t['bk_back'])}</button>
          </div>
        </form>
        <p id="book-status" class="form-status" role="status" aria-live="polite"></p>
      </div>
    </section>
    <section class="section booking-panel" id="bookings-panel" hidden>
      <div class="container">
        <h2 id="bookings-title">{e(t['bk_my_bookings'])}</h2>
        <p id="bookings-status" class="form-status" role="status" aria-live="polite"></p>
        <div id="bookings-list" class="booking-list"></div>
      </div>
    </section>
    <section class="section booking-panel" id="services-panel" hidden>
      <div class="container">
        <h2>{e(t['bk_my_services'])}</h2>
        <p id="services-status" class="form-status" role="status" aria-live="polite"></p>
        <div id="services-list" class="booking-list"></div>
        <h3 id="service-form-title">{e(t['bk_add_service'])}</h3>
        <form id="service-form" class="booking-form-grid" novalidate>
          <input type="hidden" name="id" value="">
          <label class="field field-wide"><span>{e(t['bk_service_title'])}</span>
            <input type="text" name="title" maxlength="100" required></label>
          <label class="field field-wide"><span>{e(t['bk_service_description'])}</span>
            <textarea name="description" rows="3" maxlength="1000" required></textarea></label>
          <label class="field"><span>{e(t['bk_service_price'])}</span>
            <input type="number" name="price_sar" min="0" max="100000" step="1" inputmode="numeric" required></label>
          <label class="field"><span>{e(t['bk_service_duration'])}</span><select name="duration_minutes">{durations}</select></label>
          <div class="actions field-wide">
            <button class="btn" type="submit">{e(t['bk_save'])}</button>
            <button class="btn btn-ghost" type="button" id="service-cancel" hidden>{e(t['bk_cancel_edit'])}</button>
          </div>
        </form>
      </div>
    </section>
    <section class="section booking-panel" id="hours-panel" hidden>
      <div class="container">
        <h2>{e(t['bk_availability'])}</h2>
        <p class="muted">{e(t['bk_availability_lead'])}</p>
        <form id="hours-form" novalidate>{days}
          <div class="actions"><button class="btn" type="submit">{e(t['bk_save'])}</button></div>
        </form>
        <p id="hours-status" class="form-status" role="status" aria-live="polite"></p>
      </div>
    </section>
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def headers_file() -> str:
    """site/_headers for static hosts (Netlify). Same headers the local server sends."""
    sys.path.insert(0, str(ROOT / "server"))
    from app import SECURITY_HEADERS  # single source of truth for security headers
    lines = ["/*"] + [f"  {name}: {value}" for name, value in SECURITY_HEADERS.items()]
    return "\n".join(lines) + "\n"


def build() -> list[Path]:
    written = []
    (ROOT / "site" / "_headers").write_text(headers_file(), encoding="utf-8")
    written.append(ROOT / "site" / "_headers")
    for lang in LANGS:
        pages = {
            "index.html": home_page(lang),
            "services.html": services_page(lang),
            "about.html": about_page(lang),
            "contact.html": contact_page(lang),
            "login.html": login_page(lang),
            "register.html": register_page(lang),
            "dashboard.html": dashboard_page(lang),
            "portfolio.html": portfolio_page(lang),
            "freelancer.html": freelancer_page(lang),
            "profile.html": profile_page(lang),
            "wishlist.html": wishlist_page(lang),
            "verify.html": verify_page(lang),
            "admin.html": admin_page(lang),
        }
        for s in SERVICES:
            pages[f"services/{s['slug']}.html"] = service_page(lang, s)
        for name, content in pages.items():
            target = SITE / lang / name
            write(target, content)
            written.append(target)
    written.extend(seo_files())
    return written


# Pages that search engines may index. Private pages (dashboards, admin, sign-in, verification,
# saved items) are blocked in robots.txt and left out of the sitemap.
PUBLIC_PAGES = ["index.html", "services.html", "about.html", "contact.html", "portfolio.html"]
PRIVATE_PATHS = ["/api/", "/en/admin.html", "/ar/admin.html", "/en/dashboard.html", "/ar/dashboard.html",
                 "/en/profile.html", "/ar/profile.html", "/en/wishlist.html", "/ar/wishlist.html",
                 "/en/verify.html", "/ar/verify.html", "/en/login.html", "/ar/login.html",
                 "/en/register.html", "/ar/register.html"]


def public_base() -> str:
    """The public address of the site, e.g. https://xlanora.netlify.app. Set XLANORA_PUBLIC_URL before building;
    without it a clearly marked placeholder is written so nobody publishes a wrong sitemap by mistake."""
    # Netlify sets URL to the site's address during builds; XLANORA_PUBLIC_URL overrides it.
    value = (os.environ.get("XLANORA_PUBLIC_URL", "") or os.environ.get("URL", "")).strip().rstrip("/")
    return value or "https://YOUR-SITE-NAME.netlify.app"


def seo_files() -> list[Path]:
    base = public_base()
    urls = []
    for lang in LANGS:
        for name in PUBLIC_PAGES:
            urls.append(f"/{lang}/{name}")
        for service_page in sorted((ROOT / "site" / lang / "services").glob("*.html")):
            urls.append(f"/{lang}/services/{service_page.name}")
    robots = ["# XLANORA robots.txt", "User-agent: *", "Allow: /"]
    robots += [f"Disallow: {path}" for path in PRIVATE_PATHS]
    robots += ["", f"Sitemap: {base}/sitemap.xml", ""]
    entries = "\n".join(f"  <url><loc>{base}{u}</loc></url>" for u in urls)
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f"{entries}\n</urlset>\n")
    outputs = [(ROOT / "site" / "robots.txt", "\n".join(robots)), (ROOT / "site" / "sitemap.xml", sitemap)]
    for path, content in outputs:
        path.write_text(content, encoding="utf-8")
    return [path for path, _ in outputs]


if __name__ == "__main__":
    for p in build():
        print("wrote", p.relative_to(ROOT))
