# Con Ed rate calculator

This Python script takes electrical usage data downloaded from a user's Con Ed account and computes the cost of the usage under four different Con Ed plans typically available to consumers.

## The four plans

Here's a very quick description of the plans. All plans include a charge for *delivery*, meant to account for the costs of the electrical infrastructure carrying the electricity to consumers, and a charge for *supply*, meant to account for the costs of producing the electricity. The default plan essentially just charges both by the kilowatt-hour (the amount of energy used by a 1000-watt appliance run for one hour). The time-of-use rate is the same, but both supply and demand prices vary based on the the time of year and the time of day. The other two plans are similar in their supply charges, but the delivery charges are quite different. Instead of billing according to the amount of energy used, the delivery cost for these plans is based on the *maximum* amount of energy used over any hour-long period in the billing cycle. (Actually, it's slightly more complicated than that: instead of the maximum in any hour, it's the mean of the three highest-energy hours in the billing period. And this is done separately for the peak- and off-peak times of day.) These last two are supposed to be good for heat pump users, who often have very steady demand.

| Plan | Consumer name (from a Con Ed email) | Delivery basis | Supply (MSC) basis |
|---|---|---|---|
| SC 1 Rate I (default; Con Ed rate code EL1) | Standard Residential Rate | per kWh, summer/nonsummer | flat per kWh |
| SC 1 Rate III (voluntary time-of-day) | Time-of-Use Rate | per kWh, on/off-peak | per kWh, super-peak / on-peak / off-peak |
| SC 1 Rate IV (optional demand-based) | Steady Use Rate (SUR) | per kW demand, on/off-peak | per kWh, on/off-peak |
| Rider Z Rate I (Innovative Pricing Pilot) | Smart Energy Plan (SEP) | per kW demand, on/off-peak | flat per kWh |

## Downloading your data

Go to https://coned.com and log into your Con Ed account. At the top is a menu *Account & Billing*, and inside the menu is a link *Energy Use*. Follow this link. Then click on *Green Button-Download my data*. Choose *Export usage for a range of days* and choose time period. You can choose any amount of time up to a year in length. Choose CSV for format. Click on export and your data will download.

## Running the calculator

Clone this repository. Download your data as above. Call the file usage.csv and put it in the main directory of this repository. Run

python -m conedrates

The prices outputted will assume that each calendar month is a billing period, so it won't exactly match your bills, but it should be quite close.