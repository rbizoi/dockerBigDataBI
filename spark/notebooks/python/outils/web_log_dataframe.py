#!/usr/bin/env python3
"""Lecture et enrichissement d'un access log Apache/Nginx en DataFrame Pandas.

Dépendances minimales : pandas
Dépendances recommandées : user-agents, tldextract
Option GeoIP : geoip2 + une base GeoLite2-City.mmdb

Exemples :
  python web_log_dataframe.py access_01.log
  python web_log_dataframe.py access01.log --csv access_enriched.csv
  python web_log_dataframe.py access_01.log --parquet access_enriched.parquet
  python web_log_dataframe.py access_01.log --geoip-db GeoLite2-City.mmdb
"""
from __future__ import annotations

import argparse
import ipaddress
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote_plus, urlparse

import pandas as pd

try:
    from user_agents import parse as parse_user_agent_lib
except ImportError:
    parse_user_agent_lib = None

try:
    import tldextract
except ImportError:
    tldextract = None

try:
    import geoip2.database
except ImportError:
    geoip2 = None

# -----------------------------------------------------------------------------
# 1. FORMAT DU LOG
# -----------------------------------------------------------------------------
# Expression régulière principale. Chaque groupe nommé (?P<nom>...) devient
# une future colonne du DataFrame : IP, date, méthode HTTP, URL, statut, etc.
# Le dernier champ "extra" est optionnel afin de rester compatible avec des
# variantes proches du format Apache/Nginx Combined Log.
LOG_RE = re.compile(
    r'^(?P<ip>\S+)\s+(?P<ident>\S+)\s+(?P<authuser>\S+)\s+'
    r'\[(?P<datetime>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<url>.*?)\s+(?P<protocol>HTTP/[^\"]+)"\s+'
    r'(?P<status>\d{3})\s+(?P<bytes>\S+)\s+'
    r'"(?P<referer>[^"]*)"\s+"(?P<user_agent>[^"]*)"'
    r'(?:\s+"(?P<extra>[^"]*)")?\s*$'
)

# -----------------------------------------------------------------------------
# 2. TABLES DE CLASSIFICATION
# -----------------------------------------------------------------------------
# Ces dictionnaires servent à enrichir les données brutes. Ils peuvent être
# complétés facilement avec de nouveaux moteurs, réseaux sociaux ou robots.
SEARCH_ENGINES = {
    "google.": "Google", "bing.com": "Bing", "yahoo.": "Yahoo",
    "duckduckgo.com": "DuckDuckGo", "yandex.": "Yandex",
    "baidu.com": "Baidu", "qwant.com": "Qwant",
}
SOCIAL_NETWORKS = {
    "facebook.com": "Facebook", "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn", "twitter.com": "Twitter", "x.com": "X",
    "youtube.com": "YouTube", "tiktok.com": "TikTok",
    "reddit.com": "Reddit", "pinterest.com": "Pinterest",
}
BOT_PATTERNS = {
    "googlebot": "Googlebot", "bingbot": "Bingbot", "ahrefsbot": "AhrefsBot",
    "semrushbot": "SemrushBot", "yandexbot": "YandexBot",
    "baiduspider": "Baiduspider", "duckduckbot": "DuckDuckBot",
    "applebot": "Applebot", "facebookexternalhit": "FacebookBot",
    "twitterbot": "Twitterbot",
}


@lru_cache(maxsize=1)
def _domain_extractor():
    """Charge une seule fois la liste locale des suffixes, sans accès réseau."""
    return tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def _registered_domain(host: Optional[str]) -> Optional[str]:
    """Retourne le domaine enregistrable d’un hôte.

    Exemple : ``shop.example.co.uk`` -> ``example.co.uk`` avec tldextract.
    Sans tldextract, le programme applique un repli simple en retirant ``www.``.
    """
    if not host:
        return None
    host = host.lower().strip(".")
    if tldextract is not None:
        # Pas de téléchargement réseau de la Public Suffix List pendant l'exécution.
        ext = _domain_extractor()(host)
        return ".".join(x for x in (ext.domain, ext.suffix) if x) or host
    return host[4:] if host.startswith("www.") else host


def parse_url_fields(value: Optional[str], prefix: str) -> dict:
    """Décompose une URL absolue en scheme, host, domaine, path, query et fragment.

    ``prefix`` permet de produire des colonnes comme ``referer_host`` ou
    ``referer_path``. La valeur ``-`` des logs signifie qu’aucun Referer n’a été
    transmis.
    """
    if not value or value == "-":
        return {f"{prefix}_{k}": None for k in
                ("scheme", "host", "domain", "path", "query", "fragment")}
    try:
        p = urlparse(value)
        host = p.hostname.lower() if p.hostname else None
        return {
            f"{prefix}_scheme": p.scheme or None,
            f"{prefix}_host": host,
            f"{prefix}_domain": _registered_domain(host),
            f"{prefix}_path": p.path or None,
            f"{prefix}_query": p.query or None,
            f"{prefix}_fragment": p.fragment or None,
        }
    except Exception:
        return {f"{prefix}_{k}": None for k in
                ("scheme", "host", "domain", "path", "query", "fragment")}


def parse_request_url(value: str) -> dict:
    """Analyse l’URL demandée au serveur et compte ses paramètres HTTP GET."""
    # Une URL de requête dans un access log est souvent relative (/path?...).
    try:
        p = urlparse(value)
        params = parse_qs(p.query, keep_blank_values=True)
        return {
            "url_path": p.path or None,
            "url_query": p.query or None,
            "url_fragment": p.fragment or None,
            "url_parameter_count": len(params),
        }
    except Exception:
        return {"url_path": None, "url_query": None, "url_fragment": None,
                "url_parameter_count": 0}


def parse_ip_fields(value: str) -> dict:
    """Enrichit une adresse IP : version, privée/publique, loopback, multicast."""
    try:
        ip = ipaddress.ip_address(value)
        return {
            "ip_version": ip.version,
            "ip_is_private": ip.is_private,
            "ip_is_global": ip.is_global,
            "ip_is_loopback": ip.is_loopback,
            "ip_is_multicast": ip.is_multicast,
        }
    except ValueError:
        return {"ip_version": None, "ip_is_private": False, "ip_is_global": False,
                "ip_is_loopback": False, "ip_is_multicast": False}


def _detect_bot(ua: str) -> tuple[bool, Optional[str]]:
    """Détecte les robots connus et fournit un nom de bot quand c’est possible."""
    low = (ua or "").lower()
    for pattern, name in BOT_PATTERNS.items():
        if pattern in low:
            return True, name
    if re.search(r"\b(bot|crawler|spider|slurp)\b", low):
        return True, "Other Bot"
    return False, None


def parse_user_agent(value: str) -> dict:
    """Transforme le User-Agent en navigateur, OS, appareil et type de client.

    La bibliothèque ``user-agents`` est utilisée lorsqu’elle est disponible.
    Sinon, quelques expressions régulières assurent un fonctionnement de repli.
    """
    is_bot_fallback, bot_name = _detect_bot(value)
    if parse_user_agent_lib is not None:
        ua = parse_user_agent_lib(value or "")
        is_bot = bool(ua.is_bot or is_bot_fallback)
        if is_bot and bot_name is None:
            bot_name = ua.device.family or ua.browser.family or "Other Bot"
        device_type = "Bot" if is_bot else ("Mobile" if ua.is_mobile else
                      "Tablet" if ua.is_tablet else "PC" if ua.is_pc else "Other")
        return {
            "browser": ua.browser.family or None,
            "browser_version": ua.browser.version_string or None,
            "os": ua.os.family or None,
            "os_version": ua.os.version_string or None,
            "device_type": device_type,
            "device_family": ua.device.family or None,
            "device_brand": ua.device.brand or None,
            "device_model": ua.device.model or None,
            "is_mobile": bool(ua.is_mobile), "is_tablet": bool(ua.is_tablet),
            "is_pc": bool(ua.is_pc), "is_bot": is_bot, "bot_name": bot_name,
            "client_type": "Bot" if is_bot else "Human",
        }

    # Repli sans dépendance externe : volontairement plus simple.
    low = (value or "").lower()
    browser, version = None, None
    for name, pat in [("Edge", r"(?:edg|edge)/([\d.]+)"), ("Chrome", r"chrome/([\d.]+)"),
                      ("Firefox", r"firefox/([\d.]+)"), ("Safari", r"version/([\d.]+).*safari/")]:
        m = re.search(pat, low)
        if m: browser, version = name, m.group(1); break
    os_name, os_version = None, None
    m = re.search(r"android\s+([\d.]+)", low)
    if m: os_name, os_version = "Android", m.group(1)
    elif "windows" in low: os_name = "Windows"
    elif "iphone" in low or "ipad" in low: os_name = "iOS"
    elif "mac os x" in low: os_name = "Mac OS X"
    elif "linux" in low: os_name = "Linux"
    is_mobile = "mobile" in low or "android" in low or "iphone" in low
    is_tablet = "ipad" in low or "tablet" in low
    is_pc = not is_bot_fallback and not is_mobile and not is_tablet
    return {
        "browser": "Bot" if is_bot_fallback and browser is None else browser,
        "browser_version": version, "os": os_name, "os_version": os_version,
        "device_type": "Bot" if is_bot_fallback else "Tablet" if is_tablet else "Mobile" if is_mobile else "PC" if is_pc else "Other",
        "device_family": None, "device_brand": None, "device_model": None,
        "is_mobile": is_mobile, "is_tablet": is_tablet, "is_pc": is_pc,
        "is_bot": is_bot_fallback, "bot_name": bot_name,
        "client_type": "Bot" if is_bot_fallback else "Human",
    }


def classify_referer(ref: str, domain: Optional[str], query: Optional[str], site_domain: Optional[str]) -> dict:
    """Classe le Referer : Direct, Internal, Search Engine, Social ou External.

    La fonction tente aussi d’identifier le moteur/réseau social et d’extraire
    le terme recherché depuis les paramètres q, p ou text.
    """
    if not ref or ref == "-":
        return {"referer_type": "Direct", "search_engine": None, "search_query": None,
                "social_network": None, "is_search_engine": False,
                "is_social": False, "is_direct": True}
    d = (domain or "").lower()
    if site_domain and (d == site_domain.lower() or d.endswith("." + site_domain.lower())):
        rtype, se, social = "Internal", None, None
    else:
        se = next((name for pattern, name in SEARCH_ENGINES.items() if pattern in d), None)
        social = next((name for pattern, name in SOCIAL_NETWORKS.items()
                       if d == pattern or d.endswith("." + pattern)), None)
        rtype = "Search Engine" if se else "Social" if social else "External"
    params = parse_qs(query or "", keep_blank_values=True)
    term = next((params[k][0] for k in ("q", "p", "text") if k in params and params[k]), None)
    return {"referer_type": rtype, "search_engine": se,
            "search_query": unquote_plus(term) if term else None,
            "social_network": social, "is_search_engine": bool(se),
            "is_social": bool(social), "is_direct": False}


def geoip_fields(ip_value: str, reader) -> dict:
    """Ajoute pays, ville et coordonnées si une base GeoIP2 est fournie.

    L’enrichissement est volontairement optionnel : sans lecteur GeoIP, les
    colonnes sont tout de même créées mais restent à None.
    """
    empty = {"geo_country": None, "geo_country_code": None, "geo_city": None,
             "geo_latitude": None, "geo_longitude": None, "geo_timezone": None}
    if reader is None:
        return empty
    try:
        r = reader.city(ip_value)
        return {"geo_country": r.country.name, "geo_country_code": r.country.iso_code,
                "geo_city": r.city.name, "geo_latitude": r.location.latitude,
                "geo_longitude": r.location.longitude, "geo_timezone": r.location.time_zone}
    except Exception:
        return empty


def build_dataframe(log_file: str | Path, site_domain: Optional[str] = None,
                    geoip_db: Optional[str | Path] = None) -> pd.DataFrame:
    """Lit le fichier de log et retourne le DataFrame Pandas enrichi.

    Paramètres
    ----------
    log_file : chemin du fichier access log.
    site_domain : domaine du site, utilisé pour reconnaître les Referer internes.
    geoip_db : chemin optionnel vers une base GeoLite2-City.mmdb.

    Le nombre de lignes non reconnues est conservé dans
    ``df.attrs["invalid_lines"]``.
    """
    log_file = Path(log_file)
    if not log_file.exists():
        raise FileNotFoundError(f"Fichier introuvable : {log_file}")

    reader = None
    if geoip_db:
        if geoip2 is None:
            raise RuntimeError("geoip2 n'est pas installé : pip install geoip2")
        reader = geoip2.database.Reader(str(geoip_db))

    # Caches propres à cet appel : mémoire bornée et aucun mélange entre
    # domaines de site ou bases GeoIP. Les dictionnaires cachés restent en lecture.
    cached_ip = lru_cache(maxsize=16_384)(parse_ip_fields)
    cached_url = lru_cache(maxsize=16_384)(parse_request_url)
    cached_ua = lru_cache(maxsize=4_096)(parse_user_agent)

    @lru_cache(maxsize=16_384)
    def cached_referer(value):
        fields = parse_url_fields(value, "referer")
        return {
            **fields,
            **classify_referer(value, fields["referer_domain"],
                               fields["referer_query"], site_domain),
        }

    @lru_cache(maxsize=16_384)
    def cached_geoip(value):
        return geoip_fields(value, reader)

    empty_geoip = geoip_fields("", None)
    invalid = 0

    def parsed_rows(lines):
        """Lit progressivement le fichier et conserve les numéros physiques."""
        nonlocal invalid
        for line_no, line in enumerate(lines, 1):
            match = LOG_RE.match(line.rstrip("\n"))
            if match is None:
                invalid += 1
                continue
            yield {**match.groupdict(), "line_number": line_no}

    try:
        with log_file.open("r", encoding="utf-8", errors="replace") as f:
            rows = [
                {
                    **row,
                    **cached_ip(row["ip"]),
                    **cached_url(row["url"]),
                    **cached_referer(row["referer"]),
                    **cached_ua(row["user_agent"]),
                    **(cached_geoip(row["ip"]) if reader is not None else empty_geoip),
                }
                for row in parsed_rows(f)
            ]
    finally:
        if reader is not None:
            reader.close()
        # Libère les caches avant la construction du DataFrame (pic mémoire).
        for cached in (cached_ip, cached_url, cached_ua, cached_referer, cached_geoip):
            cached.cache_clear()

    # 3) Conversion de la liste de dictionnaires en DataFrame Pandas.
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("Aucune ligne n'a pu être parsée.")
    # 4) Typage des colonnes importantes : date, code HTTP et nombre d’octets.
    df["datetime"] = pd.to_datetime(df["datetime"], format="%d/%b/%Y:%H:%M:%S %z", errors="coerce", utc=True)
    df["status"] = pd.to_numeric(df["status"], errors="coerce").astype("Int64")
    df["bytes"] = pd.to_numeric(df["bytes"].replace("-", pd.NA), errors="coerce").astype("Int64")
    df.attrs["invalid_lines"] = invalid
    return df


def find_default_log() -> Path:
    """Cherche automatiquement access01.log puis access_01.log dans le dossier courant."""
    for name in ("access01.log", "access_01.log"):
        p = Path(name)
        if p.exists(): return p
    return Path("access01.log")


def main() -> None:
    """Point d’entrée en ligne de commande : lecture, aperçu et exports optionnels."""
    # argparse rend le script utilisable directement depuis un terminal.
    ap = argparse.ArgumentParser(description="Parse et enrichit un access log Web.")
    ap.add_argument("logfile", nargs="?", default=str(find_default_log()))
    ap.add_argument("--site-domain", default=None, help="Domaine du site, ex. zanbil.ir")
    ap.add_argument("--geoip-db", default=None, help="Chemin vers GeoLite2-City.mmdb")
    ap.add_argument("--csv", default=None, help="Fichier CSV de sortie")
    ap.add_argument("--parquet", default=None, help="Fichier Parquet de sortie")
    args = ap.parse_args()

    df = build_dataframe(args.logfile, args.site_domain, args.geoip_db)
    print(f"Lignes parsées : {len(df):,}")
    print(f"Lignes rejetées : {df.attrs.get('invalid_lines', 0):,}")
    print(f"Colonnes : {len(df.columns)}")
    print(df.head(5).to_string())
    if parse_user_agent_lib is None:
        print("\nNOTE: 'user-agents' absent : parsing User-Agent de repli utilisé.")
    if tldextract is None:
        print("NOTE: 'tldextract' absent : domaine simplifié utilisé.")
    if not args.geoip_db:
        print("NOTE: GeoIP non activé (utilisez --geoip-db GeoLite2-City.mmdb).")
    if args.csv:
        df.to_csv(args.csv, index=False); print(f"CSV écrit : {args.csv}")
    if args.parquet:
        df.to_parquet(args.parquet, index=False); print(f"Parquet écrit : {args.parquet}")

if __name__ == "__main__":
    main()
