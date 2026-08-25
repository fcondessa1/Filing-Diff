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
