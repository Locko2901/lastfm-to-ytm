"""Flask web dashboard application."""

from __future__ import annotations

import logging
import os
import secrets as _secrets
import sys
from pathlib import Path

from babel import Locale
from flask import Flask, g, render_template, request
from flask_babel import Babel, get_translations

sys.path.insert(0, str(Path(__file__).parent.parent))

from .routes import actions_bp, api_bp, auth_bp, events_bp, notifications_bp, sync_bp
from .services import (
    ENV_FILE,
    DashboardContext,
)
from .services.scheduler import init_scheduler_from_env

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _ensure_secret_key(env_path: Path) -> str:
    """Get or generate FLASK_SECRET_KEY."""
    key = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if key:
        return key

    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("FLASK_SECRET_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    os.environ["FLASK_SECRET_KEY"] = key
                    return key

    key = _secrets.token_hex(32)
    os.environ["FLASK_SECRET_KEY"] = key

    _auto_section = (
        "\n\n"
        "# ============================================================================\n"
        "# AUTO-GENERATED (managed by the app - do not edit manually)\n"
        "# ============================================================================\n"
        f"FLASK_SECRET_KEY={key}\n"
    )

    if env_path.exists():
        content = env_path.read_text()
        if "# AUTO-GENERATED" in content:
            env_path.write_text(content.rstrip("\n") + f"\nFLASK_SECRET_KEY={key}\n")
        else:
            env_path.write_text(content.rstrip("\n") + _auto_section)

    logger.info("Generated and persisted new FLASK_SECRET_KEY to .env")
    return key


app = Flask(__name__, static_folder="static")


app.secret_key = _ensure_secret_key(ENV_FILE)

app.config["BABEL_DEFAULT_LOCALE"] = "en"
_translations_dir = Path(__file__).parent / "translations"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = str(_translations_dir)


def _discover_locales() -> list[str]:
    """Discover available locales."""
    locales = {"en"}
    if _translations_dir.is_dir():
        for child in _translations_dir.iterdir():
            if child.is_dir() and (child / "LC_MESSAGES" / "messages.po").exists():
                locales.add(child.name)
    return sorted(locales)


SUPPORTED_LOCALES = _discover_locales()


def get_locale():
    """Select locale from cookie, then Accept-Language header, then default."""
    cookie_locale = request.cookies.get("ytm-locale")
    if cookie_locale in SUPPORTED_LOCALES:
        return cookie_locale
    return request.accept_languages.best_match(SUPPORTED_LOCALES) or "en"


babel = Babel(app, locale_selector=get_locale)

_dist = Path(__file__).parent / "static" / "dist"
app.jinja_env.globals["use_minified"] = (_dist / "app.min.js").exists() and (_dist / "bundle.min.css").exists()


@app.context_processor
def inject_globals():
    """Make CSP nonce, locales, and JS translations accessible in all templates."""
    locale_choices = [(code, Locale(code).get_display_name(code) or code) for code in SUPPORTED_LOCALES]
    catalog = get_translations()
    js_translations = {}
    if hasattr(catalog, "_catalog"):
        js_translations = {k: v for k, v in catalog._catalog.items() if k and v and isinstance(k, str)}
    from .services.theme import load_theme_overrides

    return {
        "csp_nonce": getattr(g, "csp_nonce", ""),
        "available_locales": locale_choices,
        "js_translations": js_translations,
        "initial_theme_overrides": load_theme_overrides(),
    }


@app.before_request
def generate_csp_nonce():
    """Generate a unique nonce for inline scripts on each request."""
    g.csp_nonce = _secrets.token_urlsafe(16)


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    nonce = getattr(g, "csp_nonce", "")
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        f"connect-src 'self'; font-src 'self'"
    )
    return response


app.register_blueprint(api_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(actions_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(events_bp)


@app.route("/manifest.json")
def manifest():
    """Serve PWA manifest from site root."""
    return app.send_static_file("manifest.json")


@app.route("/")
def index():
    """Main dashboard page."""
    context = DashboardContext.build()
    return render_template("dashboard.html", **context.to_template_context())


def main():
    """Run the Flask development server."""
    logger.info("Starting web dashboard at http://127.0.0.1:2002")
    try:
        init_scheduler_from_env()
    except Exception as e:
        logger.warning(f"Could not initialize scheduler: {e}")
    app.run(debug=True, port=2002, threaded=True)


if __name__ == "__main__":
    main()
