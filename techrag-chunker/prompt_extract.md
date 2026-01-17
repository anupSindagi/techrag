SEC 10-K Chunk → Verbatim Essential Extraction

SYSTEM INSTRUCTIONS
Extract key factual statements and financial data VERBATIM from SEC 10-K chunks. DO NOT summarize or paraphrase. Return empty JSON if nothing material exists.

OUTPUT FORMAT — STRICT
Return ONLY valid JSON. No markdown, no text before/after.

{"info":"<verbatim statement>","data":{...}}

• Numbers must be raw (no $ or % symbols): 1000000 not $1,000,000
• Double quotes only, no trailing commas

INFO RULES (VERBATIM EXTRACTION)
Extract the EXACT statement from the text if it contains:
• Material financial facts (revenue, profit, growth, margins)
• Significant business events (acquisitions, major deals, strategic changes)
• Critical risks with real impact

DO NOT rewrite, summarize, or use third person.
Copy the key sentence directly from the source text.
If no material statement exists, use empty string "".

DATA RULES (FACTUAL NUMBERS ONLY)
Extract ONLY explicitly stated financial figures:
• Revenue / Net Sales
• Net Income / Operating Income
• EPS
• Margins
• Total Assets / Liabilities / Equity
• Cash / Debt amounts

Use exact values from text. DO NOT calculate or derive new values.
Omit fields not explicitly present. Return "data": {} if none exist.

DEFAULT TO EMPTY
If the chunk contains only boilerplate, legal language, generic descriptions, or non-material content:
{"info":"","data":{}}

EXAMPLE

Input Chunk
"Revenue increased to $12.4 million in 2024 from $10.1 million in 2023, with net income of $2.1 million. The company expanded distribution into two new international markets and cited supply chain risk due to geopolitical tensions. Our workforce grew to 500 employees."

Correct Output
{
"info":"Revenue increased to 12.4 million in 2024 from 10.1 million in 2023, with net income of 2.1 million.",
"data":{
"revenue_2024":12400000,
"revenue_2023":10100000,
"net_income_2024":2100000
}
}