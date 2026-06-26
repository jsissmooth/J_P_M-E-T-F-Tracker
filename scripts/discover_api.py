import sys
import json
import requests
from playwright.sync_api import sync_playwright

CUSIP = "46654Q203"  # JEPQ
BASE  = "https://am.jpmorgan.com/FundsMarketingHandler"

def get_version():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        found = []
        def handle_response(response):
            url = response.url
            if "FundsMarketingHandler" in url and "version=" in url:
                import urllib.parse
                params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                if "version" in params:
                    found.append(params["version"][0])
        page.on("response", handle_response)
        page.goto(
            "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-nasdaq-equity-premium-income-etf-etf-shares-46654q203",
            wait_until="networkidle", timeout=60000
        )
        page.wait_for_timeout(5000)
        browser.close()
        return found[0] if found else "9.12"

print("Getting version...", file=sys.stderr)
version = get_version()
print("Version: {}".format(version), file=sys.stderr)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://am.jpmorgan.com/",
    "Accept": "application/json, text/plain, */*",
}

url = "{}/product-data?cusip={}&country=us&role=adv&language=en&userLoggedIn=false&version={}".format(
    BASE, CUSIP, version)

print("Fetching product-data...", file=sys.stderr)
r = requests.get(url, headers=headers, timeout=30)
data = r.json()

def explore(obj, path="", depth=0):
    """Recursively explore the structure to find arrays that look like holdings."""
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            explore(v, path + "." + k, depth + 1)
    elif isinstance(obj, list):
        print("ARRAY at {}: {} items".format(path, len(obj)))
        if obj and isinstance(obj[0], dict):
            print("  First item keys: {}".format(list(obj[0].keys())))
            # if it looks like a holding, print more
            keys = list(obj[0].keys())
            holding_signals = ["ticker", "cusip", "weight", "shares", "name",
                               "isin", "percent", "holding", "security", "position",
                               "quantity", "market", "asset"]
            if any(any(sig in k.lower() for sig in holding_signals) for k in keys):
                print("  ** LOOKS LIKE HOLDINGS **")
                print("  First item: {}".format(json.dumps(obj[0])[:400]))

fund_data = data.get("fundData", data)
print("\n=== EXPLORING STRUCTURE ===")
explore(fund_data)

# also print all top-level keys and their types
print("\n=== TOP LEVEL KEYS ===")
if isinstance(fund_data, dict):
    for k, v in fund_data.items():
        if isinstance(v, list):
            print("  {} -> list({})".format(k, len(v)))
        elif isinstance(v, dict):
            print("  {} -> dict({} keys)".format(k, len(v)))
        else:
            print("  {} -> {}".format(k, type(v).__name__))
