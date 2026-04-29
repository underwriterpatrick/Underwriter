import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Assisted Underwriting Tool", layout="wide")

st.title("Assisted Underwriting Tool")
st.caption("Paste comps, adjust assumptions, and generate ARV / As-Is / pro statement.")

# -----------------------------
# Helpers
# -----------------------------
def money(x):
    return f"${x:,.0f}"

def extract_price(text):
    match = re.search(r"\$?\s?([\d,]{3,})", text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None

def extract_beds(text):
    match = re.search(r"(\d+)\s*(bed|beds|br|bdrm|bedroom)", text.lower())
    return int(match.group(1)) if match else None

def extract_baths(text):
    match = re.search(r"(\d+(\.\d+)?)\s*(bath|baths|ba|fb)", text.lower())
    return float(match.group(1)) if match else None

def detect_condition(text):
    t = text.lower()
    if any(w in t for w in ["fully renovated", "gut", "brand new", "turnkey"]):
        return "Renovated"
    if any(w in t for w in ["updated", "modern", "move-in", "stainless"]):
        return "Updated"
    if any(w in t for w in ["dated", "as-is", "needs work", "original"]):
        return "Dated"
    return "Average"

def parse_comps(raw):
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        price = extract_price(line)
        if not price:
            continue

        rows.append({
            "Address / Raw Comp": line,
            "Sale Price": price,
            "Beds": extract_beds(line),
            "Baths": extract_baths(line),
            "Condition": detect_condition(line),
            "Weight": 1.0
        })

    return pd.DataFrame(rows)

def condition_adjustment(condition):
    return {
        "Renovated": 0.00,
        "Updated": -0.05,
        "Average": -0.10,
        "Dated": -0.15,
        "Heavy Rehab": -0.25
    }.get(condition, -0.10)

def location_adjustment(location):
    return {
        "Superior": 0.05,
        "Similar": 0.00,
        "Inferior": -0.05,
        "Busy Road / Commercial Influence": -0.07,
        "Near Train / Transit Premium": 0.05
    }.get(location, 0.00)

def property_type_adjustment(prop_type):
    return {
        "Detached SFR": 0.00,
        "Attached / Rowhouse": -0.07,
        "Condo / Townhouse": -0.05,
        "2-4 Family": 0.00,
        "Apartment / 5+ Units": 0.00
    }.get(prop_type, 0.00)

# -----------------------------
# Sidebar inputs
# -----------------------------
st.sidebar.header("Subject Inputs")

subject_address = st.sidebar.text_input("Subject Address", "")
property_type = st.sidebar.selectbox(
    "Property Type",
    ["Detached SFR", "Attached / Rowhouse", "Condo / Townhouse", "2-4 Family", "Apartment / 5+ Units"]
)

subject_beds = st.sidebar.number_input("Beds", min_value=0.0, step=0.5, value=3.0)
subject_baths = st.sidebar.number_input("Baths", min_value=0.0, step=0.5, value=2.0)

condition = st.sidebar.selectbox(
    "Subject Condition",
    ["Renovated", "Updated", "Average", "Dated", "Heavy Rehab"]
)

location_factor = st.sidebar.selectbox(
    "Location Factor",
    ["Similar", "Superior", "Inferior", "Busy Road / Commercial Influence", "Near Train / Transit Premium"]
)

parking = st.sidebar.selectbox("Parking", ["Similar", "No Parking", "Garage / Driveway"])
basement = st.sidebar.selectbox("Basement", ["None / Similar", "Finished Basement", "Unfinished Basement"])

manual_arv = st.sidebar.number_input("Optional Manual ARV Override", min_value=0, step=5000, value=0)
manual_as_is = st.sidebar.number_input("Optional Manual As-Is Override", min_value=0, step=5000, value=0)

# -----------------------------
# Main input
# -----------------------------
raw_comps = st.text_area(
    "Paste comps here",
    height=220,
    placeholder="""Example:
79 Virginia Ave $595,000 4 beds 3 baths renovated finished basement
88 Harmon St $450,000 4 beds 2.5 baths average condition
247 Clerk St $540,000 3 beds 1 bath updated
"""
)

if st.button("Run Underwriting"):
    df = parse_comps(raw_comps)

    if df.empty:
        st.error("No comps detected. Make sure each comp line includes a price like $450,000.")
        st.stop()

    st.subheader("Parsed Comps")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Sale Price": st.column_config.NumberColumn(format="$%d"),
            "Weight": st.column_config.NumberColumn(min_value=0.0, max_value=5.0, step=0.25)
        }
    )

    valid = edited_df[edited_df["Weight"] > 0].copy()
    weighted_avg = (valid["Sale Price"] * valid["Weight"]).sum() / valid["Weight"].sum()

    # ARV from comps
    calculated_arv = weighted_avg

    # Adjustments for as-is
    adj = 0
    adj += condition_adjustment(condition)
    adj += location_adjustment(location_factor)
    adj += property_type_adjustment(property_type)

    if parking == "No Parking":
        adj -= 0.03
    elif parking == "Garage / Driveway":
        adj += 0.03

    if basement == "Finished Basement":
        adj += 0.04
    elif basement == "Unfinished Basement":
        adj += 0.01

    calculated_as_is = calculated_arv * (1 + adj)

    final_arv = manual_arv if manual_arv > 0 else calculated_arv
    final_as_is = manual_as_is if manual_as_is > 0 else calculated_as_is

    arv_low = final_arv * 0.97
    arv_high = final_arv * 1.03
    as_is_low = final_as_is * 0.97
    as_is_high = final_as_is * 1.03

    # -----------------------------
    # Results
    # -----------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Final ARV", money(final_arv))
        st.write(f"Range: {money(arv_low)} – {money(arv_high)}")

    with col2:
        st.metric("Final As-Is", money(final_as_is))
        st.write(f"Range: {money(as_is_low)} – {money(as_is_high)}")

    with col3:
        spread = final_arv - final_as_is
        st.metric("Spread", money(spread))
        st.write(f"Spread %: {(spread / final_arv) * 100:.1f}%")

    st.subheader("Adjustment Summary")
    adjustment_rows = [
        ["Condition", condition, f"{condition_adjustment(condition)*100:.1f}%"],
        ["Location", location_factor, f"{location_adjustment(location_factor)*100:.1f}%"],
        ["Property Type", property_type, f"{property_type_adjustment(property_type)*100:.1f}%"],
        ["Parking", parking, "-3.0%" if parking == "No Parking" else "3.0%" if parking == "Garage / Driveway" else "0.0%"],
        ["Basement", basement, "4.0%" if basement == "Finished Basement" else "1.0%" if basement == "Unfinished Basement" else "0.0%"],
    ]
    st.table(pd.DataFrame(adjustment_rows, columns=["Category", "Input", "Adjustment"]))

    # -----------------------------
    # Pro Statement
    # -----------------------------
    top_comps = valid.sort_values("Weight", ascending=False).head(3)
    comp_names = "; ".join(
        [f"{row['Address / Raw Comp']} ({money(row['Sale Price'])})" for _, row in top_comps.iterrows()]
    )

    subject_label = subject_address if subject_address else "the subject property"

    statement = f"""
**Professional Valuation Statement**

Based on the comparable sales provided, {subject_label} supports an estimated **ARV of {money(final_arv)}** and an estimated **as-is value of {money(final_as_is)}**.

The valuation is primarily supported by the most relevant weighted comparable sales, including {comp_names}. Adjustments were applied for subject condition, property type, location influence, parking, and basement utility.

The subject is classified as **{property_type}** with **{condition.lower()}** condition. Location was treated as **{location_factor.lower()}**, and the final reconciliation reflects market-supported qualitative adjustments rather than a simple average of sales. This approach is intended to be consistent with USPAP / IVS-style valuation principles, including relevant comparable selection, adjustment reasoning, and final value reconciliation.
"""

    st.subheader("Pro Statement")
    st.markdown(statement)

    st.download_button(
        "Download Statement",
        data=statement,
        file_name="valuation_statement.txt",
        mime="text/plain"
    )
