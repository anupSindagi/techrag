import json
from pipeline import process_10k


def main():
    # Load S&P 500 companies
    with open("sp500_tech.json", "r", encoding="utf-8") as f:
        companies = json.load(f)
    
    print(f"Found {len(companies)} companies to process\n")
    
    for i, company in enumerate(companies):
        symbol = company["Symbol"]
        name = company["Security"]
        cik = company["CIK"]
        
        print(f"\n[{i + 1}/{len(companies)}] {symbol} - {name}")
        
        try:
            process_10k(name, symbol, cik)
        except Exception as e:
            print(f"  Error processing {symbol}: {e}")
            continue
    
    print("\n" + "=" * 50)
    print("All companies processed!")


if __name__ == "__main__":
    main()
