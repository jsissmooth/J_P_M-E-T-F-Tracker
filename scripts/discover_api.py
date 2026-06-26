import sys
import json
from playwright.sync_api import sync_playwright

ETFS = {
    "JEPQ": "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-nasdaq-equity-premium-income-etf-etf-shares-46654q203",
    "JEPI": "https://am.jpmorgan.com/us/en/asset-management/adv/products/jpmorgan-equity-premium-income-etf-etf-shares-46641q332",
}

def discover(ticker, url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )

        captured_requests  = []
        captured_responses = []

        def handle_request(request):
            url_r = request.url
            method = request.method
            if method == "POST" or any(k in url_r for k in [
                "holdings", "portfolio", "fund", "positions",
                "api", "graphql", "data", "etf"
            ]):
                try:
                    captured_requests.append({
                        "url":    url_r,
                        "method": method,
                        "body":   request.post_data or "",
                        "headers": dict(request.headers),
                    })
                except Exception:
                    pass

        def handle_response(response):
            try:
                url_r = response.url
                ct = response.headers.get("content-type", "")
                if "json" in ct and any(k in url_r for k in [
                    "holdings", "portfolio", "fund", "positions",
                    "api", "graphql", "data", "etf", "jpmorgan"
                ]):
                    try:
                        data = response.json()
                        text = json.dumps(data)
                        if len(text) > 200:
                            captured_responses.append({
                                "url":  url_r,
                                "data": text[:1000],
                            })
                    except Exception:
                        pass
            except Exception:
                pass

        page = context.new_page()
        page.on("request",  handle_request)
        page.on("response", handle_response)

        print("Loading {}...".format(url), file=sys.stderr)
        page.goto(url, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(8000)

        # scroll to trigger lazy loading
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)

        # try clicking a Holdings tab if it exists
        for label in ["Holdings", "Portfolio", "Portfolio Holdings"]:
            try:
                btn = page.get_by_text(label, exact=True).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    print("  Clicked: {}".format(label), file=sys.stderr)
                    page.wait_for_timeout(5000)
                    break
            except Exception:
                pass

        page.wait_for_timeout(5000)

        print("\n=== REQUESTS for {} ===".format(ticker), file=sys.stderr)
        for r in captured_requests[-20:]:
            print("  [{}] {}".format(r["method"], r["url"]), file=sys.stderr)
            if r["body"]:
                print("    body: {}".format(r["body"][:200]), file=sys.stderr)

        print("\n=== JSON RESPONSES for {} ===".format(ticker), file=sys.stderr)
        for r in captured_responses:
            print("  URL: {}".format(r["url"]), file=sys.stderr)
            print("  Data: {}".format(r["data"][:400]), file=sys.stderr)

        browser.close()

for ticker, url in ETFS.items():
    discover(ticker, url)
    print("\n" + "="*60 + "\n", file=sys.stderr)
