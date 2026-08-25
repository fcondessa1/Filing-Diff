"""Does boilerplate stripping fix the false pairing found by tune.py?"""
from diff2 import token_similarity

intro_old = ("The Company's business, reputation, results of operations, financial condition "
 "and stock price can be affected by a number of factors, whether currently known or "
 "unknown, including those described below.")

supply_new = ("Therefore, the Company remains subject to significant risks of supply shortages "
 "and price increases that can materially adversely affect its business, results of "
 "operations, financial condition and stock price.")

intro_new = ("The following summarizes factors that could have a material adverse effect on the "
 "Company's business, reputation, results of operations, financial condition and stock "
 "price. The Company may not be able to accurately predict, control or mitigate these risks.")

print("FALSE pair (intro vs supply):  ", round(token_similarity(intro_old, supply_new), 3))
print("TRUE  pair (intro vs intro):   ", round(token_similarity(intro_old, intro_new), 3))
print()
print("Goal: TRUE > FALSE. Before stripping they were 0.283 vs 0.333 (inverted).")
