# Con Ed Residential Rate Comparison — Project Spec

**Contents.** *Purpose*: what this is and its scope. *Status and roadmap*: what is done and next. *The four plans*: what is compared. *Inputs 1–4*: usage data, MSC prices, tariff rates, Con Ed statements. *Calculation rules*: periods, proration, peak periods, demand, supply. *Output of the engine* and *Suggested structure*: the result format and the code layout. *Refreshing the data*: what to do when Con Ed publishes new rates. *Test cases*, *Open items*, *Background notes*, *Glossary*. References like "Inputs 2" mean the numbered subsections under *Inputs*.

## Purpose

Take a Con Edison customer's interval usage data and estimate what that usage would have cost under four residential billing options, so that a customer can choose a plan from accurate numbers. The same usage can be re-priced after changing it ("what if I moved this load to overnight?"), because the alternative plans exist to reward off-peak use; the tool's job is to show what shifting would be worth to the customer, which also helps the grid.

**Inputs that change over time are data, not code.** There are four, each independently updatable: the customer's usage export, Con Ed's MSC price file, the tariff rates (`data/tariff.toml`) and Con Ed's published statements (`data/statements.toml`: per-kWh adders, System Benefits Charge, gross receipts tax). A rate or statement change means adding a dated entry. The *rules* (peak-period hours, holidays, which months are summer, which plan uses which periods, proration) are in code and change only when the tariff's rules change.

**Scope.** NYC (NYISO Zone J) residential service under SC 1 and Rider Z, low tension, monthly bills, priced from 15-minute interval data. Not modeled: other zones, bi-monthly billing, and the enrollment conditions that matter when choosing a plan (Rate III's one-year commitment and 1.5-year bar on returning, Rate IV's 1.5-year bar, and no Rider Z bill protection for voluntary enrollees). Any recommendation should mention them. This is a personal decision aid, not financial or legal advice; check important decisions against Con Edison's own figures.

**Privacy.** A customer's usage data, bills and account details are private and are never committed to the repository. They are gitignored, and public examples and tests use invented data only.

**Deliverables, in order:** the Python package with a command-line interface and a worked-example notebook; a browser-only app later, running the same engine so that usage data never leaves the user's machine.

**Output.** The pricing engine returns an itemized breakdown (per plan, per billing period, per charge component: quantity, unit, rate, amount and which side of the bill it belongs to) plus diagnostics, so that any report can be built on top of it. The command line prints a monthly table of plan totals and can write the full breakdown as JSON. The final report format and the functions that display `price_period`'s result are **deliberately not specified yet** and are being designed.

**Periods.** The engine prices either calendar months (the default) or actual bill periods supplied by the user. See "Billing periods" for how bill dates map to usage days.

**Sources.** The tariff and the statements both come from the NY Department of Public Service site, https://dps.ny.gov/electric-tariffs → Consolidated Edison PSC No. 10. The *tariff* (`electric-tariff.pdf`, a 31 MB local copy that is gitignored and not in the repository) gives rates and rules. The *statements* (the site's "Statements" link; the "effective" list holds current ones and the "cancelled" list superseded ones) give the adders, SBC and tax percentages. Superseded tariff leaves (the "cancelled" Leaves list) give earlier rates. "Leaf" is the tariff's own page number and is stable across revisions; "PDF p." is the page in the local copy (the 2026-02 revision) and moves when the tariff is reissued, so prefer Leaf numbers. Useful leaves: Rider Z delivery rates 327.3; General Rule (GR) 25, supply charges, from 328; GR 26, additional delivery charges, from 337 (billing and payment processing 353, System Benefits Charge 355); SC 1 Rates I–IV 388–389.3. Current rates are those effective 2026-02-01; earlier rates are in `data/tariff.toml` back to 2025-01-01 (see Inputs 3).

## Status and roadmap

**Phase 1: package, command line, notebook.**
- Done: pricing engine for all four plans; loaders for usage, MSC, tariff and statements; tariffs and statements back to 2025 (statements from Oct 2025); reproduction of six real SC 1 Rate I bills to within $0.06; unit tests.
- Next: scenario functions (re-price usage after shifting load to other hours); display functions for the itemized result (being designed); a worked-example notebook; a synthetic sample usage file so the public repository can run end to end; a README.
- Open questions that affect numbers are in Open items.

**Phase 2: browser-only app** running the same engine, so usage data never leaves the user's machine. The technology (for example Python in the browser, or a port of the engine) is not decided.

## The four plans

| Plan | Key (code, data files, output) | Consumer name (from a Con Ed email) | Delivery basis | Supply (MSC) basis | Enrollment terms (not modeled) |
|---|---|---|---|---|---|
| SC 1 Rate I (default; Con Ed rate code EL1) | `sc1_rate1` | Standard Residential Rate | per kWh, summer tier | flat per kWh | none; the default |
| SC 1 Rate III (voluntary time-of-day) | `sc1_rate3` | Time-of-Use Rate | per kWh, on/off-peak | per kWh, super-peak / on / off | must stay one full-service year after electing; barred from returning for 1.5 years after leaving (Leaf 389.1) |
| SC 1 Rate IV (optional demand-based) | `sc1_rate4` | Steady Use Rate (SUR) | per kW demand, on/off-peak | per kWh, on/off-peak | opt-in; barred from returning for 1.5 years after leaving (Leaf 389.2) |
| Rider Z Rate I (Innovative Pricing Pilot) | `riderz_rate1` | Smart Energy Plan (SEP) | per kW demand, on/off-peak | flat per kWh | a pilot (Leaves 327–327.6); voluntary enrollees are assigned Rate I and get no bill protection |

**EL1 and EL7.** Con Ed's standard residential rate is EL1 ("Residential and Religious, Rates I and II"; MSC lookup code `001`). Some accounts carry the legacy label EL7 ("Residential and Religious – Heating", code `007`), which is printed on their bills as "EL7 Residential or Religious Heating". EL7 accounts are priced exactly like EL1: in the MSC file the `007` rows have been identical to the `001` rows, in all 18 price columns, for every billing cycle from the one starting 2013-03-30 on (they differed in earlier cycles, which this project does not use); the current tariff has no separate heating rate (SC 1 Rate II is a closed time-of-day rate); and bills labelled EL7 reproduce to the cent under Rate I.

Rider Z Rate I is the relevant Rider Z rate because voluntary (non-recruited) enrollees are assigned to Rate I (Leaf 327.1). Voluntary enrollees do not get the Rider Z bill-protection guarantee. Rider Z is a pilot and may be replaced by a permanent plan, in which case this row will be updated; the other Rider Z rates are not priced.

Rider Z Rate I's flat MSC follows the tariff: GR 25.1(b) (Leaf 330.1) treats Rider Z as an energy-only class priced at energy plus capacity as a single per-kWh rate, and gives time-of-day energy only to "Rate IV of Rider Z" and "Rate IV of SC 1". Which capacity price Rider Z Rate I takes remains an assumption (Rate I's; see the MSC mapping under Inputs).

"Summer" means June, July, August and September for every plan.

## Inputs (each independently updatable)

### 1. Usage data

This is the interval CSV export from the customer's Con Ed account ("Download My Data"), read as downloaded by `load_usage` (`conedrates/loaders.py`). Only this format, with 15-minute intervals, has been checked against real data.

**Format (verified).**
- Columns: `TYPE, DATE, START TIME, END TIME, USAGE (kWh), NOTES`. The file may start with a few account lines (customer name, address, account number) before the header. The loader skips everything before the first line beginning `TYPE,DATE`, tolerates a byte-order mark and Windows line endings, and raises a `ValueError` that does not echo the file's contents if there is no such line. The skipped lines are never printed or stored.
- Each row is one interval, in kWh, in local wall-clock time with no time zone. `START TIME` is the interval's start and `END TIME` is its last minute (00:14 for a 00:00 start), so interval length = END − START + 1 minute. The engine detects the interval length from the data.
- DST: on the spring-forward day the missing hour is simply absent (92 intervals). On the fall-back day the repeated hour is not exported (96 intervals, so about four intervals of usage are lost); rows that share a timestamp, if any, are summed.
- Missing intervals are not marked in the file; a gap is a row that is absent. The engine compares the data with the complete time grid, reports the count of missing intervals for each period, and does not fill them in. Demand windows skip any window containing a missing interval. Expect gaps (the sample has several four-hour ones) and partial first and last months.
- `NOTES` was empty in every row of the sample, so what an estimated reading looks like there is unknown. Non-empty notes are counted as "estimated" on that assumption.

**Not verified.**
- **Hourly intervals.** The loader and the engine handle other interval lengths: the 60-minute demand becomes the kWh of the hourly reading, and the output carries a warning. This path has not been tested at all yet: no real hourly export was available, and a synthetic hourly test is an open item.
- **Green Button XML.** Con Ed also offers the standard XML export, which the loader does not read. It is to be supported eventually *if it has advantages over the CSV*. Things to check in a real XML file: explicit units and scale factors, UTC or otherwise unambiguous timestamps (which would remove the DST ambiguity above), reading-quality flags that mark estimated or missing intervals (which the CSV lacks), and any information the CSV omits. Until that is assessed, the CSV is the supported input.

**Privacy.** Real exports are gitignored and never committed. Tests use invented fixtures (`tests/usage_trimmed.csv` and `tests/usage_with_junk.csv`, plus files written on the fly).

### 2. Market Supply Charge (MSC) data

The input is Con Ed's `LDS_APPND.CSV` ("MSC Lookup File"), downloadable from coned.com → Market Supply Charge Calculator page and read by `load_msc`. Updating the data should require nothing more than downloading a new copy. The file holds only the MSC itself: the Adjustment Factors – MSC and the Clean Energy Standard Supply Surcharge, which a real bill adds to the supply price, come from statements (see Inputs 4).

**Codes.** Con Ed's reference document "Electric Rate Description, and its Supply Charge and Type" (April 2021) lists the code used in the file for each rate. The residential rows (the commercial and multi-dwelling codes are ignored):

| Rate description | Code in the file |
|---|---|
| EL1 – Residential and Religious – Rates I and II | `001` (older rows: `1`) |
| EL1 – Residential and Religious – Rate III | `001VTO` |
| EL1 – Residential and Religious – Rates IV – Rider Z | `001IPP` |
| EL7 – Residential and Religious – Heating – Rates I and II | `007` (older rows: `7`) |

EL7 accounts are priced like EL1 (see "The four plans"). The loader reads codes as text and treats `001` and `1` as the same code; spreadsheet programs and pandas' default readers turn `001` into the number 1.

**Layout of the raw file.** Two header rows; the second names the zone and tension (for example `LT-ZONE J`). Columns 0–3 are the code, FROM, TO and TRIP. Then come 18 price columns: for each of zones H, I and J, ALL HOURS, ON PEAK and OFF PEAK, each for low tension (LT) and high tension (HT). Some data rows carry an extra empty trailing field. The loader selects **Zone J, low tension** by default (`--zone`, `--tension` change them). It also accepts a pre-filtered 7-column version of the file (`SC AND, FROM DT, TO DT, TRIP, ALL HOURS, ON PEAK, OFF PEAK`).

- Each row is one **billing cycle** (`TRIP` = meter-reading cycle 1–22), not a calendar month. FROM and TO are YYYYMMDD with TO inclusive; prices are in $/kWh.
- Coverage in the sample: `001` and `007` rows from 2010, `001VTO` from 2015 and `001IPP` from 2018, through about a month beyond the download date.
- There are exact duplicate rows (the same cycle under two TRIP numbers); the loader drops them.
- Some rows span 93–126 days (irregular bills); the loader ignores rows longer than 35 days.

Column meaning depends on the code:

| Code | ALL HOURS | ON PEAK | OFF PEAK |
|---|---|---|---|
| `001` (SC 1 Rates I & II; older rows `1`) | **Rate I price** | Rate II on-peak (unused) | Rate II off-peak (unused) |
| `001VTO` (SC 1 Rate III) | **Rate III super-peak price**; 0 if the period contains no June–Sept day | **Rate III on-peak** | **Rate III off-peak** |
| `001IPP` (Rider Z Rate IV) | Rate I price minus Rate I capacity (unused; see below) | **Rider Z Rate IV on-peak** | **Rider Z Rate IV off-peak** |

**Mapping MSC prices to plans:**

- **SC 1 Rate I:** `001` / ALL HOURS.
- **SC 1 Rate III:** `001VTO` super-peak, on-peak and off-peak. The super-peak price *replaces* the on-peak price in the super-peak hours (it does not add to it): the tariff assesses Rate III's capacity charge only in those hours (GR 25.1(b), Leaf 330.1), so the on-peak price excludes capacity. The size is consistent with the capacity statement: for July 2026 the file's super-peak price is 89.78¢, of which the statement's Rate III capacity charge is 79.96¢, leaving 9.82¢ of energy (against 8.40¢ for ordinary on-peak). *Supported by the tariff text; the energy/capacity split cannot be checked independently.*
- **SC 1 Rate IV:** `001IPP` ON/OFF PEAK. *Assumption:* the file has no separate SC 1 Rate IV entry. It is supported by Con Ed's code table, which lists "Rates IV – Rider Z" together under `001IPP`, and by the capacity statement, which gives SC 1 Rate IV and Rider Z Rate IV the same on-peak capacity charge (25.48¢ in July 2026).
- **Rider Z Rate I:** `001` / ALL HOURS, i.e. the SC 1 Rate I price. *Assumption:* the file and the Con Ed calculator give no Rider Z Rate I price. The tariff supports a flat price (GR 25.1(b); see "The four plans"), and the data supports Rate I's: `001`/ALL HOURS − `001IPP`/ALL HOURS equals the Rate I capacity price (constant within each May–Oct / Nov–Apr capacity period; 6.380¢ in summer 2026, matching the capacity statement), so Rider Z energy + Rate I capacity ≈ Rate I price. **Open question:** Con Ed's code table groups all of Rider Z with `001IPP`, which could mean Rider Z Rate I should use that code instead; the tariff text favors the choice above.

**Choosing a row.** For a calendar month, use the cycle whose FROM date is closest to the 1st of the month, preferring an exact calendar-month row if present; the differences are small (for example, Aug 2026 Rate I: 14.011¢ for 7/31–8/31 against 14.055¢ for 8/1–8/31 from the online calculator). For an actual bill, use the cycle whose FROM and TO equal the dates printed on the bill, since Con Ed's cycles carry the same dates as its bills (see "Billing periods" for how those dates map to usage days), and otherwise the closest.

### 3. Tariff parameters (`data/tariff.toml`)

Each plan's delivery rates live in `data/tariff.toml` as dated entries, so a rate change means *adding* an entry with a later `effective` date, never editing an old one or touching code. The file has one `[[plan_key]]` table per plan per effective date (`sc1_rate1`, `sc1_rate3`, `sc1_rate4`, `riderz_rate1`) plus `[[bpp]]` for the billing and payment charge; the file's own comments give the field names and units, so they are not repeated here. Example:

```toml
[[sc1_rate1]]                # Leaf 388
effective = 2026-02-01
customer_charge = 21.00
summer_tier_kwh = 250
summer_first = 0.16402
summer_over = 0.18858
nonsummer = 0.16402
```

For each period the engine splits it at season boundaries (Jun 1, Oct 1) and at tariff effective dates, prices each piece with the entry in effect, and prorates by days/30 (see Proration below). A period that starts before a plan's first entry is skipped with a `TariffNotInEffect` message rather than priced with the wrong rates. Units are dollars throughout; leaves before 2026 print cents (for example 35.23¢), which are converted when entered. Nothing before 2025-01-01 is loaded. The rate structure (seasons, hours, holidays) did not change between the two sets of values, only the amounts (Case 25-E-0072).

| Charge | Leaf | Effective 2025-01-01 | Effective 2026-02-01 |
|---|---|---|---|
| **SC 1 Rate I** customer charge ($/month) | 388 | 20.00 | 21.00 |
| Rate I summer, first 250 kWh ($/kWh) | 388 | 0.16107 | 0.16402 |
| Rate I summer, over 250 kWh | 388 | 0.18518 | 0.18858 |
| Rate I non-summer, all kWh | 388 | 0.16107 | 0.16402 |
| **SC 1 Rate III** customer charge | 389.1 | 20.00 | 21.00 |
| Rate III on-peak, summer (8 AM–midnight, *including* holidays) | 389.1 | 0.3523 | 0.2786 |
| Rate III on-peak, non-summer | 389.1 | 0.1305 | 0.1711 |
| Rate III off-peak (midnight–8 AM), all year | 389.1 | 0.0249 | 0.0522 |
| **SC 1 Rate IV** customer charge | 389.2 | 29.00 | 31.00 |
| Rate IV on-peak demand, summer ($/kW; weekdays excl. holidays, noon–8 PM) | 389.2 | 25.36 | 27.35 |
| Rate IV on-peak demand, non-summer | 389.2 | 19.50 | 21.04 |
| Rate IV off-peak demand (all other hours), all year | 389.2 | 7.48 | 7.17 |
| **Rider Z Rate I** customer charge | 327.3 | 20.00 | 21.00 |
| Rider Z on-peak demand, summer (weekdays excl. holidays, noon–8 PM) | 327.3 | 29.66 | 30.68 |
| Rider Z on-peak demand, non-summer | 327.3 | 22.80 | 23.60 |
| Rider Z off-peak demand, all year | 327.3 | 10.00 | 10.06 |

Rate IV's common provisions are at Leaf 389.3, Rider Z's holiday list at Leaf 327.2 and its common provisions at Leaf 327.6. The 2025 values come from the superseded leaves on the DPS site.

**Billing and Payment Processing charge** (GR 26.3, Leaf 353 rev 4/6): $1.28 per bill before 2026-02-01, $1.80 from then. It is the same for every plan and is not prorated. These are the amounts for an electric-only account; other account types (for example combined gas and electric) appear in the same rule and are not modeled.

**Holidays** (Rate IV on-peak and Rider Z on-peak only): New Year's Day (Jan 1), Memorial Day (last Monday in May), Independence Day (July 4), Labor Day (first Monday in September), Thanksgiving (fourth Thursday in November), Christmas (Dec 25). Generated by rule for any year in `conedrates/calendar.py`. The tariff does not mention observed-day shifts when a holiday falls on a weekend, so apply none. Rate III has **no** holiday exclusions.

### 4. Con Ed statements: adjustments, surcharges, SBC and taxes (`data/statements.toml`)

Everything on a real bill beyond tariff delivery and MSC supply comes from Con Edison's published *statements* (PSC No. 10), which the NY DPS posts at https://dps.ny.gov/electric-tariffs → Con Edison → Statements (the "effective" list holds current ones, the "cancelled" list the superseded ones). `data/statements.toml` holds each series as dated entries (effective date, value, statement number), plus a `[meta]` table with `as_of` (statements filed through that date are included) and `sales_tax_pct`. Refreshing means adding entries and bumping `as_of`, never editing old entries. The engine prices from it with the structure of a real bill, and a model built *only* from these statements (no fitting to bills) reproduces six SC 1 Rate I bills line by line (each line within $0.03, totals within $0.06; `tests/test_bills.py`).

**Bill structure**
- **Delivery side:** basic service charge (customer charge × days/30 + billing and payment charge, Inputs 3) + tariff delivery + the per-kWh adders MAC, AF-MAC, RDM, DRS, AMP, DLM, EVS, VDER + System Benefits Charge (NYSERDA part, company-administered part) + CESD.
- **Supply side:** supply (MSC file) + AF-MSC + CESS + MFC.
- **GRT:** a percentage on each side separately (City of New York residential: delivery 4.7940% → 4.8562% from Apr 1 2026, plus 0.2677% for to-dates Jun 2 – Jul 30 2026; supply 2.4066%), then **sales tax** 4.5% on everything including the GRT. Sales tax is not a Con Ed statement; its value is measured from bills.

**Series in the file** (`rule` is explained below; all are per kWh and apply to every plan unless noted)

| Key | Statement | Side | Rule |
|---|---|---|---|
| `afmsc` | Adjustment Factors – MSC, NYC residential, "all other customers", monthly bills | supply | to_date |
| `cess` | Clean Energy Standard Supply Surcharge, total | supply | day_weighted |
| `mfc` | Merchant Function Charge, SC 1 total | supply | day_weighted |
| `mac` | Monthly Adjustment Clause (forecast) | delivery | day_weighted |
| `afmac` | Adjustment Factor – MAC (reconciliation + uncollectible-bill expense + transition adjustment) | delivery | to_date |
| `rdm` | Revenue Decoupling Mechanism Adjustment, SC 1 (six-month periods, Feb–Jul and Aug–Jan) | delivery | day_weighted |
| `drs` | Delivery Revenue Surcharge, SC 1 Rates I–IV and Rider Z | delivery | day_weighted |
| `amp` | Arrears Management Program Recovery Surcharge | delivery | day_weighted |
| `dlm` | Dynamic Load Management Surcharge | delivery | day_weighted |
| `evs` | Electric Vehicle Make Ready Surcharge | delivery | day_weighted |
| `vder` | VDER Cost Recovery, non-standby, NYC delivery (sum of components) | delivery | day_weighted |
| `cesd` | Clean Energy Standard Delivery Surcharge (billed inside the SBC line) | delivery | day_weighted |
| `sbc_nyserda` | SBC, NYSERDA part, all service classes | delivery | day_weighted |
| `sbc_company_kwh` | SBC, company-administered part, per kWh: Rates I–III only | delivery | day_weighted |
| `sbc_company_kw` | SBC, company-administered part, **per kW**: Rate IV and Rider Z only | delivery | day_weighted |
| `grt_delivery_pct`, `grt_supply_pct` | Gross receipts tax and other tax surcharges, City of New York residential, monthly bills (percent) | each side | to_date |

**Units and the AF-MSC merge.** Statements filed before Feb 2026 print cents per kWh (later ones dollars); `statements.toml` holds dollars and each old entry carries the printed cents in a comment. Use the *monthly-bill* column, not the bi-monthly one. Before 2026-02-01 the supply adjustment was the sum of two tables, Adjustment Factor – MSC I (monthly reconciliation) and – MSC II (hedging/rebills, "all other customers"); the NYC-residential values of both are summed into `afmsc` (the sum for statement #170 equals the first merged statement #171). PDF text extraction scrambles the column order of these tables; read the rendered table.

**Which statement value applies to a bill** (`rule` in the file; verified on six bills):
- `to_date`: the statement in effect on the bill's TO date. The tariff says so for the Adjustment Factors – MSC (GR 25.2.4) and – MAC (GR 26.1.3); the GRT statement says "to-date". The "TO date" of a calendar month is its last day.
- `day_weighted`: the average of each usage day's value over the bill. Used for statements that take effect on the 1st of a month. A bill spanning a change blends the statements by days. *Inferred* from the bills: it fits all six, including three that span a change; the next-best of 27 timing combinations fits about three times worse.
- If a day of the period is not covered by any statement the period is skipped with a message (the same as a missing tariff). Statements are in effect "until changed", so periods extending past `as_of` are priced with the last known values and flagged.

**What differs by plan: the System Benefits Charge.** The NYSERDA part (0.39¢/kWh) is the same for all. The company-administered part (from Mar 1 2026) is 0.39¢/kWh for SC 1 Rates I–III but $0.85 per kW of "monthly maximum demand" for Rate IV and Rider Z. Before Mar 2026 the SBC was a single per-kWh amount for all plans (0.47¢ from Jul 1 2025, 0.39¢ from Jan 1 2026). Everything else is a per-kWh amount identical for all plans, so it changes totals but not which plan is cheapest; sales tax and GRT scale every plan's total by about 10%.

**Assumptions and open items**
- *Assumption:* Rider Z pays AMP, DLM and EV Make-Ready. Their statements list "SC 1 – Rates I, II, III and IV" without naming Rider Z, but GR 26.6, 26.10 and 26.11 apply them to all customers.
- *Open:* the meaning of "monthly maximum demand" for the per-kW SBC; the tariff does not define it, and the user plans to ask Con Ed. The engine offers three readings, `--sbc-demand max_billable` (default; the larger of on-/off-peak billable demand), `sum_billable`, and `peak_window` (the single highest 60-minute demand), and flags the choice in the diagnostics. They differ by up to about $2.40 a month on this usage; plan rankings were the same under all three. Whether the per-kW SBC is prorated by days/30 is also unverified (currently not).
- *Open:* statements after `as_of` (2026-10-07) have not been added.

**Status of validation.** Feb–Sep 2026 are reproduced from six real bills; the missing March bill (the Con Ed site would not download it) is predicted within $0.29. Oct 2025 – Jan 2026 are priced from statements and superseded tariff leaves but no bills from those months are available, so they pass only unit and consistency checks (`tests/test_statements.py`, `Backfill`). October 2025 has statements and tariffs but no usage data (usage starts Nov 1 2025).

## Calculation rules

### Billing periods

- The default is calendar months (`Period.calendar_month`; `calendar_months(first, last)` lists them for a usage file).
- Optionally, the user supplies actual bill FROM/TO dates (`bills.csv`, read by `load_bills`), which allows validating against real bills. The six available bills cover Feb–Sep 2026 except March (the Con Ed site would not download that one). See "Status of validation" in Inputs 4.
- **Bill dates are meter-read dates.** A bill "Feb 9 to Mar 11" (30 days = TO − FROM) covers usage from Feb 10 through Mar 11 *inclusive*, i.e. the usage window is [FROM+1, TO+1). Verified on the six bills: with this window, interval kWh match billed kWh within 3 kWh; with [FROM, TO) they were off by up to 22. Con Ed's MSC rows use the bill dates themselves (FROM and TO as printed), so MSC lookup uses FROM and TO unshifted. Implemented by `Period.from_bill` in `conedrates/engine.py`.

### Proration (GR 10.5.2, Leaf 85)

When a period isn't exactly 30 days, let the factor f = days / 30:

- **Customer charge:** × f. Confirmed by the Aug 7 – Sep 8, 2026 bill: $21 × 32/30 + $1.80 billing and payment charge = $24.20 exactly.
- **kWh tier sizes:** × f. The Rate I summer tier becomes 250 × f kWh.
- **Demand ($/kW) charges:** × f. The tariff says "prorated for 30 days"; interpret it as days/30, consistent with the rest of the rule.
- **Per-kWh charges and per-bill charges (billing and payment charge):** not prorated.

**Day counting:** days = TO − FROM, for bills and calendar months alike. A calendar month's TO is the first day of the next month, so its days are the days in the month (the Aug 7 – Sep 8 bill used 32).

**Splitting.** A period is split by days wherever a tariff entry takes effect or a summer/non-summer boundary (Jun 1, Oct 1) falls inside it (GR 10.5.1; Leaf 389.3 also implies season-based proration for Rates I–III). Each piece is priced with its own rates and prorated by its own days. Implemented by `segments()` in `conedrates/engine.py`.

### Time periods

Classify each usage interval by the period it falls in, using local time. An interval belongs to a period if it lies entirely within it; with 15-minute intervals aligned to the clock, no interval straddles a boundary.

**Rate III** has three MSC periods and two delivery periods:
- **Super-peak:** summer (Jun–Sep) weekdays, 2 PM–6 PM, holidays included. MSC is the `001VTO` super-peak price **instead of** the on-peak price (evidence in Inputs 2). Delivery is still the on-peak rate.
- **On-peak:** all days, 8 AM–midnight, except super-peak hours for MSC purposes.
- **Off-peak:** midnight–8 AM.

**Rate IV and Rider Z Rate I** use the same periods for delivery and (Rate IV) MSC:
- **On-peak:** weekdays excluding holidays, noon–8 PM.
- **Off-peak:** all other hours.
- For SC 1 Rate IV, MSC on-peak energy is priced at `001IPP` ON PEAK and off-peak energy at `001IPP` OFF PEAK. Rider Z Rate I's MSC is flat.

### Billable demand (Rate IV and Rider Z Rate I)

The tariff text is at Leaf 389.3 (Rate IV) and Leaf 327.6 (Rider Z):

> For each day in a billing cycle, the maximum daily demand shall be calculated for each time period applicable to that day. The Billable Demands shall be determined by calculating the average of the three highest maximum daily demands occurring in each time period for the applicable billing period. All maximum daily demand values shall be established by calculating the highest integrated 60-minute demand ending in each day and being entirely comprised of intervals ending in the same time period (on-peak, off-peak).

Implementation with 15-minute data (`conedrates/demand.py`):

1. For each day and each period, look at every window of 4 consecutive 15-minute intervals that are all present, all fall in that period, and all start on that day. The window's demand in kW is the sum of its kWh. A missing interval disqualifies the windows containing it.
2. That day's maximum demand for the period is the largest window demand. Days with no qualifying window for a period (e.g. weekends/holidays for on-peak) contribute nothing to that period.
3. Billable demand for the period = the average of the 3 largest daily maxima in the billing period. If fewer than 3 days qualify, average what exists and flag it (`low_data`).
4. Demand charge = billable demand × $/kW rate × f.

"Ending in each day" and "entirely comprised of intervals ending in the same time period" suggest windows cannot cross midnight or a period boundary. That's how step 1 is written. Off-peak spans overnight (8 PM–noon next day on weekdays), so a window from 11:30 PM–12:30 AM crosses days and is excluded. **Deliberate simplification:** the code assigns a window to the day its intervals *start* in, whereas the tariff says "ending in each day"; this differs only for a window ending exactly at midnight (starting 11 PM). Listed in Open items.

### Supply cost

Sum over intervals of kWh × the MSC price applicable to that interval's period (Rate III, SC 1 Rate IV) or kWh × the flat price (Rate I, Rider Z Rate I; the Rider Z choice is an assumption, see Inputs 2). For Rate III, the super-peak price replaces the on-peak price in super-peak hours.

## Output of the engine

`price_period(usage, period, tariff, msc, statements=None, sbc_demand_basis="max_billable")` returns

```
{"diagnostics": {...},
 "plans": {"sc1_rate1" | "sc1_rate3" | "sc1_rate4" | "riderz_rate1":
             {"items": [...], "warnings": [...], "total": ...}}}
```

Each item has `component`, `quantity`, `unit`, `rate`, `amount` and `group` (`"delivery"` or `"supply"`). For each plan and period the items are:

- Customer charge (prorated) and billing and payment charge
- Delivery: for each component, the quantity (kWh or billable kW), rate, and amount
- Supply: for each MSC period, the kWh, price, and amount
- Statement-based adders, SBC, GRT and sales tax (each a separate item), unless priced with `--no-statements`
- The total

Diagnostics: days, proration factor, the MSC row used, the statement numbers used for each series, missing/estimated intervals, low-data demand flags, and warnings for unverified assumptions.

The command line (`python -m conedrates`) takes `--usage`, `--msc`, `--tariff`, `--statements`, `--zone`, `--tension`, `--bills`, `--no-statements`, `--sbc-demand` and `--out` (full itemized JSON). It prints a monthly table. How results are displayed beyond that is described under Purpose.

## Suggested structure

Python with pandas (a settled decision: it is the most mainstream tool for this kind of data work). Inputs are data, rules are code:

```
 INPUTS (data, refreshed by the user)             RULES (code)
 ────────────────────────────────────             ────────────
 usage CSV ───────────► loaders.load_usage ──┐
 LDS_APPND.csv ───────► loaders.load_msc ────┤
 data/tariff.toml ────► loaders.load_tariff ─┼──► engine.price_period ──► {diagnostics,
 data/statements.toml ► statements.py ───────┤        ▲                    plans: {items, total}}
 bills.csv ───────────► bills.load_bills ────┘        │
                                                      ├─ calendar.py  (seasons, holidays, peak hours)
                                                      └─ demand.py    (billable demand)

 scenario functions ─────► (planned) shift usage, re-run the engine
 cli.py ─────────────────► monthly table, JSON
 display functions ──────► (in design) formatted breakdowns
 browser-only app ───────► (Phase 2; technology not decided)
```

The scenario, display and browser layers sit around the engine and never inside it.

- `conedrates/engine.py`: `Period`, `segments`, `price_period`, `run`, `calendar_months`; one pricing function for all four plans, with shared helpers.
- `conedrates/loaders.py`: usage parser, MSC loader and row selection, tariff loader and `TariffNotInEffect`.
- `conedrates/statements.py`: statement series and the `to_date` / `day_weighted` rules.
- `conedrates/calendar.py`: holidays, seasons, time-period classification.
- `conedrates/demand.py`: billable demand.
- `conedrates/bills.py`: real bills, used only for validation.
- `conedrates/cli.py`: command line.
- `data/`: `tariff.toml`, `statements.toml` (the files refreshed when rates change).
- `tests/`: unit tests (`python3 -m unittest discover -s tests -t .`).

## Refreshing the data

Rates change, so refreshing is routine. Each step ends with running the tests (`python3 -m unittest discover -s tests -t .`) and committing on a branch.

**Statements** (`data/statements.toml`). Start at https://dps.ny.gov/electric-tariffs, open the *effective* or *cancelled* electric tariffs list, and follow "Statements" in the Consolidated Edison PSC No. 10 row. Cancelled statements give history and effective ones give the current values. For each series in the table under Inputs 4, add an entry with `effective`, the value and the statement number (`stmt`). Use the NYC residential, SC 1, monthly-bill figures. Before Feb 2026, convert printed cents to dollars and keep the cents in a comment. Read the rendered table, not extracted text, which scrambles columns. Some statements are effective for only a few days or for six-month periods, and several can take effect in one month. Then bump `as_of` in `[meta]`.

**Tariff** (`data/tariff.toml`). When a leaf is reissued, add a new `[[plan_key]]` entry (or `[[bpp]]`) with the new `effective` date and a comment naming the leaf and revision. Do not edit old entries. Superseded leaves are in the DPS site's cancelled Leaves list. Update the table under Inputs 3 to match.

**MSC file** (`LDS_APPND.csv`). Con Edison publishes the supply-price file; the user downloads the new version and replaces the old one. The loader enforces the checks described under Inputs 2 (duplicates, the 35-day rule). Check that the newest cycles have prices for all four code families.

**Usage.** Download a new interval CSV from the Con Ed account and replace `usage.csv`.

**Bills (optional validation).** Transcribe new bills into the private bills files and run `tests/test_bills.py`; a new month that does not reproduce signals a missing or mistimed statement.

## Test cases

**1. Bill reproduction (SC 1 Rate I).** Bill period 2026-08-07 → 2026-09-08 (32 days), 308 kWh:
- Customer charge 21 × 32/30 = 22.40; plus billing and payment charge 1.80 = **$24.20** (matches the bill).
- Tier: 250 × 32/30 = 266.67 kWh at 0.16402 + 41.33 kWh at 0.18858 = **$51.53** (16.732¢/kWh average). The bill shows 17.338¢; the gap is the statement-based adders, which case 6 reproduces.
- MSC: the bill shows 13.727¢/kWh; the online calculator gives 13.8152¢ for these dates. The small gap is attributed to which cycle row is used (see "Choosing a row" in Inputs 2); case 6 reproduces the bill from the file row for its own dates.

**2. MSC lookup.** The calendar-month row 2026-07-01 → 2026-07-31 should give:
- Rate I 0.144326
- Rate III 0.897796 / 0.084043 / 0.065453
- IPP on/off 0.353062 / 0.074175

These match the user's manual pulls from the online calculator.

**3. Rate III super-peak presence.** The period 2026-04-30 → 2026-05-31 has `001VTO` ALL HOURS = 0; the period 2026-04-30 → 2026-06-01 has 0.878514. The engine must never apply a super-peak price outside June–September days.

**4. Synthetic demand tests** (hand-checkable; `Demand` in `tests/test_engine.py`):
- Constant 1 kW load → billable demand 1 kW in both periods.
- One 2-hour 5 kW spike on a single weekday afternoon → on-peak billable demand = (5 + 1 + 1)/3 ≈ 2.33 kW on a 1 kW base.
- A spike on a Saturday at 3 PM counts toward **off-peak**.
- A spike on July 4 (weekday) is off-peak for Rate IV/Rider Z but on-peak/super-peak for Rate III.

**5. Holidays** (`Holidays` in `tests/test_engine.py`). Check generated dates, e.g. Memorial Day 2026 = May 25; Labor Day 2026 = Sep 7; Thanksgiving 2026 = Nov 26.

**6. Real bill reproduction** (`tests/test_bills.py`, skipped when the private files are absent). Six SC 1 Rate I bills, Feb 9 – Sep 8 2026, priced from the statements alone: each bill line (basic, delivery, SBC, supply, MFC, GRT, sales tax) within $0.03 and totals within $0.06 using billed kWh; within 2% from raw interval data.

**7. Out-of-sample bill.** The Mar 11 – Apr 9 2026 bill could not be downloaded. Its kWh (203) is the Apr bill's prior read minus the Mar bill's new read (15867 − 15664); its total ($97.66) is in the Apr bill's "previous charges" summary. The statement model predicts $97.37.

**8. Statement lookup** (`tests/test_statements.py`, public data): the `to_date` rule, the `day_weighted` blend across a statement change (Jul 9 – Aug 7 bill: 22 days under RDM #37, 7 under #38), uncovered days raising, and plan scope.

**9. Loader robustness** (`tests/test_loaders.py`, public fixtures `tests/usage_trimmed.csv` and `tests/usage_with_junk.csv`, plus generated files): preamble skipping, BOM, CRLF, missing header and empty file raising `ValueError` without echoing file contents.

**Planned, not yet written:** a synthetic hourly-interval usage test (see Open items).

Tests that need private files (`usage.csv`, `bills/`, `LDS_APPND.csv`) skip when those are absent, so the suite passes on a fresh clone.

## Open items

This list is an index; the detail is at the places cited.

1. ~~Sample usage export and parser.~~ Done (Inputs 1).
2. ~~Confirm the `LDS_APPND.csv` layout and code meanings; verify the Rate III super-peak replacement.~~ Done (Inputs 2).
3. Confirm the per-kW proration interpretation (days/30), ideally against a real demand-billed bill.
4. Display functions for `price_period` output: in design (`new-outputters` branch). Scenario (usage-shifting) functions: planned.
5. ~~Statements and tariffs back to Oct 2025 / Jan 2025.~~ Done. Still open: bills to validate Oct 2025 – Jan 2026; statements after `as_of` (2026-10-07); the NYC-residential statement columns are hard-wired, so other zones need other columns.
6. The meaning of "monthly maximum demand" for the per-kW SBC (ask Con Ed); whether Rider Z pays AMP, DLM and EV Make-Ready (Inputs 4).
7. Rider Z Rate I's MSC code: `001` (current) or `001IPP` (Con Ed's code table groups Rider Z with it) (Inputs 2).
8. A synthetic hourly-interval usage test; hourly intervals have not been tested.
9. Assess the Green Button XML export: does it carry anything the CSV does not?
10. Billable-demand window assignment at midnight: the code uses the day a window starts in, the tariff says "ending in each day".
11. Write down refresh procedures for the statements file and the MSC file.

## Background notes

- Supply prices shifted a lot between years. Rate I capacity was ~4.18¢/kWh in summer 2025 and ~6.38¢ in summer 2026; the Rate III super-peak went from ~78¢ to ~89¢. When two plans come out close, report each year separately.
- Rate III's super-peak MSC is very high (~89¢/kWh in summer 2026), so super-peak usage (summer weekdays, 2–6 PM) is far more expensive on Rate III than on any other plan.
- Enrollment constraints (lock-in periods, return restrictions) are in the tariff pages for each rate. They're not modeled, but worth mentioning in any recommendation.

## Glossary

- **AF-MAC / AF-MSC:** Adjustment Factor – MAC / – MSC. After-the-fact corrections to the forecast adjustments.
- **AMP:** Arrears Management Program recovery surcharge.
- **BPP:** billing and payment processing charge (GR 26.3), a flat amount per bill.
- **CESD / CESS:** Clean Energy Standard Delivery / Supply surcharge.
- **DLM:** Dynamic Load Management surcharge.
- **DRS:** Delivery Revenue Surcharge.
- **EVS:** Electric Vehicle Make Ready surcharge.
- **GR:** General Rule, a numbered section of the tariff. **Leaf:** the tariff's own page number.
- **GRT:** gross receipts tax, charged as a percentage on each side of the bill.
- **MAC:** Monthly Adjustment Clause, a forecast adjustment to delivery charges.
- **MFC:** Merchant Function Charge, supply-related costs.
- **MSC:** Market Supply Charge, the price of the electricity itself.
- **RDM:** Revenue Decoupling Mechanism adjustment.
- **SBC:** System Benefits Charge (energy-efficiency and clean-energy programs).
- **SC 1:** Service Classification 1, residential service.
- **VDER:** Value of Distributed Energy Resources cost recovery.
- **Zone J:** the NYISO zone for New York City.
