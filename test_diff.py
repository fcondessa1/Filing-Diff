from diff import diff_sections

old = """
We face intense competition in all of our markets, which could reduce our margins and market share over time as competitors introduce comparable products at lower price points across our core segments.

Supply chain disruption in Asia could materially affect our ability to deliver products on schedule, particularly given our concentration of manufacturing partners in a small number of facilities.

Our reliance on a single cloud provider exposes us to service interruptions that could disrupt customer operations and damage our reputation in the enterprise market segment.
"""

new = """
We face intense competition in all of our markets, which could reduce our margins and market share over time as competitors introduce comparable products at lower price points across our core segments.

Supply chain disruption in Asia could materially and adversely affect our ability to deliver products on schedule, and we now expect these constraints to persist through the next fiscal year given our concentration of manufacturing partners.

New and evolving artificial intelligence regulation in the European Union may impose compliance obligations that increase our operating costs and delay product launches in that region substantially.
"""

r = diff_sections(old, new, min_chars=120)
print("stats:", r["stats"])
print()
print("ADDED   :", r["added"][0][:80], "...")
print("REMOVED :", r["removed"][0][:80], "...")
print("MODIFIED:", f"sim={r['modified'][0]['similarity']}", "|", r["modified"][0]["new"][:70], "...")
