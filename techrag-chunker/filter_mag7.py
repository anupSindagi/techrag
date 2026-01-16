import csv
import json

# Magnificent 7 tickers
MAG7_TICKERS = ["GOOGL", "AMZN", "AAPL", "META", "MSFT", "NVDA", "TSLA"]

companies = []

with open("sp500.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["Symbol"] in MAG7_TICKERS:
            companies.append({
                "Symbol": row["Symbol"],
                "Security": row["Security"],
                "GICS Sector": row["GICS Sector"],
                "GICS Sub-Industry": row["GICS Sub-Industry"],
                "Headquarters Location": row["Headquarters Location"],
                "Date added": row["Date added"],
                "CIK": row["CIK"],
                "Founded": row["Founded"]
            })

with open("sp500_tech.json", "w") as f:
    json.dump(companies, f, indent=2)

print(f"Extracted {len(companies)} companies to sp500_tech.json")
