import streamlit as st
import pdfplumber
import pandas as pd
import re
import datetime
from io import BytesIO

st.set_page_config(page_title="Bank Statement Tool", layout="wide")

# --- Parse a single transaction line ---
def parse_transaction_line(line, prev_balance):
    date_match = re.match(r'^(\d{2}-\d{2}-\d{2,4})', line)
    if not date_match:
        return None, prev_balance

    date_str = date_match.group(1)
    try:
        date_obj = datetime.datetime.strptime(date_str, "%d-%m-%y") if len(date_str.split('-')[2]) == 2 else datetime.datetime.strptime(date_str, "%d-%m-%Y")
        date = date_obj.strftime("%d-%m-%Y")
    except:
        return None, prev_balance

    rest = line[len(date_str):].strip()

    # Extract closing balance (e.g. 14,96,485.63Cr)
    balance_match = re.search(r'(\d[\d,]*\.\d{2})(Cr|Dr)?$', rest)
    if not balance_match:
        return None, prev_balance

    balance_amt = balance_match.group(1)
    balance_type = balance_match.group(2) or "Cr"
    balance_val = float(balance_amt.replace(",", ""))
    balance_val = balance_val if balance_type == "Cr" else -balance_val

    # Calculate deposit or withdrawal
    deposit = withdrawal = 0.0
    if prev_balance is not None:
        diff = balance_val - prev_balance
        if diff > 0:
            deposit = diff
        elif diff < 0:
            withdrawal = -diff

    # Remaining text is narration
    narration = rest[:balance_match.start()].strip()

    return {
        "Date": date,
        "Particulars": narration,
        "Deposit": round(deposit, 2),
        "Withdrawals": round(withdrawal, 2),
        "Closing Balance": f"{balance_amt}{balance_type}"
    }, balance_val

# --- Full PDF parsing with multi-line narration and page skipping ---
def extract_transactions(pdf_file):
    entries = []
    prev_balance = None
    narration_buffer = ""

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().split("\n")
            for line in lines:
                line = line.strip()

                # Skip footers/headers/empty
                if not line or "Account" in line or "Page" in line:
                    continue

                if re.match(r'^\d{2}-\d{2}-\d{2,4}', line):
                    # Attach narration buffer to previous entry
                    if narration_buffer and entries:
                        entries[-1]["Particulars"] += " " + narration_buffer.strip()
                        narration_buffer = ""

                    parsed, prev_balance = parse_transaction_line(line, prev_balance)
                    if parsed:
                        entries.append(parsed)
                else:
                    # Continuation of previous narration
                    narration_buffer += " " + line.strip()

    # Final buffer addition
    if narration_buffer and entries:
        entries[-1]["Particulars"] += " " + narration_buffer.strip()

    return entries

# --- Streamlit UI ---
st.title("📄 Bank Statement Tool")
st.markdown("Upload a **Bank of Baroda PDF** to extract transactions in table format.")

pdf_file = st.file_uploader("Upload PDF Statement", type=["pdf"])

if pdf_file:
    with st.spinner("Extracting transactions..."):
        data = extract_transactions(pdf_file)

    if data:
        df = pd.DataFrame(data)
        st.success(f"✅ Found {len(df)} transactions.")
        st.dataframe(df)

        output = BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)

        st.download_button(
            "📥 Download Excel",
            data=output,
            file_name="bank_statement.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("⚠️ No valid transactions found.")
