"""Regression test for the two bugs found on Apple's real 10-K."""
from sections import html_to_text, extract_item
from diff import split_paragraphs

# Mimics Apple: <div>/<span> paragraphs (no <p>), a TOC, and a
# forward-looking-statements preamble that cross-references Item 1A.
def make(risk_body, n=30):
    paras = "".join(
        f'<div><span>{risk_body} Sentence {i} of the section body text here.</span></div>'
        for i in range(n)
    )
    return f"""<html><body>
    <table><tr><td>TOC table</td></tr></table>
    <div><span>Item 1A. Risk Factors .......... 12</span></div>
    <div><span>Item 1B. Unresolved Staff Comments .......... 40</span></div>
    <div><span>This section contains forward-looking statements. Risks are
    described in Item 1A of this Form 10-K under the heading Risk Factors.
    The Company assumes no obligation to revise or update any forward-looking
    statements for any reason, except as required by law and applicable rules.</span></div>
    <div><span>ITEM 1A. RISK FACTORS</span></div>
    {paras}
    <div><span>Item 1B. Unresolved Staff Comments</span></div>
    <div><span>None.</span></div>
    </body></html>"""

html = make("Our business faces substantial competition and supply constraints.")
text = html_to_text(html)
sec = extract_item(text, "1A")

print("=== Bug 2: start boundary ===")
print("starts with real heading? ", (sec or "").lstrip().upper().startswith("ITEM 1A"))
print("swallowed FLS preamble?   ", "forward-looking statements" in (sec or "").lower())
print()
print("=== Bug 1: paragraph splitting ===")
paras = split_paragraphs(sec or "", min_chars=50)
print(f"section chars: {len(sec or ''):,}")
print(f"paragraphs:    {len(paras)}   (blob bug would give 1-3)")
print(f"largest para:  {max((len(p) for p in paras), default=0):,} chars")
print()
print("=== Sanity ===")
print("leaked into 1B?", "Unresolved Staff" in (sec or ""))
