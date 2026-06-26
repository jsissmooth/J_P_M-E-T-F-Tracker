import json
import os
import re
import sys
import requests
from datetime import date
import pandas_market_calendars as mcal

BASE_URL = "https://am.jpmorgan.com/FundsMarketingHandler/product-data"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://am.jpmorgan.com/",
    "Accept": "application/json, text/plain, */*",
}


def is_nyse_trading_day(d):
    nyse = mcal.get_calendar("NYSE")
    return not nyse.schedule(start_date=d.isoformat(), end_date=d.isoformat()).empty


def get_version():
    """Extract the version parameter from JPMorgan's product page HTML."""
    try:
        url = ("https://am.jpmorgan.com/us/en/asset-management/adv/products/"
               "jpmorgan-nasdaq-equity-premium-income-etf-etf-shares-46654q203")
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }, timeout=30)
        match = re.search(r'version=([\d\.]+_[\d]+)', r.text)
        if match:
            return match.group(1)
        match = re.search(r'"version"\s*:\s*"([\d\.]+_[\d]+)"', r.text)
        if match:
            return match.group(1)
    except Exception as e:
        print("  Warning: could not extract version: {}".format(e), file=sys.stderr)
    return "9.12"


def fetch_fund_data(cusip, version):
    url = ("{}?cusip={}&country=us&role=adv&language=en"
           "&userLoggedIn=false&version={}").format(BASE_URL, cusip, version)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_holdings(fund_data):
    fd = fund_data.get("fundData", {})

    # get effective date from dailyHoldingsAll metadata
    daily_all = fd.get("dailyHoldingsAll", {}) or {}
    holding_date = daily_all.get("date") or daily_all.get("effectiveDate")

    raw = daily_all.get("data", []) or []
    if not raw:
        # fallback to dailyHoldings (top 10)
        daily = fd.get("dailyHoldings", {}) or {}
        raw = daily.get("data", []) or []

    records = []
    for h in raw:
        records.append({
            "name":         h.get("securityDescription") or "",
            "ticker":       h.get("securityTicker") or "",
            "identifier":   h.get("securityId") or "",
            "pct_of_fund":  round(float(h.get("netAssetValuePercent") or 0), 6),
            "quantity":     h.get("shares"),
            "market_value": h.get("marketValue"),
            "sector":       h.get("sector") or "",
            "industry":     h.get("industry") or "",
            "security_type": h.get("securityType") or "",
        })

    return records, holding_date


def get_etf_data_dir(ticker):
    d = os.path.join(DATA_DIR, ticker)
    os.makedirs(d, exist_ok=True)
    return d


def save_snapshot(records, today_str, ticker):
    data_dir = get_etf_data_dir(ticker)
    payload = {"date": today_str, "ticker": ticker, "holdings": records}
    with open(os.path.join(data_dir, "{}.json".format(today_str)), "w") as f:
        json.dump(payload, f, indent=2)
    with open(os.path.join(data_dir, "latest.json"), "w") as f:
        json.dump(payload, f, indent=2)


def find_prior_snapshot(today_str, ticker):
    data_dir = get_etf_data_dir(ticker)
    files = sorted(
        f for f in os.listdir(data_dir)
        if f.endswith(".json") and f not in ("latest.json", "diff.json", "history.json")
    )
    prior = [f for f in files if f.replace(".json", "") < today_str]
    return os.path.join(data_dir, prior[-1]) if prior else None


def compute_diff(today_records, prior_records, today_str, prior_date_str, etf_ticker):
    today_map = {r["ticker"] or r["name"]: r for r in today_records}
    prior_map = {r["ticker"] or r["name"]: r for r in prior_records}
    all_keys  = sorted(set(today_map) | set(prior_map))
    rows = []
    for key in all_keys:
        t = today_map.get(key)
        p = prior_map.get(key)
        if t and p:
            q_today   = t["quantity"] or 0
            q_prior   = p["quantity"] or 0
            pct_today = t["pct_of_fund"] or 0
            pct_prior = p["pct_of_fund"] or 0
            qty_chg   = ((q_today - q_prior) / q_prior * 100) if q_prior != 0 else 0
            rows.append({
                "ticker":              t.get("ticker") or p.get("ticker") or "",
                "name":                t.get("name") or p.get("name") or "",
                "identifier":          t.get("identifier") or "",
                "sector":              t.get("sector") or "",
                "status":              "changed" if round(qty_chg, 6) != 0 else "unchanged",
                "quantity_today":      q_today,
                "quantity_prior":      q_prior,
                "quantity_pct_change": round(qty_chg, 4),
                "pct_of_fund_today":   pct_today,
                "pct_of_fund_prior":   pct_prior,
                "pct_of_fund_change":  round(pct_today - pct_prior, 4),
                "market_value_today":  t.get("market_value"),
            })
        elif t:
            rows.append({
                "ticker": t.get("ticker") or "", "name": t.get("name") or "",
                "identifier": t.get("identifier") or "", "sector": t.get("sector") or "",
                "status": "added",
                "quantity_today": t["quantity"] or 0, "quantity_prior": None,
                "quantity_pct_change": None,
                "pct_of_fund_today": t["pct_of_fund"] or 0, "pct_of_fund_prior": None,
                "pct_of_fund_change": None, "market_value_today": t.get("market_value"),
            })
        else:
            rows.append({
                "ticker": p.get("ticker") or "", "name": p.get("name") or "",
                "identifier": p.get("identifier") or "", "sector": p.get("sector") or "",
                "status": "removed",
                "quantity_today": None, "quantity_prior": p["quantity"] or 0,
                "quantity_pct_change": None, "pct_of_fund_today": None,
                "pct_of_fund_prior": p["pct_of_fund"] or 0,
                "pct_of_fund_change": None, "market_value_today": None,
            })
    return {"date": today_str, "ticker": etf_ticker, "prior_date": prior_date_str, "diff": rows}


def append_history(today_str, diff, etf_ticker):
    data_dir = get_etf_data_dir(etf_ticker)
    history_path = os.path.join(data_dir, "history.json")
    history = []
    if os.path.exists(history_path):
        with open(history_path) as f:
            history = json.load(f)
    entry = {"date": today_str, "prior_date": diff["prior_date"]}
    if entry not in history:
        history.append(entry)
        history.sort(key=lambda x: x["date"], reverse=True)
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)


def process_etf(etf_ticker, cusip, today_str, version):
    print("Fetching {} (CUSIP: {})...".format(etf_ticker, cusip), file=sys.stderr)
    try:
        fund_data = fetch_fund_data(cusip, version)
        records, holding_date = parse_holdings(fund_data)

        if not records:
            print("  No holdings returned.", file=sys.stderr)
            return

        print("  {} holdings found (date: {}).".format(len(records), holding_date), file=sys.stderr)
        save_snapshot(records, today_str, etf_ticker)

        prior_path = find_prior_snapshot(today_str, etf_ticker)
        if not prior_path:
            diff_rows = []
            for r in records:
                diff_rows.append({
                    "ticker":              r.get("ticker") or "",
                    "name":                r.get("name") or "",
                    "identifier":          r.get("identifier") or "",
                    "sector":              r.get("sector") or "",
                    "status":              "unchanged",
                    "quantity_today":      r["quantity"] or 0,
                    "quantity_prior":      r["quantity"] or 0,
                    "quantity_pct_change": 0,
                    "pct_of_fund_today":   r["pct_of_fund"] or 0,
                    "pct_of_fund_prior":   r["pct_of_fund"] or 0,
                    "pct_of_fund_change":  0,
                    "market_value_today":  r.get("market_value"),
                })
            diff = {"date": today_str, "ticker": etf_ticker, "prior_date": None, "diff": diff_rows}
        else:
            with open(prior_path) as f:
                prior_data = json.load(f)
            diff = compute_diff(records, prior_data["holdings"], today_str, prior_data["date"], etf_ticker)

        data_dir = get_etf_data_dir(etf_ticker)
        with open(os.path.join(data_dir, "diff.json"), "w") as f:
            json.dump(diff, f, indent=2)

        append_history(today_str, diff, etf_ticker)

        changed = sum(1 for r in diff["diff"] if r["status"] == "changed")
        added   = sum(1 for r in diff["diff"] if r["status"] == "added")
        removed = sum(1 for r in diff["diff"] if r["status"] == "removed")
        print("  Done -- {} changed | {} added | {} removed".format(
            changed, added, removed), file=sys.stderr)

    except Exception as e:
        print("  ERROR: {}".format(e), file=sys.stderr)


def main():
    today_str = date.today().isoformat()
    today     = date.today()

    if not is_nyse_trading_day(today):
        print("{} is not a NYSE trading day -- skipping.".format(today_str), file=sys.stderr)
        sys.exit(0)

    print("Getting API version...", file=sys.stderr)
    version = get_version()
    print("Version: {}".format(version), file=sys.stderr)

    print("Running for {}...".format(today_str), file=sys.stderr)
    for etf_ticker, cusip in ETFS.items():
        process_etf(etf_ticker, cusip, today_str, version)
    print("All done.", file=sys.stderr)


if __name__ == "__main__":
    main()
