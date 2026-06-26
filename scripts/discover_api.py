import sys
import json
import requests
from playwright.sync_api import sync_playwright

# CUSIPs extracted from the ETF page URLs
ETFS = {
    "JEPQ": "46654Q203",
    "JEPI": "46641Q332",
    "SCDS": "46654Q666",
    "JMOM": "46641Q779",
    "JMEE": "46641Q118",
    "JPSE": "46641Q845",
    "JVAL": "46641Q753",
    "JTEK": "46654Q732",
    "JPSV": "46654Q708",
    "LVDS": "46654Q583",
    "MCDS": "46654Q674",
    "JPME": "46641Q886",
    "JPRE": "46641Q126",
    "JQUA": "46641Q761",
    "JAVA": "46641Q167",
    "JPEF": "46654Q781",
}

BASE = "https://am.jpmorgan.com/FundsMarketingHandler"

def get_version():
    """Grab the version parameter from the main JPM page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        version_found = []

        def handle_response(response):
            url = response.url
            if "FundsMarketingHandler" in url and "version=" in url:
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                if "version" in params:
                    version_found.append(params["version"][0])

        page.on("response", handle_response)
        page.goto(
            "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-nasdaq-equity-premium-income-etf-etf-shares-46654q203",
            wait_until="networkidle", timeout=60000
        )
        page.wait_for_timeout(5000)
        browser.close()
        return version_found[0] if version_found else "9.12"

print("Getting version parameter...", file=sys.stderr)
version = get_version()
print("Version: {}".format(version), file=sys.stderr)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://am.jpmorgan.com/",
    "Accept": "application/json, text/plain, */*",
}

# Try JEPQ with several endpoint patterns
cusip = "46654Q203"
endpoints = [
    "{}/product-data?cusip={}&country=us&role=adv&language=en&userLoggedIn=false&version={}".format(BASE, cusip, version),
    "{}/holdings?cusip={}&country=us&role=adv&language=en&userLoggedIn=false&version={}".format(BASE, cusip, version),
    "{}/portfolio?cusip={}&country=us&role=adv&language=en&userLoggedIn=false&version={}".format(BASE, cusip, version),
    "{}/fund-holdings?cusip={}&country=us&role=adv&language=en&userLoggedIn=false&version={}".format(BASE, cusip, version),
    "{}/portfolioHoldings?cusip={}&country=us&role=adv&language=en&userLoggedIn=false&version={}".format(BASE, cusip, version),
]

for url in endpoints:
    print("\nTrying: {}".format(url), file=sys.stderr)
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print("  Status: {}".format(r.status_code), file=sys.stderr)
        if r.status_code == 200:
            data = r.json()
            text = json.dumps(data)
            print("  Response length: {} chars".format(len(text)), file=sys.stderr)
            print("  Top-level keys: {}".format(list(data.keys()) if isinstance(data, dict) else "list"), file=sys.stderr)
            # print first 2000 chars
            print("  Preview: {}".format(text[:2000]), file=sys.stderr)
        else:
            print("  Body: {}".format(r.text[:200]), file=sys.stderr)
    except Exception as e:
        print("  Error: {}".format(e), file=sys.stderr)
