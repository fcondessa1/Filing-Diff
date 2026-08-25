"""
Minimal SEC EDGAR client.

EDGAR is free and has no API key, but it DOES enforce two rules:
  1. You must send a User-Agent identifying yourself (name + email).
  2. Max 10 requests/second. We stay well under.

Violating #1 gets you a 403. Violating #2 gets you IP-banned.
"""

import time
import requests

# CHANGE THIS. EDGAR will 403 you otherwise.
USER_AGENT = "Your Name your.email@example.com"

HEADERS = {"User-Agent": USER_AGENT}
_last_call = 0.0


def _get(url: str) -> requests.Response:
    """Rate-limited GET. Keeps us at ~5 req/sec, half the allowed ceiling."""
    global _last_call
    elapsed = time.time() - _last_call
    if elapsed < 0.2:
        time.sleep(0.2 - elapsed)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    _last_call = time.time()
    resp.raise_for_status()
    return resp


def get_cik(ticker: str) -> str:
    """
    Map a ticker to a zero-padded 10-digit CIK.

    EDGAR indexes by CIK, not ticker. This mapping file is the official one
    and is small enough to fetch on demand; cache it locally once you have
    more than a handful of tickers.
    """
    data = _get("https://www.sec.gov/files/company_tickers.json").json()
    ticker = ticker.upper()
    for entry in data.values():
        if entry["ticker"].upper() == ticker:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker not found in EDGAR mapping: {ticker}")


def list_filings(cik: str, form_types=("10-K", "10-Q"), limit: int = 8) -> list[dict]:
    """
    Return recent filings of the given form types, newest first.

    The submissions endpoint returns the last ~1000 filings as parallel arrays
    (not a list of objects), so we zip them back into dicts.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    recent = _get(url).json()["filings"]["recent"]

    out = []
    for form, date, accession, primary_doc in zip(
        recent["form"],
        recent["filingDate"],
        recent["accessionNumber"],
        recent["primaryDocument"],
    ):
        if form not in form_types:
            continue
        acc_nodash = accession.replace("-", "")
        out.append(
            {
                "form": form,
                "filing_date": date,
                "accession": accession,
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{acc_nodash}/{primary_doc}"
                ),
            }
        )
        if len(out) >= limit:
            break
    return out


def fetch_document(url: str) -> str:
    """Download the raw filing HTML."""
    return _get(url).text


if __name__ == "__main__":
    cik = get_cik("AAPL")
    print(f"CIK: {cik}")
    for f in list_filings(cik, limit=4):
        print(f"{f['filing_date']}  {f['form']:6}  {f['url']}")
