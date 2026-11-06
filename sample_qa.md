# Sample Q&A

Facts-only prototype over the five allowlisted Groww pages. Refusal rows use the exact deterministic policy messages. Factual rows are retrieval-verified against stored chunks; generated Groq wording may vary slightly, but the cited source and last-updated rule are fixed.

**Disclaimer:** Facts-only. No investment advice. Answers may be incomplete or out of date; always verify on the cited source. Mutual fund investments are subject to market risks.

| # | Question | Intent | Sample answer | Source |
|---|----------|--------|---------------|--------|
| 1 | What is the expense ratio of HDFC Large Cap Fund Direct Growth? | fact | The expense ratio is 1.01%. | [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 2 | What is the minimum SIP for HDFC Mid Cap Fund Direct Growth? | fact | The minimum SIP investment is ₹100. | [HDFC Mid Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) |
| 3 | What is the exit load of HDFC Flexi Cap? | fact | Exit load of 1% applies if redeemed within 1 year. | [HDFC Flexi Cap Direct Plan Growth](https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth) |
| 4 | What is the benchmark of HDFC Large Cap? | fact | The benchmark is the NIFTY 100 Total Return Index. | [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 5 | What is the AUM of HDFC Large Cap Fund? | fact | The page shows AUM of ₹9,34,076 Cr. | [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 6 | What is the NAV of HDFC Large Cap Fund? | fact | The latest NAV shown is ₹1,233.61 as of 05 Nov 2026. | [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| 7 | What is the lock-in for HDFC ELSS Tax Saver? | out_of_corpus | That fact isn't available on the five sourced Groww pages. Please check the linked official page for details. | [HDFC Mutual Fund](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |
| 8 | How can I download a capital gains statement? | out_of_corpus | That fact isn't available on the five sourced Groww pages. Please check the linked official page for details. | [HDFC Mutual Fund](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |
| 9 | Should I buy HDFC Flexi Cap? | refuse_advice | I can only share facts from the listed Groww pages and can't offer investment advice or recommendations. Please ask about a specific fact such as expense ratio, exit load, or minimum SIP. | [HDFC Mutual Fund](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |
| 10 | What was 1Y return of HDFC ELSS? | refuse_returns | I can't calculate, compare, or comment on returns or performance. You can check the official scheme page for published figures. | [HDFC Mutual Fund](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |
| 11 | My PAN is ABCDE1234F, show holdings | refuse_pii | I can't accept PAN, Aadhaar, account, OTP, email, or phone details. Please ask a facts-only question without personal information. | [HDFC Mutual Fund](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |
| 12 | What is the riskometer of HDFC Large Cap? | out_of_corpus | That fact isn't available on the five sourced Groww pages. Please check the linked official page for details. | [HDFC Mutual Fund](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) |

## Expected last-updated line

For the factual rows above, the UI derives the line from the stored `fetched_at` value:

`Last updated from sources: 06 Nov 2026`

## Notes

- Rows 1–6 are factual retrieval targets. The app must not add outside facts, compute returns, or give advice.
- Row 7 reflects a corpus limitation: the retrieved ELSS chunk contains the “Lock-in” label and a “3Y annualised” return figure, but no lock-in duration. A deterministic post-check converts an invented duration to `out_of_corpus`.
- Row 8 reflects that the corpus does not describe a download procedure; the assistant returns `out_of_corpus` rather than invent steps or ask for account details.
- Rows 9–12 are deterministic refusals and do not require Groq.
- To capture live generated wording, add `GROQ_API_KEY` and `LLM_MODEL` to `.env` and ask the same questions in the UI.
