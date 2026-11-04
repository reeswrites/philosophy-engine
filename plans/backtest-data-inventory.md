# Backtest data inventory (2026-11-03, revised for ordering tests)

Tags: [F] = confirmed on a page I opened; [R] = recalled, verify before building. Failure modes: DT dark twin, DI displacement, BL backlash, RB rebundling.
Two blows to land: (A) do rules trail material/tech/price change? (B) did standing precede any material floor and the gain persist?

## Cases (ordering = which came first)

**1. Whaling.** https://en.wikipedia.org/wiki/Whaling_in_the_United_States [F]: US fleet peak 736 vessels 1846; tonnage 199k (1858), 167k (1860); 39 ships by 1876; coal oil/turpentine named, kerosene not.
- Ordering: tech/price first. Kerosene/petroleum 1850s-60s [R], collapse by 1870s [F]. Margarine hydrogenation and factory ships ~1910s-25 [R]; Geneva convention 1931, IWC 1946, moratorium decided 1982 [R]. Rules trail by 25-120 years. Separation: excellent. Blow A: strongest.
- Data: IWC catch database (iwc.int fetch failed; [R] public); Census/Bockstoce tables [F]. Failure: DT/DI (demand rebundled onto Antarctic stocks, then palm oil). Staggered: no. Difficulty: Medium.

**2. Married Women's Property Acts.** https://ideas.repec.org/h/eme/rehizz/s0363-3268(2013)0000029007.html [F]: corrected passage dates for 48 states, mostly 1850-1920; Earnings Acts separate.
- Ordering: standing first. Mississippi 1839, New York 1848/1860 [R]; married women's labour-force participation was single digits until after 1900 [R]. Blows A and B both testable, since state timing varies against LFP and industrialization. Persistence: IPUMS 1850-1920 outcomes [R].
- Data: dates in paper tables (paywalled); IPUMS full-count census public. Staggered: excellent. Failure: BL/RB (separate-estate trusts, husband-managed) need hand coding. Difficulty: Medium.

**3. US unilateral divorce.** https://www.nber.org/papers/w10175 [F]: staggered state adoption from 1969; female suicide down ~20%, domestic violence down, women's partner homicide suggestively down [F].
- Ordering: mixed. Female LFP had risen since the 1950s; the pill (1960) reached young unmarried women state by state through ~1970-75 [R]. Exit rights arrived before wage parity, and gains persisted [F]: Blow B. Blow A is testable via state pill-access and LFP timing.
- Data: NCHS mortality, FBI SHR, state laws; public [R]. Failure: none clear; negative control. Difficulty: Low.

**4. Dutch livestock buyouts.** https://www.dutchnews.nl/2024/12/some-1700-livestock-farmers-signed-up-for-buyout-schemes [F]: ~1,700 applicants (920 + 665 + 104). https://www.dutchnews.nl/2025/07/dutch-pig-herd-shrinks-below-10-million-as-buyout-schemes-bite [F]: pigs 9.96M (-5.1%); dairy herd 3.65M; average herd 89 to 114 cows; farms >5,000 pigs stable.
- Ordering: pig price slump 2021-23 [R] and 2019 nitrogen ruling [R] precede 2022-23 schemes. Testable if prices lead exits. Consolidation hints at DT/RB (not causal).
- Data: CBS StatLine; EU pig prices [R]. Staggered: scheme rounds, Natura 2000 proximity. Difficulty: Medium; short series.

**5. Cage-free pledges 2015-25.** https://egg-dashboard.innovateanimalag.org/egg-dashboard.html [F]: cage-free flock share chart; no download named.
- Ordering: pledges 2015-16 and Prop 12 (2018) [R] vs avian flu price spikes 2015, 2022-25 [R]. Separable monthly. Data: USDA AMS reports, public [R]. Failure: BL (preemption bills), RB (relabeling). Difficulty: Low-Medium.

**6. Quebec QPIP 2006.** https://equitablegrowth.org/for-fathers-day-evidence-from-three-countries-on-the-importance-of-paid-parental-leave-for-new-dads/ [F]; https://ideas.repec.org/a/ucp/jlabec/doi10.1086-703115.html [F]: 5 non-transferable weeks, take-up +250%; fathers' housework up, mothers shifted to childcare (partial DI).
- Ordering: policy led take-up; no tech shift identified. Data: Canadian GSS time diaries [R]; DiD vs rest of Canada. Difficulty: Medium.

**7. Norway father quota 1993.** Dahl, Løken, Mogstad papers [R]; https://pubmed.ncbi.nlm.nih.gov/24135861/ (not opened). Ordering: followed 1977 leave law and high female employment [R] (rules trailed). Data: registers, not public; tables only. Difficulty: High.

**8. Footbinding.** https://darwinianconservatism.blogspot.com/2009/11/gerry-mackie-on-female-circumcision.html?m=0 [F, secondary]: pledge groups, intermarrying, abandoned in ~two decades.
- Ordering: machine-spun yarn undercut girls' handicraft value from the 1880s [R]; pledge societies 1890s [F]; 1902 edict, 1912 ban [R]. Rules trailed. Data: Ding Xian survey in paper tables [R]. Difficulty: High.

**9. Kibbutz children's houses.** https://www.jta.org/archive/last-kibbutz-childrens-house-closes-2 [F]: Baram, last holdout, 80 children moved home June 1997 after a decision over a year earlier.
- Ordering: affluence and parental demand preceded kibbutz-level votes [R]; staggered but non-public data (Haifa Kibbutz Research Institute, not opened). RB/DI (care returned to mothers). Difficulty: High.

## Calibration data
- ATUS https://www.bls.gov/tus/ [F]: free microdata, 2003-2025, Leave and Job Flexibilities Module 2024-25 [F].
- MTUS https://www.timeuse.org/mtus [F]: 100+ surveys, 30 countries, free account; MTUS-X extract builder.
- HETUS https://ec.europa.eu/eurostat/web/time-use-surveys [F]: decadal waves; microdata by application [R].
- Mental load: Invisible Family Load Scale (Wayne et al. 2023) used by Italy's FORTIES survey, not public until after 2026 [F]. No open dataset found; proxy with ATUS secondary childcare.

## Ranked first backtests (by power to land blows A and B)
1. **Whaling.** Largest, cleanest rule-trails-technology gap; decades of separation.
2. **Married Women's Property Acts.** Standing before any labour floor, 48-state staggering, and a persistence test; lands both blows.
3. **US unilateral divorce.** Exit rights before wage parity with persistent gains (B); pill and LFP timing give a partial A.
4. **Dutch buyouts vs pig prices.** Direct price-versus-rule ordering and a DT test; short series, so it ranks last. Cage-free pledges are the runner-up.
