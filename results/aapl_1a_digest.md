# AAPL Item 1A: what changed

Model `claude-haiku-4-5-20251001`, prompts: added v1, modified v1, removed v2. 63 changes summarised.

| check | count |
|---|---|
| verified | 57 |
| PARTLY VERIFIED | 6 |
| UNVERIFIED | 0 |

Tokens: 68,736 in / 11,634 out. Full-run cost $0.1269; this run $0.0252 (54 from cache).

**Removals.** The diff flagged 12 paragraphs as removed. 3 were skipped as merge artifacts (their text survives in a consolidated paragraph; see verify.py). The model judged the other 9 against the closest surviving text: 2 removed, 2 moved or reworded, 5 partly removed.

**Against hand verification**, the model's removal verdict matched 4 of 9. Taking the diff's label at face value would have matched 4 of 9.

| paragraph | hand | model | match |
|---|---|---|---|
| The Company distributes third-party applications for its pro… | partially_removed | partially_removed | ✓ |
| The Company's retail operations are subject to many factors … | removed | removed | ✓ |
| The Company relies on single-source outsourcing partners in … | moved_or_reworded | partially_removed | ✗ |
| The Company has invested in manufacturing process equipment,… | moved_or_reworded | partially_removed | ✗ |
| Some third-party digital content providers require the Compa… | removed | removed | ✓ |
| Payment card data is also subject to additional requirements… | moved_or_reworded | partially_removed | ✗ |
| The Company has historically experienced higher net sales in… | partially_removed | partially_removed | ✓ |
| Because of the following factors, as well as other factors a… | removed | moved_or_reworded | ✗ |
| The Company's business, results of operations and financial … | removed | moved_or_reworded | ✗ |

## High materiality (10)

- **ADDED** Added new risk factor regarding compliance with evolving online safety laws, particularly those protecting minors and requiring age verification.
  - *Why it matters:* The company identifies a new category of regulatory risk that could require significant product modifications, increase operational costs, and result in material liability.
  - ✓ (new) "The Company is also subject to new and changing laws and regulations regarding online safety, including enhanced protections for minors and mandatory age verification requirements."
  - ✓ (new) "These laws and regulations can increase regulatory risks by requiring complex compliance measures and significant modifications to the Company's products, services and operations."

- **MODIFIED** **[PARTLY VERIFIED]** The company expanded its trade risk disclosure to reflect increased U.S. tariffs announced in Q2 2025, added specific details about supply chain concentration and macroeconomic impacts, and clarified its sourcing includes U.S. facilities alongside Asia-Pacific partners.
  - *Why it matters:* The disclosure now explicitly addresses newly announced tariffs affecting the company's key sourcing countries and acknowledges potential semiconductor tariffs under investigation, representing a material change in the specific trade risks the company faces.
  - ✗ not found (new) "Beginning in the second quarter of 2025, new tariffs were announced on imports to the U.S. including additional tariffs on imports from China, India, Japan, South Korea, Taiwan, Vietnam and the European Union"
  - ✗ not found (new) "the U.S. Department of Commerce has initiated an investigation under Section 232 into imports of semiconductors, semiconductor manufacturing equipment, and their derivative products"
  - ✓ (old) "tensions between governments, including the U.S. and China, have in the past led to tariffs and other restrictions affecting the Company's business"

- **MODIFIED** Replaced broad risk factor introduction with a specific risk about competitive failure.
  - *Why it matters:* The company narrowed its risk disclosure from acknowledging multiple unknown factors to highlighting one specific competitive risk, materially changing the scope and emphasis of disclosed risks.
  - ✓ (old) "The Company's business, reputation, results of operations, financial condition and stock price can be affected by a number of factors, whether currently known or unknown"
  - ✓ (new) "If the Company is unable to compete successfully, its business, reputation, results of operations, financial condition and stock price can be materially adversely affected"

- **MODIFIED** **[PARTLY VERIFIED]** The company expanded its IP infringement risk disclosure to specifically address machine learning and artificial intelligence technologies, and added concerns about exposure to significant licensing costs and reputational harm.
  - *Why it matters:* The company identified a new and material risk related to AI/ML technologies that could result in licensing costs and reputational damage, reflecting emerging legal and operational challenges investors should evaluate.
  - ✗ not found (new) "This risk may be exacerbated by the use of new and emerging technologies, including machine learning and artificial intelligence, which can involve acquisition and use of copyrighted materials"
  - ✓ (new) "expose the Company to significant licensing costs, all of which can materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"
  - ✓ (old) "the Company believes licenses to such third-party intellectual property can generally be obtained on commercially reasonable terms"

- **MODIFIED** Apple added disclosure that it is subject to a court order preventing it from imposing commissions or fees on certain in-app purchases in the U.S.
  - *Why it matters:* A court order with potential revenue implications from a major product line represents a material legal constraint that investors need to understand.
  - ✓ (old) "the Company has made changes to its App Store, including actions taken in response to litigation"
  - ✓ (new) "is currently subject to a court order preventing it from imposing any commission or fee on certain purchases"

- **MODIFIED** Expanded the DMA risk disclosure to address global competition laws more broadly and added a statement that DMA compliance changes could materially adversely affect the company's business, reputation, and financial condition.
  - *Why it matters:* The addition of a forward-looking statement linking DMA compliance to potential material adverse effects on business and financial results is significant for investors assessing regulatory and operational risks.
  - ✓ (new) "Globally, several jurisdictions have adopted, or may in the future adopt, competition-related laws and regulations imposing wide-ranging obligations on technology companies"
  - ✓ (new) "Changes to the Company's business in response to the DMA or other laws and regulations could materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price."
  - ✓ (old) "and other jurisdictions may seek to require the Company to make changes to its business."

- **MODIFIED** **[PARTLY VERIFIED]** Added "stock price" to potential harms and disclosed that Google was found to violate antitrust laws with court-ordered remedies that could restrict the Company's ability to earn revenue from Google licensing arrangements.
  - *Why it matters:* The disclosure names a specific, material risk to a major revenue source (Google licensing) and reveals that legal remedies could prohibit Google from offering favorable commercial terms to the Company.
  - ✓ (new) "materially adversely affect the Company's business, results of operations, financial condition and stock price"
  - ✓ (new) "On August 5, 2024, Google was found to have violated U.S. antitrust laws."
  - ✗ not found (new) "remedies prohibiting Google from offering the Company commercial terms for search distribution. If implemented, these remedies could materially adversely affect the Company's ability to earn revenue"

- **MODIFIED** The company expanded its risk disclosure to include tariffs and trade restrictions as a downward pressure on margins, clarified that net sales are also at risk, and added a new specific risk about concentration in a single product category.
  - *Why it matters:* The new risks about tariffs, trade restrictions, and single-product-category concentration represent material changes to the company's risk profile that investors would care about for evaluating earnings volatility and diversification.
  - ✓ (new) "the imposition of new or increased tariffs and other trade restrictions, their overall magnitude and duration, and retaliatory actions"
  - ✓ (new) "the Company generates a significant portion of its net sales from a single product category and a decline in demand for that product could significantly impact net sales and gross margins"
  - ✓ (new) "The Company's net sales and gross margins are subject to volatility and downward pressure"

- **PARTLY REMOVED** The disclosure about App Store commission structure and risks was substantially reframed; the specific risk that commission reductions could materially harm the business was removed, replaced by a factual statement about a U.S. court order.
  - *Why it matters:* The loss of explicit disclosure that reduced commissions could materially affect financial performance is material because App Store commissions are a significant revenue source and investors need to understand financial risks from regulatory changes.
  - ✓ (old) "the Company retains a commission from sales of applications and sales of digital services or goods"
  - ✓ (old) "reductions in the rate of the commission that the Company retains on such sales, or if the rate of the commission is otherwise narrowed"
  - ✓ (new) "is currently subject to a court order preventing it from imposing any commission or fee on certain purchases"

- **REMOVED** The specific risks related to retail operations, including store construction and operation costs, retail partner relationships, inventory management, and lease renewal, are no longer disclosed.
  - *Why it matters:* Investors need visibility into operational challenges specific to retail, a distinct business channel with unique cost and partnership risks that differ materially from general pricing and supply chain pressures.
  - ✓ (old) "manage costs associated with retail store construction and operation; manage relationships with existing retail partners"
  - ✓ (old) "manage costs associated with fluctuations in the value of retail inventory; and obtain and renew leases in quality retail locations"
  - ✓ (old) "macroeconomic factors that could have an adverse effect on general retail activity"

## Medium materiality (32)

- **ADDED** Added risk disclosure that regulatory requirements, government investigations, and litigation could force product/service modifications and require sharing innovations with competitors, materially harming competitive advantage.
  - *Why it matters:* Investors care about IP protection and competitive advantages, but this articulates a known category of risk rather than introducing a new specific threat.
  - ✓ (new) "Regulatory requirements, government investigations and litigation can force the Company to withdraw from, or modify its products and services"
  - ✓ (new) "they may require the Company to share its innovations with competitors"
  - ✓ (new) "have a negative impact on the Company's competitive advantage and materially adversely affect its business"

- **ADDED** Added disclosure about risks from new laws and regulations specific to specialized industries and emerging technologies like AI and machine learning.
  - *Why it matters:* The company is acknowledging material regulatory headwinds in high-stakes sectors (health, finance) and AI/ML, which could affect product availability and compliance costs that investors monitor.
  - ✓ (new) "Risks and costs related to new and changing laws, regulations, executive orders, directives, and enforcement priorities increase"
  - ✓ (new) "specialized applications, including health and financial services, or as the Company expands the use of technologies, such as machine learning and artificial intelligence"
  - ✓ (new) "must navigate new legal, regulatory and ethical considerations relating to such technologies"

- **MODIFIED** The company expanded its risk disclosure to include competition from feature imitation, seamless component integration by competitors, and wearables market competition, while reframing the competitive threat more broadly across products and services.
  - *Why it matters:* The addition of specific competitive tactics like feature imitation and the inclusion of wearables market exposure represents a more detailed articulation of competitive risks that an attentive investor would find noteworthy, though the core competitive threat remains largely unchanged.
  - ✓ (new) "the Company faces significant competition as competitors imitate the Company's product features and applications within their products"
  - ✓ (new) "The Company also expects competition to intensify as competitors imitate the Company's approach to providing components seamlessly"
  - ✓ (new) "The Company has a minority market share in the global smartphone, personal computer, tablet and wearables markets"

- **MODIFIED** The company added risks related to recruiting skilled personnel, navigating global regulatory requirements, and potential reputational damage, while restructuring and expanding several existing risk factors around product introductions.
  - *Why it matters:* These changes add meaningful operational and regulatory considerations that would interest investors, though they largely elaborate on existing product transition risks rather than introducing fundamentally new categories of risk.
  - ✓ (new) "navigate global regulatory requirements and barriers to market access"
  - ✓ (new) "the Company's ability to recruit and retain highly skilled personnel to execute on its strategic initiatives"
  - ✓ (new) "can materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"

- **MODIFIED** The company clarified its outsourcing geography to include U.S. locations, explicitly disclosed single-source dependency in the U.S. and Europe, added cost as an adverse effect risk, and expanded consequences to include stock price impact.
  - *Why it matters:* An investor would notice the explicit disclosure of geographic concentration and single-source supplier risks in developed markets, plus the acknowledgment that these issues could affect stock price, representing more transparent risk articulation.
  - ✓ (old) "Substantially all of the Company's manufacturing is performed in whole or in part by outsourcing partners located primarily in China mainland, India, Japan, South Korea, Taiwan and Vietnam"
  - ✓ (new) "A significant majority of the Company's manufacturing is performed in whole or in part by outsourcing partners located primarily in China mainland, India, Japan, South Korea, Taiwan and Vietnam, in addition to sourcing from partners and facilities located in the U.S."
  - ✓ (new) "The Company relies on single-source partners in the U.S., Asia and Europe to supply and manufacture many components"
  - ✓ (new) "Such diminished control has from time to time had, and may in the future have, an adverse effect on the cost, quality or quantity"
  - ✓ (new) "can materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"

- **MODIFIED** The company added 'stock price' as an additional adverse impact of supply risks and removed language about supplier agreements and financial conditions.
  - *Why it matters:* Investors care about direct impacts on stock price, though the core supply risk disclosure remains substantially unchanged.
  - ✓ (old) "materially adversely affect the Company's business, results of operations and financial condition."
  - ✓ (new) "materially adversely affect the Company's business, results of operations, financial condition and stock price."
  - ✓ (old) "While the Company has entered into agreements for the supply of many components, there can be no assurance the Company will be able to extend or renew these agreements on similar terms, or at all."

- **MODIFIED** The company modified its supply chain risk disclosure to emphasize the inability to extend supplier agreements on similar terms, added risks of supplier failure and consolidation, and strengthened language about difficulty obtaining alternative sources.
  - *Why it matters:* An investor would notice the shift toward more explicit risks around supplier agreements and consolidation, though the core single-source dependency risk remains substantially similar.
  - ✓ (old) "The continued availability of these components at acceptable prices, or at all, can be affected for any number of reasons, including if suppliers decide to concentrate on the production of common components instead of components customized to meet the Company's requirements."
  - ✓ (new) "The Company may not be able to extend or renew agreements for the supply of components on similar terms, or at all, and may not be successful in obtaining sufficient quantities from its suppliers in a timely manner, or in identifying and obtaining sufficient quantities from an alternative source."
  - ✓ (new) "component suppliers may fail, be subject to consolidation within a particular industry, or decide to concentrate on the production of common components"

- **MODIFIED** The company softened language about third-party software discontinuation and added explicit statements about the adverse business impact.
  - *Why it matters:* While the core risk remains the same, the shift from "no assurance" to "may discontinue" and the added details about specific business impacts would alert an attentive investor to a changed framing of this risk.
  - ✓ (old) "There can be no assurance third-party developers will continue to develop and maintain software"
  - ✓ (new) "Third-party developers may discontinue the development and maintenance of software applications and services"
  - ✓ (new) "adversely impacting the Company's business, results of operations, financial condition and stock price"

- **MODIFIED** **[PARTLY VERIFIED]** The company expanded its talent risk disclosure to explicitly address cost pressures from intense competition, regulatory/immigration risks to workforce recruitment, and broadened potential adverse impacts to include strategy and stock price.
  - *Why it matters:* While the core talent retention risk existed before, the addition of regulatory barriers to hiring and explicit acknowledgment of cost inflation from compensation competition represents a meaningful shift in disclosed risk factors that investors monitoring talent-related headwinds should notice.
  - ✓ (new) "Periods of intense competition for talent in particular fields can lead to increased costs as the Company seeks to offer competitive compensation"
  - ✗ not found (new) "Laws and regulations, including immigration, labor and employment laws and export controls, can materially adversely affect the Company's ability to recruit and retain"
  - ✗ not found (new) "could materially adversely affect the Company's culture, operational flexibility, strategy and costs, all of which can materially adversely affect stock price"

- **MODIFIED** Expanded the risk disclosure to cover not just carrier financing offers but also the broader distribution model through resellers including competitors, and clarified that financing plans may be modified, not just discontinued.
  - *Why it matters:* An investor should notice the shift from narrow carrier financing risk to broader distribution channel risk including potential disadvantages from competing products sold by the same resellers.
  - ✓ (old) "Some carriers providing cellular network service for the Company's products offer financing, installment payment plans or subsidies"
  - ✓ (new) "The Company distributes its products and certain of its services through cellular network carriers and other resellers, many of which distribute products and services from competitors."
  - ✓ (new) "such plans may be discontinued or modified any time"

- **MODIFIED** The company added digital marketing assets as a reseller support program and expanded the risk disclosure to include consumer preference changes and explicit language about potential material adverse impact.
  - *Why it matters:* The addition of consumer preference changes as a specific risk factor and the stronger language about material adverse impact reflect a meaningful shift in how the company characterizes reseller-related risks, though the core business risk itself remains unchanged.
  - ✓ (new) "developing and making digital marketing assets available to resellers"
  - ✓ (new) "the purchasing preferences and behaviors of consumers may change"
  - ✓ (new) "could materially adversely impact the Company's business, results of operations, financial condition and stock price"

- **MODIFIED** The company expanded its data security risk disclosure to specify personal and sensitive health and financial information, and added potential stock price impact as a consequence of data breaches.
  - *Why it matters:* The addition of specific sensitive data types and stock price impact signals a more serious data risk exposure that investors would want to monitor, though the core risk was already disclosed.
  - ✓ (old) "personal information with respect to the Company's customers and employees"
  - ✓ (new) "personal and sensitive health and financial information with respect to the Company's customers and employees"
  - ✓ (old) "could materially adversely affect the Company's business, reputation, results of operations and financial condition"
  - ✓ (new) "could materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"

- **MODIFIED** The company expanded the scope of investment risks to include commercial relationships, added counterparty performance risk, and broadened potential adverse effects to include stock price impact.
  - *Why it matters:* The addition of commercial relationship risks and counterparty failure risk represents a meaningful expansion of disclosed investment risks that investors should understand.
  - ✓ (new) "new business strategies, commercial relationships and acquisitions"
  - ✓ (new) "a counterparty's failure to perform or deliver as anticipated"
  - ✓ (new) "materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"

- **MODIFIED** The company broadened the patent risk disclosure to cover standards-enabled products, expanded the definition of potential claimants to include data and intellectual property asset holders, and added a new risk about patent claims from emerging technologies like machine learning and artificial intelligence.
  - *Why it matters:* An investor would notice the company is now acknowledging broader categories of IP competitors and new technological risks, suggesting evolving competitive threats in AI and machine learning that could increase litigation exposure.
  - ✓ (old) "patent claims relating to its cellular-enabled products"
  - ✓ (new) "patent claims relating to its standards-enabled products"
  - ✓ (new) "data and other intellectual property asset–holding companies frequently assert their intellectual property rights"
  - ✓ (new) "new and emerging technologies, including machine learning and artificial intelligence, are further integrated into the Company's products and services"

- **MODIFIED** The company expanded its disclosure of litigation settlement risks to include impacts on revenue and stock price, and strengthened the language about potential adverse effects.
  - *Why it matters:* An investor would notice the addition of revenue reduction and stock price impact as potential consequences, though the fundamental risk category remains unchanged.
  - ✓ (old) "There can be no assurance such agreements can be obtained on acceptable terms or that litigation will not occur."
  - ✓ (new) "However, such agreements may not always be available on acceptable terms, and litigation may still arise."
  - ✓ (new) "Such agreements can also significantly reduce the Company's revenue and increase the Company's cost of sales and operating expenses, materially adversely affecting the Company's business, results of operations, financial condition and stock price."

- **MODIFIED** The company expanded its litigation risk disclosure to include potential stock price impacts and added specific risks regarding intellectual property enforcement and valuation.
  - *Why it matters:* An investor would care about direct threats to stock price and new IP-related business constraints, though these are elaborations of existing litigation risk rather than entirely new risks.
  - ✓ (old) "results of operations and financial condition for that reporting period could be materially adversely affected"
  - ✓ (new) "results of operations, financial condition and stock price for that reporting period could be materially adversely affected"
  - ✓ (new) "limit the Company's ability to enjoin others from using, or to derive value from, its intellectual property rights"
  - ✓ (old) "has from time to time required, and can in the future require, the Company to change its business practices and limit"
  - ✓ (new) "Adverse resolution of legal matters has from time to time required, and can in the future require, the Company to change its business practices"

- **MODIFIED** The Company added new regulatory risk categories including online safety, age verification, and national security to its list of complex global laws and regulations it faces.
  - *Why it matters:* These additions signal heightened regulatory scrutiny in emerging areas like online platform safety and age-appropriate content, plus geopolitical concerns, which could materially impact operations and compliance costs.
  - ✓ (new) "online safety; age verification"
  - ✓ (new) "national security"
  - ✓ (old) "privacy, data security and data localization; consumer protection"

- **MODIFIED** The company expanded the regulatory risk disclosure to include executive orders and enforcement priorities, removed the section about specialized applications and emerging technologies, and added stock price impact.
  - *Why it matters:* An investor would notice the addition of enforcement priorities as a regulatory risk factor and the explicit mention of potential stock price impact, though the core compliance risk remains substantively similar.
  - ✓ (new) "New and changing laws, regulations, executive orders, directives, and enforcement priorities can adversely affect the Company's business"
  - ✓ (old) "These risks and costs may increase as the Company's products and services are introduced into specialized applications, including health and financial services, or as the Company expands the use of technologies, such as machine learning and artificial intelligence features"
  - ✓ (new) "it could materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"

- **MODIFIED** The company removed language about having programs in place to satisfy regulatory requirements and added stock price as a potential adverse impact from import/export violations.
  - *Why it matters:* The addition of stock price impact is notable for investors, though the core regulatory risk remains unchanged; the softened language about compliance programs slightly increases the stated risk.
  - ✓ (old) "Although the Company has programs, policies and procedures in place that are designed to satisfy regulatory requirements, there can be no assurance that such policies and procedures will be effective"
  - ✓ (new) "The Company's programs, policies and procedures may not be effective in preventing a violation or a claim of a violation."
  - ✓ (new) "which could materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price."

- **MODIFIED** Narrowed the risk factor from environmental, social and governance considerations to just varied stakeholder expectations about social issues, removing specific reference to ESG and governance.
  - *Why it matters:* An investor tracking the company's ESG risk exposure would notice the de-emphasis of governance concerns and the removal of environmental considerations from this specific risk factor.
  - ✓ (old) "Expectations relating to environmental, social and governance considerations and related reporting obligations"
  - ✓ (new) "Varied stakeholder expectations about social and other issues"

- **MODIFIED** The company reframed its ESG risk disclosure to emphasize the challenge of managing diverse and conflicting stakeholder expectations rather than failure to achieve announced goals, and expanded language about potential adverse consequences.
  - *Why it matters:* An attentive investor would notice the shift in framing reduces specificity about ESG commitments while broadening the scope of potential harms from legal/regulatory to include consumer and stakeholder reactions.
  - ✓ (old) "environmental, social and governance considerations relating to businesses, including climate change and greenhouse gas emissions, human and civil rights, and diversity, equity and inclusion"
  - ✓ (new) "differing expectations about a wide range of social and other issues related to the Company's business"
  - ✓ (old) "The Company cannot guarantee that it will achieve its announced environmental, social and governance goals and initiatives."
  - ✓ (new) "the Company may not be able to fully achieve all of its goals and initiatives"

- **MODIFIED** Added explicit mention that antitrust investigations could impact stock price alongside business metrics and financial condition.
  - *Why it matters:* While the substantive antitrust risks remain unchanged, explicitly naming stock price as a potential consequence makes the risk more directly relevant to shareholders' investment returns.
  - ✓ (old) "have a materially adverse impact on the Company's business, results of operations and financial condition"
  - ✓ (new) "have a material adverse impact on the Company's business, results of operations, financial condition and stock price"
  - ✓ (old) "could materially adversely affect the Company's business, reputation, results of operations and financial condition"
  - ✓ (new) "could materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price"

- **MODIFIED** The company expanded the risk disclosure to explicitly include impacts on results of operations, financial condition, and stock price, and added lower profit margins as a potential consequence of compliance changes.
  - *Why it matters:* An investor would notice the company is now clearly stating that legal and regulatory risks could directly impact financial metrics and shareholder value, plus the addition of profit margin erosion as a specific harm.
  - ✓ (old) "There can be no assurance the Company's business will not be materially adversely affected"
  - ✓ (new) "The Company's business, results of operations, financial condition and stock price can be materially adversely affected"
  - ✓ (new) "lost sales, and lower profit margins"

- **MODIFIED** The company expanded its privacy risk disclosure to include perceived failures, explicitly enumerate penalty outcomes, and identify new risks from AI and emerging technologies.
  - *Why it matters:* The addition of 'perceived failure' as a trigger and explicit mention of AI-related data disclosure risks represent material changes to the scope and nature of privacy compliance risks that investors should monitor.
  - ✓ (old) "Any failure by the Company to comply with these public statements or with federal, state or international privacy or data protection laws and regulations could result in inquiries or proceedings against the Company"
  - ✓ (new) "Any failure or perceived failure by the Company to comply with these public statements or with federal, state or international privacy or data protection laws and regulations could result in inquiries, proceedings and penalties"
  - ✓ (new) "The risks of inadvertent disclosure of personal data can increase with the introduction of new and complex technologies, such as artificial intelligence features"

- **MODIFIED** **[PARTLY VERIFIED]** The company added obligations for handling data of minors and payment card data, replaced 'security and transfer of personal information' with 'protection and transfer of personal data', and removed specific language about healthcare and financial institution agreements.
  - *Why it matters:* The addition of minor data protection and payment card data obligations represents new regulatory scope that investors should track, though the removal of healthcare/financial institution agreement language suggests some risk narrowing.
  - ✓ (new) "specific obligations relating to the collection and processing of data associated with minors"
  - ✗ not found (new) "health, biometric, financial and payment card data are subject to additional privacy, security and breach notification requirements"
  - ✓ (old) "if health data or financial data is handled in a manner not permitted by law or under the Company's agreements with healthcare or financial institutions"

- **MODIFIED** The company added that investment value fluctuations could have a material adverse impact on its stock price, in addition to results of operations and financial condition.
  - *Why it matters:* An investor would notice this clarification that investment losses could directly affect stock price, adding specificity to the potential impact beyond operational metrics.
  - ✓ (old) "could have a material adverse impact on the Company's results of operations and financial condition."
  - ✓ (new) "could have a material adverse impact on the Company's results of operations, financial condition and stock price."

- **MODIFIED** The company removed language about wholesalers as distribution channels, softened language about mitigating international credit risks, removed mention of prepayments being concentrated in Asia, and strengthened the consequence statement regarding credit risk from a disclaimer to a potential material adverse effect.
  - *Why it matters:* The changes materially heighten the stated consequences of credit risk failures from potential losses to explicit material adverse effects on operations, financial condition and stock price, which investors should notice.
  - ✓ (old) "through third-party cellular network carriers, wholesalers, retailers and resellers"
  - ✓ (new) "through third-party cellular network carriers and other resellers"
  - ✓ (old) "and its ability to mitigate such risks may be limited"
  - ✓ (new) "If the Company is unable to monitor and limit exposure to credit risk on its trade and vendor non-trade receivables, as well as long-term prepayments, the Company's results of operations, financial condition and stock price could be materially adversely affected"
  - ✓ (old) "vendor non-trade receivables and prepayments related to long-term supply agreements were concentrated among a few individual vendors"

- **PARTLY REMOVED** The disclosure of supply and manufacturing disruption risks from natural disasters, IT failures, commercial disputes, and environmental/labor/political issues was removed; only general control and quality risks remain.
  - *Why it matters:* Investors lose visibility into specific operational disruption scenarios beyond the generic control-loss risk, though candidate 2 addresses geopolitical disruptions separately under tariffs and trade disputes.
  - ✓ (old) "Any failure of these partners to perform can have a negative impact on the Company's cost or supply"
  - ✓ (old) "manufacturing or logistics in these locations or transit to final destinations can be disrupted for a variety of reasons, including natural and man-made disasters, information technology system failures, commercial disputes, economic, business, labor, environmental, public health or political issues, trade and other international disputes, geopolitical tensions, or conflict"
  - ✓ (new) "While these arrangements can lower operating costs, they also reduce the Company's direct control over production and distribution. Such diminished control has from time to time had, and may in the future have, an adverse effect on the cost, quality or quantity of products manufactured"

- **PARTLY REMOVED** **[PARTLY VERIFIED]** **[VERDICT UNSUPPORTED: no quote from the new filing found]** The risk of recoverability loss on manufacturing process equipment held at outsourcing partners was removed; only the prepayment risk survives.
  - *Why it matters:* Investors lose visibility into a specific asset category (manufacturing equipment at outsourcers) and the disruption risks unique to that arrangement, though prepayment risk remains disclosed.
  - ✓ (old) "The Company has invested in manufacturing process equipment, much of which is held at certain of its outsourcing partners"
  - ✗ not found (new) "The Company has made prepayments associated with long-term supply agreements to secure supply of inventory components"

- **REMOVED** The disclosure about third-party digital content providers requiring DRM and security solutions, and risks of developing or licensing such solutions at reasonable cost and timely manner, has been removed.
  - *Why it matters:* This risk addresses specific technological and financial barriers to meeting third-party requirements for content protection, which could affect the Company's ability to offer digital content services competitively.
  - ✓ (old) "Some third-party digital content providers require the Company to provide digital rights management and other security solutions."
  - ✓ (new) "The Company contracts with numerous third parties to offer their digital content to customers. This includes the right to sell, or offer subscriptions to, third-party content"

- **PARTLY REMOVED** The disclosure of payment card processing cost increases and loss of payment processing ability following non-compliance with PCI standards was removed; only investigatory expenses and fines remain.
  - *Why it matters:* Loss of payment card processing capability or significant cost increases would directly harm revenue and operations, making their omission from disclosure material to investors evaluating business continuity risks.
  - ✓ (old) "if cardholder information is potentially compromised, the Company can be liable for associated investigatory expenses and can also incur significant fees or fines"
  - ✓ (new) "can be liable for associated investigatory expenses, and can incur significant fees or fines"

- **PARTLY REMOVED** The disclosure about seasonal holiday demand in Q1, unexpected developments like IT system failures, and logistics partner failures was removed; only the single-product concentration and new product introduction risks were retained.
  - *Why it matters:* Loss of seasonal demand disclosure and operational risk factors reduces visibility into demand volatility sources and business continuity vulnerabilities that investors should consider.
  - ✓ (old) "new product and service introductions can significantly impact net sales, cost of sales and operating expenses"
  - ✓ (new) "introduction of new products or services, including new products or services with lower profit margins"
  - ✓ (old) "the Company generates a significant portion of its net sales from a single product and a decline in demand for that product could significantly impact quarterly net sales"

## Low materiality (21)

- **ADDED** Added introductory language to the Risk Factors section explaining that risks listed could have material adverse effects and are not exhaustive.
  - *Why it matters:* This is standard boilerplate disclaimer language that does not identify any new risks or change the company's actual risk exposure.
  - ✓ (new) "The following summarizes factors that could have a material adverse effect on the Company's business, reputation, results of operations, financial condition and stock price."

- **MODIFIED** Added 'stock price' to the list of things that adverse economic conditions can materially adversely affect.
  - *Why it matters:* This is a minor wording addition that clarifies an obvious implication without substantively changing the risk exposure being described.
  - ✓ (old) "adverse economic conditions can materially adversely affect the Company's business, results of operations and financial condition."
  - ✓ (new) "adverse economic conditions can materially adversely affect the Company's business, results of operations, financial condition and stock price."

- **MODIFIED** Removed the phrase 'In addition to an adverse impact on demand for the Company's products and services' from the beginning of the risk factor paragraph about economic conditions.
  - *Why it matters:* This is a clarification of emphasis rather than a material change to the actual risks disclosed, as the core economic conditions risk and its potential consequences remain unchanged.
  - ✓ (old) "In addition to an adverse impact on demand for the Company's products and services, uncertainty about"
  - ✓ (new) "Uncertainty about, or a decline in, global or regional economic conditions can also have a significant impact"

- **MODIFIED** The company added explicit mention of retail stores as locations subject to operational disruption risks and removed the example about geopolitical tensions and supply chain concentration.
  - *Why it matters:* The addition of retail stores clarifies existing risk exposure rather than introducing new risk categories, while the removal of a specific example does not materially change the overall risk assessment.
  - ✓ (new) "Many of the Company's operations, retail stores and facilities, as well as critical business operations"
  - ✓ (old) "For example, global supply chains can be highly concentrated and geopolitical tensions or conflict could result in significant disruptions."

- **MODIFIED** The company added a concluding sentence emphasizing that business interruptions can materially adversely affect its business, results of operations, financial condition and stock price, and changed 'experience' to 'incur' regarding expenditures.
  - *Why it matters:* The modification emphasizes existing risks with stronger language but does not introduce new risk factors or materially change the scope of the business interruption risk already disclosed.
  - ✓ (old) "experience significant expenditures to resume operations"
  - ✓ (new) "incur significant expenditures to resume operations"
  - ✓ (new) "Any of the foregoing can materially adversely affect the Company's business, results of operations, financial condition and stock price."

- **MODIFIED** Restructured competitive market risk description to separate core competitive pressures from market characteristics, and removed reference to 'product price and performance characteristics' improvements.
  - *Why it matters:* The change reorganizes existing risk factors without substantively altering the scope or nature of competitive pressures faced by the company.
  - ✓ (old) "continual improvement in product price and performance characteristics, rapid adoption of technological advancements by competitors"
  - ✓ (new) "continual improvement in product performance, and price sensitivity on the part of consumers and businesses. These markets are further defined by frequent introduction of new products and services"

- **MODIFIED** Added 'stock price' to the list of things that supply risks can materially adversely affect.
  - *Why it matters:* This is a minor wording change that adds an abstract consequence already implicit in discussing material adverse effects, without substantively changing the risk description.
  - ✓ (old) "the Company remains subject to significant risks of supply shortages and price increases that can materially adversely affect its business, results of operations and financial condition"
  - ✓ (new) "the Company remains subject to significant risks of supply shortages and price increases that can materially adversely affect its business, results of operations, financial condition and stock price"

- **MODIFIED** The company simplified its inventory write-down policy by removing language about obsolescence and excess demand accruals, and softened assurances about asset recoverability.
  - *Why it matters:* The changes clarify accounting policies without indicating new risks or meaningful changes to how the company actually manages inventory and asset impairment.
  - ✓ (old) "The Company records a write-down for product and component inventories that have become obsolete or exceed anticipated demand, or for which cost exceeds net realizable value. The Company also accrues necessary cancellation fee reserves for orders of excess products and components."
  - ✓ (new) "The Company records a write-down for product and component inventories if cost exceeds net realizable value."
  - ✓ (old) "there can be no assurance the Company will not incur write-downs, fees, impairments and other charges"
  - ✓ (new) "the Company may incur write-downs, impairments and other charges"

- **MODIFIED** Added disclosure that the Company accrues cancellation fee reserves for excess product and component orders.
  - *Why it matters:* This clarifies existing inventory risk management practice without materially changing the scope or severity of the forecasting risk already disclosed.
  - ✓ (new) "The Company accrues necessary cancellation fee reserves for orders of excess products and components."
  - ✓ (old) "there is a risk the Company will forecast incorrectly and order or produce excess or insufficient amounts"
  - ✓ (new) "not fully utilize purchase commitments. The Company accrues necessary cancellation fee"

- **MODIFIED** Simplified language about third-party software availability by removing reference to 'availability' and 'developers' perception and analysis' in favor of more direct phrasing about 'developer support' and 'perceived benefits.'
  - *Why it matters:* The change is primarily stylistic, clarifying existing risk language without materially altering the scope or substance of the third-party developer dependency risk.
  - ✓ (old) "The Company believes the availability of third-party software applications and services for its products depends in part on the developers' perception and analysis of the relative benefits"
  - ✓ (new) "The Company believes that third-party developer support depends on the perceived benefits of creating software and services for the Company's products"

- **MODIFIED** Apple expanded the developer incentive risk to explicitly include the wearables market alongside smartphones, personal computers, and tablets.
  - *Why it matters:* The change clarifies existing risk exposure in a growing product category without introducing fundamentally new concerns about developer incentives.
  - ✓ (old) "The Company's minority market share in the global smartphone, personal computer and tablet markets"
  - ✓ (new) "The Company's minority market share in the global smartphone, personal computer, tablet and wearables markets"

- **MODIFIED** Added 'stock price' to the list of potential adverse effects from failure to maintain company culture.
  - *Why it matters:* This is a minor clarification to existing risk language that adds stock price to the enumerated consequences, without substantively expanding the scope of the underlying risk.
  - ✓ (old) "could otherwise materially adversely affect the Company's business, reputation, results of operations and financial condition."
  - ✓ (new) "could otherwise materially adversely affect the Company's business, reputation, results of operations, financial condition and stock price."

- **MODIFIED** The company softened language describing cybersecurity attack consequences by removing 'materially' from damage claims and changing 'impact' to 'affect' for stock price effects.
  - *Why it matters:* The change moderates the severity of stated consequences without eliminating any risks or substantively narrowing their scope.
  - ✓ (old) "materially damage commercial relationships, and expose the Company to litigation"
  - ✓ (new) "damage commercial relationships, and expose the Company to litigation"
  - ✓ (old) "impact the Company's stock price, materially damage commercial relationships"
  - ✓ (new) "affect its stock price, damage commercial relationships"

- **MODIFIED** The company removed the opening sentence describing its implemented systems and processes for securing IT systems and preventing unauthorized access through encryption and authentication technologies.
  - *Why it matters:* The removal is primarily stylistic; the substantive risks discussed remain unchanged and the company still acknowledges its security measures may be insufficient.
  - ✓ (old) "The Company has implemented systems and processes intended to secure its information technology systems and prevent unauthorized access to or loss of sensitive data, and mitigate the impact of unauthorized access, including through the use of encryption and authentication technologies."
  - ✓ (new) "As with all companies, the security the Company has implemented may not be sufficient for all eventualities"

- **MODIFIED** Added 'commercial relationships' as a potential source of disruption and risk alongside business strategies and acquisitions.
  - *Why it matters:* The change expands the risk category slightly but remains within standard risk disclosure language and does not introduce a materially new risk exposure.
  - ✓ (old) "Investment in new business strategies and acquisitions could disrupt"
  - ✓ (new) "Investment in new business strategies, commercial relationships and acquisitions could disrupt"

- **MODIFIED** The company changed language about indemnification provisions from stating they are sometimes included in agreements to stating the company enters into agreements that include them.
  - *Why it matters:* This is a minor rewording that does not substantively change the risk exposure described or add new information about indemnification obligations.
  - ✓ (old) "agreements entered into by the Company sometimes include indemnification provisions"
  - ✓ (new) "the Company enters into agreements that include indemnification provisions"

- **MODIFIED** Added specific detail about what data protection obligations cover: collection, use, protection and transfer of personal data.
  - *Why it matters:* The change clarifies the scope of data protection obligations but does not introduce new risks or materially expand the company's legal exposure.
  - ✓ (old) "The Company's business is subject to a variety of U.S. and international laws, rules, policies and other obligations regarding data protection."
  - ✓ (new) "The Company's business is subject to a variety of U.S. and international laws, rules, policies and other obligations regarding the collection, use, protection and transfer of personal data."

- **MODIFIED** The Company changed 'security' to 'protection' and 'personal information' to 'personal data' in its data privacy risk disclosure.
  - *Why it matters:* These are terminology updates that do not substantively change the scope or nature of the data privacy risks facing the Company.
  - ✓ (old) "collection, use, retention, security and transfer of various types of personal information"
  - ✓ (new) "collection, use, retention, protection and transfer of various types of personal data"

- **MODIFIED** The company strengthened its tax examination risk disclosure by replacing the generic assurance qualifier with a more emphatic statement about uncertainty and added potential stock price impact to the list of adverse effects.
  - *Why it matters:* The changes are primarily stylistic refinements that do not introduce new substantive tax risks or materially broaden the scope of existing tax liabilities.
  - ✓ (old) "There can be no assurance as to the outcome of these examinations."
  - ✓ (new) "The outcome of such examinations is inherently uncertain."
  - ✓ (new) "results of operations, financial condition and stock price could be materially adversely affected."

- **NOT REMOVED (moved or reworded)** The cautionary statement about past performance not being indicative of future results was reworded into a broader disclaimer about the incompleteness of risk disclosures.
  - *Why it matters:* Both versions convey similar forward-looking statement cautions; the reworded version maintains the essential message that investors should not rely on historical indicators or assume complete risk disclosure.
  - ✓ (old) "past financial performance should not be considered to be a reliable indicator of future performance"
  - ✓ (new) "The risks and uncertainties described below are not exhaustive and should not be considered a complete statement"

- **NOT REMOVED (moved or reworded)** The risk about continually improving products to maintain competitive advantages was reworded and moved into Candidate 1's discussion of product and service introductions and market competition.
  - *Why it matters:* The substance of needing continuous product improvement to compete effectively survives, though the new disclosure focuses more on execution risks and less on maintaining functional and design advantages specifically.
  - ✓ (old) "The Company's business, results of operations and financial condition depend substantially on the Company's ability to continually improve its products and services"
  - ✓ (new) "the Company must continually introduce new products, services and technologies, enhance existing products and services"
