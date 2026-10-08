from sections import extract_item, html_to_text

# Synthetic filing: TOC at top (the trap), real body below.
html = """<html><body>
<table><tr><td>Financials</td></tr></table>
<p>Item 1A. Risk Factors .......... 12</p>
<p>Item 1B. Unresolved Staff Comments .......... 40</p>
<p>Item 7. MD&amp;A .......... 55</p>
<p>Item 8. Financial Statements .......... 70</p>
<hr>
<p>ITEM 1A &ndash; RISK FACTORS</p>
<p>""" + ("Our business faces substantial competition. " * 40) + """</p>
<p>Item 1B. Unresolved Staff Comments</p>
<p>None.</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>""" + ("Revenue increased due to volume growth. " * 40) + """</p>
<p>Item 8. Financial Statements</p>
</body></html>"""

text = html_to_text(html)
risk = extract_item(text, "1A")
mda = extract_item(text, "7")

print("1A found:", risk is not None, "| len:", len(risk or ""))
print("1A starts:", repr((risk or "")[:45]))
print("1A leaked into 1B?", "Unresolved Staff" in (risk or ""))
print()
print("7  found:", mda is not None, "| len:", len(mda or ""))
print("7  starts:", repr((mda or "")[:45]))
print("7  leaked into Item 8?", "Financial Statements" in (mda or ""))
print()
print("Table dropped?", "Financials" not in text)

# --------------------------------------------------------------------------- #
# Headings laid out as tables (Amazon's 10-Qs) and short "no changes" sections
# (IonQ and D-Wave Q1 10-Qs), both found on the first multi-company digest.
# --------------------------------------------------------------------------- #

toc_row = "<tr><td>Item {n}.</td><td>{name}</td><td>{page}</td></tr>"
amazon_like = ("<html><body><table>"
    + toc_row.format(n="1", name="Legal Proceedings", page=38)
    + toc_row.format(n="1A", name="Risk Factors", page=38)
    + toc_row.format(n="2", name="Unregistered Sales of Equity Securities", page=50)
    + "</table>"
    + "<p>See Item 1A of Part II, “Risk Factors.”</p>"
    # Layout tables often start with an empty row that only sets column widths.
    + "<table><tr><td style='width:10%'></td><td></td></tr>"
      "<tr><td>Item 1A.</td><td>Risk Factors</td></tr></table>"
    + "<p>" + "Please carefully consider the following risks. " * 40 + "</p>"
    + "<table><tr><td>Item 2.</td><td>Unregistered Sales of Equity Securities</td></tr></table>"
    + "<p>None.</p></body></html>")
t = html_to_text(amazon_like)
risk = extract_item(t, "1A")

statement = ("<html><body><p>Item 1A. Risk Factors</p><p>There have been no material changes "
             "to the risk factors disclosed in our Annual Report on Form 10-K for the year ended "
             "December 31, 2025.</p><p>Item 2. Unregistered Sales</p><p>None.</p></body></html>")
s = html_to_text(statement)

checks = {
    "heading inside a one-row table is found": risk is not None and risk.startswith("Item 1A."),
    "section ends at the Item 2 heading table": risk is not None and "Unregistered" not in risk,
    "table of contents still dropped": "Legal Proceedings" not in t,
    "short 'no changes' section is not returned by default": extract_item(s, "1A") is None,
    "but is returned when asked for": "no material changes" in (extract_item(s, "1A", min_chars=100) or ""),
}
print()
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
print(f"\n{sum(checks.values())}/{len(checks)} table and statement checks passed")
