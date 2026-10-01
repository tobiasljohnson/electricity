# Con Ed Residential Rate Comparison — Project Spec

## Purpose

Take a Con Edison customer's interval usage data and estimate what that usage would have cost under four residential billing options. Data files (usage, market supply prices, tariff rates) must be replaceable over time without code changes.

The output/report format is **deliberately not specified yet**. The pricing engine should return an itemized breakdown (per plan, per billing period, per charge component) so that any report can be built on top of it later.

All tariff references are to Con Ed's PSC No. 10 electric tariff (`electric-tariff.pdf`). "PDF p." is the page in that file, and "Leaf" is the tariff's own page number. All rates below took effect 02/01/2026 unless noted.

## The four plans

| Plan | Delivery basis | Supply (MSC) basis |
|---|---|---|
| SC 1 Rate I (default; the user's current rate, billed as "EL7") | per kWh, summer tier | flat per kWh |
| SC 1 Rate III (voluntary time-of-day) | per kWh, on/off-peak | per kWh, super-peak / on / off |
| SC 1 Rate IV (optional demand-based) | per kW demand, on/off-peak | per kWh, on/off-peak |
| Rider Z Rate I (Innovative Pricing Pilot) | per kW demand, on/off-peak | flat per kWh |

Rider Z Rate I is the relevant Rider Z rate because voluntary (non-recruited) enrollees are assigned to Rate I (PDF p. 484). Voluntary enrollees do not get the Rider Z bill-protection guarantee.

"Summer" means June, July, August and September for every plan.

## Inputs (each independently updatable)

### 1. Usage data

This is the interval export from the customer's Con Ed account ("Green Button" / "Download My Data"). The script should read the export as downloaded. **The format is not yet known; get a sample file from the user before writing the parser.** Things to determine from the sample:

- Interval length. It is expected to be 15 minutes. If it is hourly, the 60-minute demand calculation below becomes clock-hour kWh; say so in the output.
- Timestamp convention (interval start or end, time zone, how DST transitions appear).
- Units (kWh per interval vs. kW), and whether estimated or missing intervals are marked.

### 2. Market Supply Charge (MSC) data

The input is Con Ed's `LDS_APPND.CSV` ("MSC Lookup File"), downloadable from coned.com → Market Supply Charge Calculator page. Its code meanings are in the "Reference Code File (PDF)" on the same page. Updating the data should require nothing more than downloading a new copy.

The raw file's exact layout still needs confirming. It includes zone and tension columns; use **Zone J, low tension**, and make both configurable. A user-filtered version (`filtered.csv`) with these columns exists and can be used for development:

```
SC AND, FROM DT, TO DT, TRIP, ALL HOURS, ON PEAK, OFF PEAK
```

- Each row is one **billing cycle** (`TRIP` = meter-reading cycle 1–22), not a calendar month. Dates are YYYYMMDD and prices are in $/kWh.
- The file covers roughly Nov 2024 – Sep 2026 so far.
- There are exact duplicate rows (same cycle under two TRIP numbers); dedupe them.
- Some rows span 93–126 days (irregular bills); ignore rows longer than ~35 days.

Column meaning depends on the code:

| Code | ALL HOURS | ON PEAK | OFF PEAK |
|---|---|---|---|
| `1` (SC 1 Rates I & II) | **Rate I price** | Rate II on-peak (unused) | Rate II off-peak (unused) |
| `001VTO` (SC 1 Rate III) | **Rate III super-peak price**; 0 if the period contains no June–Sept day | **Rate III on-peak** | **Rate III off-peak** |
| `001IPP` (Rider Z Rate IV) | Rate I price minus Rate I capacity (unused; see below) | **Rider Z Rate IV on-peak** | **Rider Z Rate IV off-peak** |

**Mapping MSC prices to plans:**

- **SC 1 Rate I:** `1` / ALL HOURS.
- **SC 1 Rate III:** `001VTO` super-peak, on-peak and off-peak.
- **SC 1 Rate IV:** `001IPP` ON/OFF PEAK. *Assumption:* the file has no separate SC 1 Rate IV entry. SC 1 Rate IV and Rider Z Rate IV share the same capacity charge in the Statement of MSC – Capacity, so their MSCs should be equal or nearly so.
- **Rider Z Rate I:** `1` / ALL HOURS, i.e. the SC 1 Rate I price. *Assumption:* the file and the Con Ed calculator give no Rider Z Rate I price. The data supports the assumption: `1`/ALL HOURS − `001IPP`/ALL HOURS equals the Rate I capacity price (constant within each May–Oct / Nov–Apr capacity period; 6.380¢ in summer 2026, matching the capacity Statement). So Rider Z energy + Rate I capacity ≈ Rate I price.

**Choosing a row for a calendar month:** use the cycle whose FROM date is closest to the 1st of the month; prefer an exact calendar-month row if present. The differences are small (e.g. Aug 2026 Rate I: 14.011¢ for 7/31–8/31 vs 14.055¢ for 8/1–8/31 from the online calculator). If the user supplies actual bill dates, use the row whose FROM/TO dates match or are closest.

### 3. Tariff parameters (config file)

Use a YAML (or similar) file listing each plan's parameters, each set with an effective date, so that a rate change means adding an entry, not editing code. The engine should pick the entry in effect for each period and apply GR 10.5.1 proration if a rate change falls inside a period (see Proration below).

Current values:

**SC 1 Rate I** (PDF p. 616, Leaf 388)
- Customer charge: $21.00/month
- Summer: first 250 kWh $0.16402/kWh; over 250 kWh $0.18858/kWh
- Non-summer: all kWh $0.16402/kWh

**SC 1 Rate III** (PDF p. 618, Leaf 389.1)
- Customer charge: $21.00/month
- On-peak (all days, 8 AM–midnight, *including* holidays): summer $0.2786/kWh; non-summer $0.1711/kWh
- Off-peak (midnight–8 AM): $0.0522/kWh all year

**SC 1 Rate IV** (PDF p. 619, Leaf 389.2; common provisions PDF p. 621, Leaf 389.3)
- Customer charge: $31.00/month
- On-peak demand (weekdays excluding holidays, noon–8 PM): summer $27.35/kW; non-summer $21.04/kW
- Off-peak demand (all other hours): $7.17/kW all year

**Rider Z Rate I** (PDF p. 486, Leaf 327.3; holidays PDF p. 485; common provisions PDF p. 491)
- Customer charge: $21.00/month
- On-peak demand (weekdays excluding holidays, noon–8 PM): summer $30.68/kW; non-summer $23.60/kW
- Off-peak demand (all other hours): $10.06/kW all year

**Billing and Payment Processing charge** (GR 26.3): $1.80 per bill. This is the same for every plan and is not prorated.

**Holidays** (Rate IV on-peak and Rider Z on-peak only): New Year's Day (Jan 1), Memorial Day (last Monday in May), Independence Day (July 4), Labor Day (first Monday in September), Thanksgiving (fourth Thursday in November), Christmas (Dec 25). Generate these by rule for any year. The tariff does not mention observed-day shifts when a holiday falls on a weekend, so apply none. Rate III has **no** holiday exclusions.

### 4. Optional common charges

These are the per-kWh charges that apply identically under all four plans: GR 26 additional delivery charges and adjustments (MAC, RDM, etc.), MSC adjustment factors, the Merchant Function Charge, the Clean Energy Standard Supply Surcharge, and the GR 30 gross receipts tax percentage. Their values come from monthly Con Ed Statements that are not in the tariff.

- Accept them as a single optional $/kWh figure plus an optional GRT percentage.
- They don't change which plan is cheapest (except that GRT scales the differences), but they are needed for totals that resemble a real bill.
- Evidence from the user's bills: the displayed delivery rate exceeded the tariff rate by ~0.61¢/kWh (Aug–Sep 2026) and ~3.20¢/kWh (Mar–Apr 2026), so this varies a lot by month.
- *Unverified:* some of these adjustments might be computed separately for demand-billed customers. Note this as a caveat when plans come out close.

## Calculation rules

### Billing periods

- The default is calendar months.
- Optionally, the user can supply a list of actual bill FROM/TO dates. That allows validating against real bills.

### Proration (GR 10.5.2, PDF text near Leaf 85)

When a period isn't exactly 30 days, let the factor f = days / 30:

- **Customer charge:** × f. This is confirmed by the user's bill: $21 × 32/30 + $1.80 BPP = $24.20 exactly.
- **kWh tier sizes:** × f. The Rate I summer tier becomes 250 × f kWh.
- **Demand ($/kW) charges:** × f. The tariff says "prorated for 30 days"; interpret it as days/30, consistent with the rest of the rule.
- **Per-kWh charges and per-bill charges (BPP):** not prorated.

**Day counting:** the user's Aug 7 – Sep 8 bill used 32 days (TO − FROM). Treat a calendar month as TO − FROM, where TO is the first day of the next month, i.e. the number of days in the month.

If a rate change or summer/non-summer boundary falls inside a user-supplied bill period, split by days (GR 10.5.1; PDF p. 621 also implies season-based proration for Rates I–III). Calendar-month periods avoid the seasonal case entirely.

### Time periods

Classify each usage interval by the period it falls in, using local time. An interval belongs to a period if it lies entirely within it; with 15-minute intervals aligned to the clock, no interval straddles a boundary.

**Rate III** has three MSC periods and two delivery periods:
- **Super-peak:** summer (Jun–Sep) weekdays, 2 PM–6 PM, holidays included. MSC is the `001VTO` super-peak price **instead of** the on-peak price. Delivery is still the on-peak rate.
  - *To verify* against the Reference Code PDF: that the super-peak price replaces (rather than adds to) the on-peak MSC for those hours. The numbers support replacement: super-peak ≈ energy + the full 2–6 PM capacity charge from the Statement.
- **On-peak:** all days, 8 AM–midnight, except super-peak hours for MSC purposes.
- **Off-peak:** midnight–8 AM.

**Rate IV and Rider Z Rate I** use the same periods for delivery and (Rate IV) MSC:
- **On-peak:** weekdays excluding holidays, noon–8 PM.
- **Off-peak:** all other hours.
- For SC 1 Rate IV, MSC on-peak energy is priced at `001IPP` ON PEAK and off-peak energy at `001IPP` OFF PEAK. Rider Z Rate I's MSC is flat.

### Billable demand (Rate IV and Rider Z Rate I)

The tariff text is at PDF p. 621 (Rate IV) and p. 491 (Rider Z):

> For each day in a billing cycle, the maximum daily demand shall be calculated for each time period applicable to that day. The Billable Demands shall be determined by calculating the average of the three highest maximum daily demands occurring in each time period for the applicable billing period. All maximum daily demand values shall be established by calculating the highest integrated 60-minute demand ending in each day and being entirely comprised of intervals ending in the same time period (on-peak, off-peak).

Implementation with 15-minute data:

1. For each day and each period, look at every window of 4 consecutive 15-minute intervals that all fall in that period and that day. The window's demand in kW is the sum of its kWh.
2. That day's maximum demand for the period is the largest window demand. Days with no qualifying window for a period (e.g. weekends/holidays for on-peak) contribute nothing to that period.
3. Billable demand for the period = the average of the 3 largest daily maxima in the billing period. If fewer than 3 days qualify, average what exists and flag it.
4. Demand charge = billable demand × $/kW rate × f.

"Ending in each day" and "entirely comprised of intervals ending in the same time period" suggest windows cannot cross midnight or a period boundary. That's how step 1 is written. Off-peak spans overnight (8 PM–noon next day on weekdays), so a window from 11:30 PM–12:30 AM crosses days and is excluded.

### Supply cost

Sum over intervals of kWh × the MSC price applicable to that interval's period (Rate III, SC 1 Rate IV) or kWh × the flat price (Rate I, Rider Z Rate I).

## Output of the engine

For each plan and each period, return an itemized record of:

- Customer charge (prorated), BPP
- Delivery: for each component, the quantity (kWh or billable kW), rate, and amount
- Supply: for each MSC period, the kWh, price, and amount
- Optional common charges and GRT, if supplied
- Totals
- Diagnostics: days, proration factor, the MSC row used, missing/estimated intervals, low-data demand flags

Report formatting comes later.

## Suggested structure

Python + pandas is a reasonable default; confirm with the user.

- `data/`: usage exports, `LDS_APPND.CSV`, `tariff.yaml`. These are the files the user refreshes.
- Loaders: usage parser, MSC loader/filter, tariff loader.
- Engine: one pricing function per plan, `price_<plan>(intervals, period, tariff, msc) -> breakdown`, plus shared helpers for period classification, holidays, proration, and billable demand.
- CLI entry point: input paths, zone, and optional bill-dates file → breakdowns (e.g. CSV/JSON) for now.

## Test cases

**1. Bill reproduction (SC 1 Rate I).** Bill period 2026-08-07 → 2026-09-08 (32 days), 308 kWh:
- Customer charge 21 × 32/30 = 22.40; plus BPP 1.80 = **$24.20** (matches the bill).
- Tier: 250 × 32/30 = 266.67 kWh at 0.16402 + 41.33 kWh at 0.18858 = **$51.53** (16.732¢/kWh average). The bill shows 17.338¢; the gap is common adjustments, not an error.
- MSC: the bill shows 13.727¢/kWh; the online calculator gives 13.8152¢ for these dates. The small gap is unexplained and acceptable.

**2. MSC lookup.** The calendar-month row 2026-07-01 → 2026-07-31 should give:
- Rate I 0.144326
- Rate III 0.897796 / 0.084043 / 0.065453
- IPP on/off 0.353062 / 0.074175

These match the user's manual pulls from the online calculator.

**3. Rate III super-peak presence.** The period 2026-04-30 → 2026-05-31 has `001VTO` ALL HOURS = 0; the period 2026-04-30 → 2026-06-01 has 0.878514. The engine must never apply a super-peak price outside June–September days.

**4. Synthetic demand tests** (hand-checkable):
- Constant 1 kW load → billable demand 1 kW in both periods.
- One 2-hour 5 kW spike on a single weekday afternoon → on-peak billable demand = (5 + 1 + 1)/3 ≈ 2.33 kW on a 1 kW base.
- A spike on a Saturday at 3 PM counts toward **off-peak**.
- A spike on July 4 (weekday) is off-peak for Rate IV/Rider Z but on-peak/super-peak for Rate III.

**5. Holidays.** Check generated dates, e.g. Memorial Day 2026 = May 25; Labor Day 2026 = Sep 7; Thanksgiving 2026 = Nov 26.

## Open items

1. Get a sample usage export and write its parser (interval length, timestamp convention, DST).
2. Confirm the raw `LDS_APPND.CSV` layout and code meanings against the Reference Code PDF.
3. Verify that the Rate III super-peak price replaces the on-peak MSC for those hours.
4. Confirm the per-kW proration interpretation (days/30), ideally against a real demand-billed bill if one can be found.
5. Decide the report format (the user has ideas; deferred until the engine works).

## Background notes

- Supply prices shifted a lot between years. Rate I capacity was ~4.18¢/kWh in summer 2025 and ~6.38¢ in summer 2026; the Rate III super-peak went from ~78¢ to ~89¢. When two plans come out close, report each year separately.
- Rate III's super-peak MSC is very high (~89¢/kWh in summer 2026). With delivery included, summer weekday 2–6 PM usage costs ~$1.17/kWh on Rate III.
- Enrollment constraints (lock-in periods, return restrictions) are in the tariff pages for each rate. They're not modeled, but worth mentioning in any recommendation.
