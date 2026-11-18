# nikkei-market

「日経モーニング10」用の米国市場センチメント指標を毎朝自動取得するリポジトリです。

- `scripts/fetch_market.py`：VIX（Cboe／FRED）、CNN Fear & Greed Index、Cboe Put/Call Ratio を取得
- `.github/workflows/fetch-market.yml`：毎日 6:15 JST に GitHub Actions で実行
- `data/market.json`：最新値（毎朝のタスクが読み込む）
- `data/history.csv`：全日分の蓄積
