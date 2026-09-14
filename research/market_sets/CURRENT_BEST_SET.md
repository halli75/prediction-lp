# Current best market set

**Name:** `pool_ge_100`  
**Updated:** 2026-09-13T06:22:52Z  
**Strategy knobs:** pool150 champion held (`spread_frac=0.6676`, `size_mult=1.291`, `inv_soft=35`, `max_abs_inv=100`).  
**Universe:** all allowlisted markets with `daily_reward_pool >= 100` (50 names).  
**Eval apply:** `min_daily_reward_pool=100` + allowlist in `research/market_sets/pool_ge_100.json`.  
**strategy_current_best.py:** NOT overwritten (market-set win only).

## Window metrics vs pool150 gates

| Window | pool_ge_100 | pool150 gate | Delta | Max DD% | Soft-reject |
|--------|------------:|-------------:|------:|--------:|:-----------:|
| 12d sample | **+1673.11** | +1197.56 | **+475.55** | 1.28 | false |
| 30d | **+2734.01** | +2083.31 | **+650.70** | 1.22 | false |
| ~60d (54d present) | **+2604.43** | +1913.93 | **+690.50** | 3.03 | false |

- 30d reward +1547.08 / trading +1186.93 / fills 293
- 60d reward +1596.80 / trading +1007.63 / fills 1255

## Finding

On the defensive pool150 quoting knobs, **widening the pool floor from 150 → 100** added profitable names without the inventory bleed seen at pool>=50 (sample +990, worse than pool150). Tight top-N / seed Fed-Iran / diverse-theme sets all *underperformed* the pool-threshold universes on the 12d sample — quality still matters, but the 100–149 band is net-positive here.

## Allowlist (50)

- `0xa3b36b2d6104d34af4e6c6215fc818e43352e78a748fbfb0b85e3a35f71dec9a`  pool=1000  vol=37012872  fed  — Will there be no change in Fed interest rates after the September 2026 meeting?
- `0x876506d8b2bd7a0d3fa4fe18c024eee6e1dd81ee24c26795dadd6cfe4a7b5d0d`  pool=1000  vol=28676744  fed  — Will the Fed increase interest rates by 25 bps after the September 2026 meeting?
- `0x58d5cc2bf06a3289b127049239aee051f3b941f219efebbca02d3f50f0eb2a64`  pool=1000  vol=902474  sweden_pm  — Will Magdalena Andersson be the next Prime Minister of Sweden?
- `0x8a42bb4cb9b9f157b539611f6a8c122388f652570cfc3c07d538e7df2bb78894`  pool=1000  vol=582413  sweden_pm  — Will Ulf Kristersson be the next Prime Minister of Sweden?
- `0xa3d50cf0138c0faad988d80e35036aab97ae6d5627f539ce3ce531b555acc209`  pool=514  vol=79259  sweden_parliament  — Will the Moderate Party (M) win the second most seats in the 2026 Swedish parliamentary election?
- `0x9cb23d04b2ded06147482076688b69b487a8d982c63ebdda2ab3678cf27cf390`  pool=500  vol=15226953  us_crypto_law  — Clarity Act (H.R.3633) signed into law in 2026?
- `0x9e2966ab58d8cd6efaccfd92b2d7c518ff6c4318e8bcd3032fef68c8254d102a`  pool=486  vol=116395  sweden_parliament  — Will the Sweden Democrats (SD) win the second most seats in the 2026 Swedish parliamentary election?
- `0x5db999fad322cea2914535aae5517060c3f80ad6d8c0231cde2124a434d16846`  pool=400  vol=65865669  iran_geo  — Will the U.S. invade Iran before 2027?
- `0x95fc6a4ed7f6856d26aa7f21b9f902d05c9cf76b616fd3463de4d147f7a9126b`  pool=400  vol=2916887  iran_geo  — Bab el-Mandeb Strait effectively closed by September 30?
- `0x5c79dfde05559b79a9cb9f7c4187e4d49632dd042572ae676952f812732591cc`  pool=300  vol=11532056  iran_geo  — Strait of Hormuz traffic returns to normal by December 31?
- `0xdbe93b5a701f36076a560fa4b9ba59e365a6e8e2ea6a83764640010657277ca4`  pool=298  vol=1944685  israel  — Will Gadi Eizenkot be the next Prime Minister of Israel?
- `0x1a01bf78f56a507fcb666d564d8c8b91b0750679163ed6e96746102c9b7d285d`  pool=253  vol=10529297  brazil  — Will Flávio Bolsonaro win the 2026 Brazilian presidential election?
- `0x12aa13b3da17ceae1b0a59b5d5b77121e91bb79b4bb0b52bf6543ed3f8d0953b`  pool=250  vol=374608  fed  — Will the Fed increase interest rates by 25 bps after the October 2026 meeting?
- `0xdf9bf27ee5757c55b44b8b9826ddc9ec3a8809aa3278634c45edbb7fc8f1a3e3`  pool=250  vol=301908  fed  — Will there be no change in Fed interest rates after the October 2026 meeting?
- `0xdf8e2dc5860027decbe6164555c3c1c9645c3bd33e16b9dc57ca87125047d4a8`  pool=247  vol=10901315  brazil  — Will Luiz Inácio Lula da Silva win the 2026 Brazilian presidential election?
- `0x8126317d621047fb13d508a2651eecc8d38305904671822a62309c5aabd353aa`  pool=242  vol=2413173  france  — Will Marine Le Pen win the 2027 French presidential election?
- `0xdf0ab07edc24b3da2363536f47c7929cedb468c29425e7efbb69816e921b5a35`  pool=214  vol=44384  esports_lec  — Will Caliste Win the LEC 2026 Summer Split MVP?
- `0x377e7fe65cf198a7fc4fdae3f2136b74729279267858daaf96718b23bc2a5607`  pool=200  vol=4466297  iran_geo  — Iran leadership change by December 31?
- `0xcd2640464754b9a894ffec98ac11554fdd507ea89ca01237eabb3a6de4a606e6`  pool=200  vol=4298338  f1  — Will Kimi Antonelli be the 2026 F1 Drivers' Champion?
- `0xd8659b58a90d0d69fb1170f25b2b896871a1328115fd11c6f4cfe2b01a2a8ba0`  pool=200  vol=702891  iran_geo  — Bab el-Mandeb Strait effectively closed by December 31?
- `0xc4b07998e8f9bf6b95f079d6dc0529f3c6f59698d4e168817ad5f99304de6c57`  pool=200  vol=652316  movies  — Will Spider-Man: Brand New Day be the top grossing movie of 2026?
- `0x0c9b3726e283b1bf76bb7465a3f7a08ef2880bf850fddccd068f4a7572da88eb`  pool=200  vol=28886  emmys  — Will Jean Smart – “Hacks” win Emmys 2026: Outstanding lead actress in a comedy series?
- `0x8096b13bf1eaaae4344eadcf766b25ddffbb4a94deb233c54fef6cb64c39a2de`  pool=200  vol=19633  emmys  — Will “DTF St. Louis” win Emmys 2026: Outstanding limited or anthology series?
- `0x46f2f457e14ee9021ebd0ef4c27eacd98fdceaf7f2938b484e2551e9e3275ae8`  pool=186  vol=1588033  france  — Will Édouard Philippe win the 2027 French presidential election?
- `0x7586a96520578acaaaa4ea84a2582f197f84255da1f3392a7aa300386c187b37`  pool=172  vol=3812430  israel  — Will Benjamin Netanyahu be the next Prime Minister of Israel?
- `0x607f376c8a27f05f8f93d61204683540db6e7d6817b5acebeb0bc3d72b48ab1c`  pool=165  vol=55978  emmys  — Will “The Late Show With Stephen Colbert” win Emmys 2026: Outstanding variety series?
- `0x059db22dae2d735516017d47d1def0ea43e5d7221259c3aaa60c090d32566d4e`  pool=150  vol=770122  fed  — Fed Rate Hike by October 2026 Meeting?
- `0x07414b5c367c107a563491fe8b354abd5b07f099fce3b25cd57e80110ce780ff`  pool=146  vol=123148  fifa  — Will another city host the final of the 2030 FIFA World Cup?
- `0x502a94e5c525766d5ee7f16c6568131ba1b2cbadb69c703af05a6ef00336ed64`  pool=144  vol=9862627  russia  — Will United Russia (ER) gain the most seats in the next Russian parliamentary election?
- `0xccd5e0951f88111c82a1827bf4574eaaa186dd12dfa05001733873c1d5a939f1`  pool=138  vol=30309  fifa  — Will Madrid host the final of the 2030 FIFA World Cup?
- `0x12dc2b61723b2a54fc1947a307389b5f32038e7a29a0e936ad1fe410b969d06a`  pool=131  vol=4134093  ballon_dor  — Will Harry Kane win the 2026 Ballon d'Or?
- `0x939abe4a38f670b916138202bc9045767299998dbb3c3fb389146fb17f24a477`  pool=128  vol=27981  sweden_parliament  — Will the Sweden Democrats (SD) win the third most seats in the 2026 Swedish parliamentary election?
- `0xc46b099054624fe3cc7fa4d0ddcea4dd292ab5c647ee459da9937a75a01094cd`  pool=127  vol=28542  emmys  — Will Katherine LaNasa – “The Pitt” win Emmys 2026: Outstanding supporting actress in a drama series?
- `0x74c00fc8e90a6a0a672bd0561679bb4ee511f03880308f9f6dac6a8dd1dcf41c`  pool=124  vol=14191  emmys  — Will Rhea Seehorn – “Pluribus” win Emmys 2026: Outstanding lead actress in a drama series?
- `0xbbb881b0ecfbfbd6bdc5fab54fc82871a2daf99417e51106f58ad1abacdbb65b`  pool=122  vol=47375  sweden_parliament  — Will the Moderate Party (M) win the third most seats in the 2026 Swedish parliamentary election?
- `0x9013401c7b896520f5f6b4c3dd698ccb94cce6a5d53f44c6764ad192c7d12387`  pool=117  vol=21935  japan_macro  — Will Japan's core-core CPI increase by between 2.0 and 2.4% in 2026?
- `0xd4e77ba6f29fc093509d24f508631abd445ecf506bbdc9c4c80e60256a318527`  pool=116  vol=8289366  fed  — Will no Fed rate cuts happen in 2026?
- `0xa273dc84e8f52c912473b122429a93f2b00fc05d8ca667bbc8012fa928456e31`  pool=111  vol=14123  emmys  — Will Oscar Isaac – “Beef” win Emmys 2026: Outstanding lead actor in a limited or anthology series or movie?
- `0x9b9a651f1a92a9cc2367bd175ce000891c8022b220d95f8fb84e465dd1d6710d`  pool=110  vol=23504  emmys  — Will Kate O’Flynn – “Widow’s Bay” win Emmys 2026: Outstanding supporting actress in a comedy series?
- `0xbca22b54ac820532232309109c1b980ec12e626f31c452b02b56f5a2d67a4a13`  pool=110  vol=21595  emmys  — Will Stephen Root – “Widow’s Bay” win Emmys 2026: Outstanding supporting actor in a comedy series?
- `0xc9615bb82d6535d630ff98e8094060bc767d8b9446516e98f84d2001a35e50e7`  pool=106  vol=2943551  russia  — Will New People (NL) gain the most seats in the next Russian parliamentary election?
- `0x5fa0025c3a11f2fb0a00a3cbdeb6a33339e01d71171e4150ff150946285c6eb1`  pool=105  vol=44682  emmys  — Will “Widow’s Bay” win Emmys 2026: Outstanding comedy series?
- `0x07d6d1ac69e705071cfaa10ab950f8231dc3de7cb03638cbabb7fbf481806797`  pool=102  vol=59370  mlb  — Will Los Angeles Dodgers win the 2026 National League Championship Series?
- `0xb8b5ba728577c752f2147f8a15a1710b39c70bafe5fa9536159725c7f09779c4`  pool=102  vol=41580  chess  — Will Gukesh Dommaraju win the 2026 World Chess Championship?
- `0x747dc809fb79e1b05be09c42d6179459a58de2ef3e40f02484a4e1260f741f75`  pool=100  vol=38349306  aliens  — Will the US confirm that aliens exist before 2027?
- `0x094772b3529f455e881a4483eaf1c24266384f55e97c23f24f638f5726ba9920`  pool=100  vol=1044739  iran_geo  — Iran leadership change by September 30?
- `0x8062cf78d93f9202f4c0a1018d141f4af35d486a368f07e65265f27d48b4e040`  pool=100  vol=803084  tech_ipo  — Will Anthropic IPO by October 31, 2026?
- `0xf1fa8b7530ceec866131fbc6681209e39d6b448bdca563b46d936cc792e6cf7a`  pool=100  vol=76720  tech_ipo  — Will OpenAI launch a new consumer hardware product by October 31, 2026?
- `0xa425a9988c6d6f6991cbfeb7d3d23596febbc4b8e538cd8232e80a7582b40d69`  pool=100  vol=36865  emmys  — Will HBO Max win the most Emmys?
- `0x0a9e4eb4accd73a406f08d7a5174e629b2fc0e0aa240f73c2ae3f2d0c16fc9f6`  pool=100  vol=36460  emmys  — Will Apple TV win the most Emmys?

File: `research/market_sets/pool_ge_100.json`


## Wave2 refine (floors / combos) — 2026-09-13T06:30:04Z

Sample-only scan around pool100. **No challenger beat sample gate 1673.11**; champion unchanged. No 30d/60d spent.

| Rank | Set | n | Sample | Δ vs gate | DD% |
|-----:|-----|--:|-------:|----------:|----:|
| 1 | **pool_ge_100** (champ) | 50 | **+1673.11** | 0 | 1.28 |
| 2 | pool_ge_110 | 40 | +1433.78 | −239 | 1.32 |
| 3 | pool_ge_100_ex_emmys | 39 | +1337.65 | −335 | 1.28 |
| 4 | pool_ge_120 | 35 | +1320.88 | −352 | 1.33 |
| 5 | pool_ge_125 | 33 | +1300.63 | −372 | 1.11 |
| 6 | pool_ge_140 | 29 | +1215.63 | −457 | 1.12 |
| 7 | pool_ge_150 | 27 | +1197.56 | −476 | 1.18 |
| 8 | pool_ge_130 | 31 | +1196.49 | −477 | 1.12 |
| 9 | pool_ge_90 | 54 | +1065.90 | −607 | 3.40 |
| 10 | pool_ge_80 | 65 | +989.61 | −684 | 3.51 |
| 11 | pool_100_to_199 | 27 | +586.15 | −1087 | 0.51 |

**Takeaway:** floor 100 is a local optimum on this sample. Tighter floors lose the 100–109 band; looser floors (90/80) bleed like pool50; dropping Emmys or megapools both destroy PnL. Artifact: `results/market_combo_leaderboard_wave2.json`.
