[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/slavaolena/gta6-trophy-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/slavaolena/gta6-trophy-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

# GTA VI Trophy Rarity Forecast

Entry untuk kompetisi make.fun gta6-trophy-rarity-forecast-01. Script `main.py` membaca case file JSON dari direktori input, menghitung forecast kuantil kelimpahan trophy GTA VI menggunakan weighted history dari 4 pembacaan terakhir dengan penekanan eksponensial pada data terbaru, lalu menghasilkan output JSON berisi 55 array masing-masing 5 nilai quantiles (0.05, 0.25, 0.5, 0.75, 0.95) yang tidak menurun dan dibatasi [0,100].

## Run

```bash
python3 main.py
```

Environment variables:
- `MAKEFUN_INPUT_DIR` (default: `input`) — direktori berisi file `.in`
- `MAKEFUN_OUTPUT_DIR` (default: `out`) — direktori output file `.out`

Link: https://make.fun/bounty/gta6-trophy-rarity-forecast-01
