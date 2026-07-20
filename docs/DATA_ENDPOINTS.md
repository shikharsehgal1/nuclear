# SPUT Research — Public Data Endpoint Inventory

Discovery run: 2026-07-20 (UTC). All raw responses archived under
`data/raw/discovery/` with companion `.meta.json` files (`url`, `retrieved_at`, `http_status`, notes).

Tier definitions used here:
- **Tier 2** — public *official* published values with timestamps (fund sponsor / recognized publisher).
- **Tier 3** — public proxy for the quantity we actually want.
- **Tier 4** — must be reconstructed/derived (no direct public series).

---

## 1. Sprott Physical Uranium Trust (primary target)

### 1.1 Fund page with inline full history — **WORKING, Tier 2** (primary dataset)

- **URL:** `https://sprott.com/investment-strategies/exchange-listed-products/physical-commodity-funds/uranium/`
- **Method:** plain GET with a browser User-Agent (curl works; no JS execution needed).
- **Key finding:** there is **no XHR/JSON API for history**. The site is Umbraco CMS and the
  Highcharts configs are **server-rendered inline in the HTML** with the *entire* history
  since inception embedded as JS arrays (`data: [[Date.UTC(y,m,d),v],...]`). Re-fetching the
  page daily yields the full, updated history each time.
- **Series embedded (all verified by extraction):**

  | Series (Highcharts `name`) | Frequency | Range obtained | Points | Units |
  |---|---|---|---|---|
  | `Net Asset Value` | daily (TSX trading days) | 2021-07-19 → 2026-07-17 | 1,255 | **USD** NAV/unit (U.U) |
  | `Share Price` | daily | 2021-07-19 → 2026-07-17 | 1,255 | USD close, TSX U.U |
  | `Premium/Discount to Net Asset Value` | daily | 2021-07-19 → 2026-07-17 | 1,255 | % vs NAV |
  | `Growth of $10,000 Value` | daily | 2021-07-19 → 2026-07-17 | 1,255 | USD NAV total-return index |
  | `Pounds of U308 (millions)` | weekly (Fridays) | 2021-07-16 → 2026-07-17 | 255 | millions lbs U3O8, 1 decimal |
  | `Daily Pounds Acquired` + `Cumulative` | per purchase date | 2021-07-19 → 2026-05-11 | 256 | lbs acquired (excludes ~18.1M lbs initial UPC holdings) |

- **Parsing notes:** dates are JS `Date.UTC(year, month, day)` with **0-indexed months**.
  The weekly pounds chart stores dates in `xAxis.categories` and values in a separate
  numeric array (index-aligned). Chart `renderTo` ids: `Uranium_Market_Price_Vs_NAV_Graph_Placeholder`,
  `Uranium_PDC_Graph_Placeholder`, `Uranium_Growth_Of_10K_NetAssetValue_Placeholder`,
  `Uranium_Uranium_MetalsHeldChart_Placeholder`, `Uranium_Uranium_MetalsAcquiredChart_Placeholder`.
- **Timezone/currency ambiguities:** dates are trade dates; page footer says values
  "last updated 6:00 PM EST". NAV and market-price series are USD (per page disclosure:
  "NAV performance calculation is based on the USD NAV and the market price performance
  calculation is based on the USD closing price on the TSX"). **No CAD (U.UN) NAV history
  is published** — the CA$ block on the page is current-day only. Weekly lbs held is
  "based on trade date" (not settlement).
- **Current-day snapshot also in page:** NAV, market price, premium/discount, total lbs
  (full precision: 81,447,348), units outstanding (344,156,215), market value of uranium
  ($6,968,512,888), total NAV ($7,085,131,837) — but **as-of latest day only**, no history.
- **Robots/licensing:** `sprott.com/robots.txt` does not disallow this path. Standard
  website terms; data republished for research should credit Sprott.
- **Files saved:** `sprott_uranium_page_full.html`, derived
  `sprott_uranium_inline_series.extracted.json` (all six series, ISO dates).

### 1.2 Sprott JSON API (current-day only) — **WORKING, Tier 2 snapshot**

- **URL:** `https://sprott.com/api/FinancialData/v1/BullionCalculatorData` (GET, no params honored)
- Returns a JSON array (double-encoded as a JSON string) covering all Sprott physical
  trusts. **SPUT = `id: 1218`**. Fields: `dateTimeStamp` (latest NAV date, `T00:00:00Z`),
  `nav` (USD NAV/unit, 4 dp), `pdCalc` (premium/discount %), `units` (units outstanding),
  `totalNav` (USD), `totalMarketValue` (USD value of uranium held), `totalOunces1`
  (**lbs of U3O8** for SPUT despite the name), `totalOunces2` (0 for SPUT).
- `?date=YYYY-MM-DD` is **ignored** — always returns latest day. No history variant found.
- This is the highest-precision daily record (units outstanding + total NAV are not in the
  charts) — **poll it daily going forward** to build point-in-time history.
- **File saved:** `sprott_api_bullioncalculatordata.json`.

### 1.3 Sprott endpoints tried and FAILED

| URL | Result |
|---|---|
| `https://sprott.com/api/FinancialData/v1/` | 404 |
| `https://sprott.com/api/FinancialData/v1/BullionCalculatorHistory` | 404 |
| `https://sprott.com/api/` | 404 |
| `https://sprott.com/swagger/index.html` | 404 |
| `?date=` param on BullionCalculatorData | 200 but parameter ignored (latest day only) |

No Kurtosys/fundpress/ycharts embeds present in the page (searched: `kurtosys`,
`fundpress` — only a CMS partial named "FundPressReleases", unrelated). Web search found
no third-party GitHub scraper documenting a hidden Sprott history API; the inline-HTML
approach above is the mechanism.

### 1.4 Gaps → reconstruction (Tier 4)

- **Units outstanding / total NAV / uranium market value history:** not published as a
  series anywhere found. Reconstruct from (a) daily polling of §1.2 going forward, and
  (b) Wayback Machine snapshots of the fund page / API
  (`web.archive.org/web/*/sprott.com/*uranium*`) for backfill; or derive
  `units ≈ totalNav / nav` from archived snapshots. Also derivable: uranium market value
  ≈ weekly lbs held × spot price (proxy, Tier 4).
- **CAD (U.UN) NAV history:** reconstruct as USD NAV × daily USD/CAD noon rate (Bank of
  Canada Valet API is public), Tier 4; exact published CAD NAV only via archived snapshots.
- **Sprott's proprietary composite spot price** (TradeTech/UxC/Platts/Numerco composite):
  only period returns are published (benchmark rows in the performance tables), no daily
  level series. Use Numerco (§3) as a Tier 3 daily proxy.

---

## 2. Cameco — monthly UxC/TradeTech spot & long-term prices — **WORKING, Tier 2**

- **URL:** `https://www.cameco.com/invest/markets/uranium-price`
- Full monthly table is **embedded in the HTML** (Drupal view `uranium_price`, inside
  `<div data-controller="table-chart" data-table-chart-config-value="uraniumPrice">`;
  hidden `<table>` with rows `views-field-field-monthly-date`, `...-spot-price`,
  `...-long-term-price`).
- **Range obtained:** 463 rows, **1988-01-01 → 2026-06-30**, USD/lb. Spot = average of
  month-end prices published by UxC and TradeTech; long-term prior to May 2004 is
  TradeTech only (per page disclosure). Dates are `YYYY/MM/DD` month markers; treat as
  month-end values.
- **Licensing:** underlying values are UxC/TradeTech assessments republished by Cameco —
  fine for research, do not redistribute as a commercial feed. Robots.txt does not
  disallow `/invest/`.
- **Files saved:** `cameco_uranium_price_page.html`,
  `cameco_monthly_uranium_prices.extracted.json`.

---

## 3. Numerco — daily U3O8 spot price history — **WORKING, Tier 2/3**

- **Landing page:** `https://numerco.com/UHistory/` (linked from
  `https://numerco.com/menu/live-price-indications/`). Note
  `https://numerco.com/NSet/aCNSet.html` is **gone (404)**; `/NSet` now redirects to
  `https://numerco.com/dashboard` (current values only).
- The UHistory page loads its table client-side from a **public Parse Server backend**
  whose server URL and client keys are served in the page source (lines ~623-624):
  - **Endpoint:** `GET https://pg-app-yoa7d4wnnpyx68zgkxvc6d17cjk19s.scalabl.cloud/1/classes/UHistory`
  - **Headers (public client credentials embedded in the page):**
    `X-Parse-Application-Id: 7o6eTnJo7VQS4JcPeZiiF1BiflsKSur4YrrjzoC2`,
    `X-Parse-Javascript-Key: VxtEfDpOhx4fOBFO1ebD50wqpmULjpOh8Ln1idM6`
  - **Params:** `order=createdAt|-createdAt`, `limit` (≤1000), `skip`, `count=1`.
  - **Fields:** `Date` (`dd-MMM-yy` string), `SpotPrice` (USD/lb mid), `ImpliedPrice`
    (implied fund price, appears to be the Yellow Cake implied series), `createdAt`
    (~12:30 UTC daily).
- **Range obtained:** 4,687 rows, **2007-07-27 → 2026-07-17** (daily, business days).
- **Caveats:** this replicates exactly the read the public web page performs (keys are
  client-side by design, data is publicly displayed); still, it is an undocumented
  backend — cache results, poll gently (page itself refreshes every 10 min), and treat
  Numerco's terms as governing redistribution. Numerco is one of the four inputs to
  Sprott's composite benchmark, so as a proxy for "Sprott's spot price" it is Tier 3.
- **Files saved:** `numerco_uhistory_page.html`, `numerco_uhistory_skip{0,1000,2000,3000,4000}.json`.
- Failed variants: `https://numerco.com/UHistory/UHistory.csv` → 404 (referenced in page
  JS but not served); `/NSet/aCNSet.html`, `/NSet/CNSet.html` → 404.

---

## 4. Yellow Cake PLC — **periodic only, Tier 2 (low frequency)**

- **Homepage:** `https://www.yellowcakeplc.com/` — current spot price widget via
  `https://www.yellowcakeplc.com/api/spotUraniumPrice.php` (**WORKING** but returns an
  HTML snippet with *current* spot price, daily change, and "Implied Yellow Cake Uranium
  Price" only — **no history**).
- NAV per share and U3O8 holdings are published **quarterly** in Operating Update PDFs
  (e.g. `wp-content/uploads/2026/04/Yellow-Cake-Quarterly-Operating-Update-31-December-2025.pdf`)
  and in LSE RNS announcements (monthly-ish "Value of U3O8" statements) — PDF/press-release
  format, not machine-readable; would need PDF parsing (Tier 2 values, Tier 4 effort).
- Probed and **FAILED** (404): `api/navPerShare.php`, `api/nav.php`, `api/sharePrice.php`,
  `api/spotUraniumPriceHistory.php`, `api/history.php`, `api/data.php`.
- Robots.txt: fully permissive.
- **Files saved:** `yellowcake_homepage.html`, `yellowcake_api_spoturaniumprice.html`.
- Verdict: use only for cross-validation of holdings/NAV at quarter ends.

---

## 5. CME uranium futures (UX) — **BLOCKED**

- `https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/1327/FUT` →
  **HTTP 403**: "This IP address is blocked due to suspected web scraping activity …
  Use of scripts … is strictly prohibited by CME Group's website Data Terms of Use."
- CME explicitly prohibits scripted access in its Data Terms of Use — **do not retry
  with header spoofing**. Alternatives if futures settlements are needed: licensed
  vendors, or Nasdaq Data Link/CME DataMine paid products. Not pursued.

---

## 6. Summary matrix

| Quantity wanted | Best source | Frequency / range | Tier |
|---|---|---|---|
| NAV/unit (USD) daily | Sprott page inline `Net Asset Value` | daily, 2021-07-19 → present | 2 |
| Market price (USD, TSX U.U) daily | Sprott page inline `Share Price` | daily, 2021-07-19 → present | 2 |
| Premium/discount daily | Sprott page inline series | daily, 2021-07-19 → present | 2 |
| NAV/unit (CAD) | reconstruct USD NAV × BoC USDCAD; archived snapshots | daily | 4 |
| Units outstanding | Sprott API §1.2 (poll daily) + Wayback backfill | current + reconstructed | 2 fwd / 4 back |
| Total NAV, uranium market value | same as units outstanding; or lbs × spot | current + reconstructed | 2 fwd / 4 back |
| Lbs U3O8 held | Sprott page inline weekly chart (+ full-precision current value) | weekly, 2021-07-16 → present | 2 |
| Sprott composite spot price (levels) | not published; Numerco daily as proxy | daily, 2007-07-27 → present | 3 |
| Monthly spot / long-term U price | Cameco embedded table (UxC/TradeTech) | monthly, 1988-01 → present | 2 |
| Yellow Cake NAV/holdings | quarterly PDFs / RNS | quarterly | 2 (PDF) |
| CME UX futures settlements | blocked (403, ToU prohibits scraping) | — | — |
