# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from collections import Counter
from html import escape  # for safe HTML receipt display

st.set_page_config(page_title="Hotdog Stand POS", layout="wide")

# CSS so only the receipt prints when using the browser's print dialog
PRINT_CSS = """
<style>
@media print {
  body * {
    visibility: hidden;
  }
  #receipt-block, #receipt-block * {
    visibility: visible;
  }
  #receipt-block {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    padding: 16px;
  }
}
</style>
"""
st.markdown(PRINT_CSS, unsafe_allow_html=True)

# ---------- Config ----------
DEFAULT_MENU = [
    {"item": "Hotdog", "price": 3.50},
    {"item": "Cheese Dog", "price": 4.00},
    {"item": "Chili Dog", "price": 4.50},
    {"item": "Sausage", "price": 5.00},
    {"item": "Soda", "price": 1.50},
    {"item": "Water", "price": 1.00},
    {"item": "Chips", "price": 1.25},
]

MENU_CSV = Path("menu.csv")
SALES_XLSX = Path("sales.xlsx")
SALES_SHEET = "Sales"
LOGO_FILE = Path("logo-bobs-dogz.png")

# ---------- Helpers ----------
def load_menu():
    if MENU_CSV.exists():
        try:
            df = pd.read_csv(MENU_CSV)
            if "item" not in df.columns or "price" not in df.columns:
                return DEFAULT_MENU.copy()
            return df.to_dict("records")
        except Exception:
            return DEFAULT_MENU.copy()
    else:
        return DEFAULT_MENU.copy()

def save_menu(menu_list):
    pd.DataFrame(menu_list).to_csv(MENU_CSV, index=False)

def ensure_sales_file_exists():
    if not SALES_XLSX.exists():
        cols = [
            "Timestamp",
            "Date",
            "Items",
            "Subtotal",
            "Discount",
            "Tax",
            "Tip",
            "Card Fee",
            "Total",
            "Payment Method",
            "Notes",
            "Cash Received",
            "Change",
        ]
        pd.DataFrame(columns=cols).to_excel(
            SALES_XLSX, sheet_name=SALES_SHEET, index=False
        )

def append_sale_to_excel(record: dict):
    ensure_sales_file_exists()
    try:
        existing = pd.read_excel(SALES_XLSX, sheet_name=SALES_SHEET)
    except Exception:
        existing = pd.DataFrame()
    new_row = pd.DataFrame([record])
    out = pd.concat([existing, new_row], ignore_index=True)
    with pd.ExcelWriter(SALES_XLSX, engine="openpyxl", mode="w") as writer:
        out.to_excel(writer, sheet_name=SALES_SHEET, index=False)

def remove_last_sale():
    if not SALES_XLSX.exists():
        return False
    try:
        df = pd.read_excel(SALES_XLSX, sheet_name=SALES_SHEET)
    except Exception:
        return False
    if df.empty:
        return False
    df = df.iloc[:-1]  # drop last row
    with pd.ExcelWriter(SALES_XLSX, engine="openpyxl", mode="w") as writer:
        df.to_excel(writer, sheet_name=SALES_SHEET, index=False)
    return True

def safe_read_sales():
    if not SALES_XLSX.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(SALES_XLSX, sheet_name=SALES_SHEET)
    except Exception:
        try:
            return pd.read_excel(SALES_XLSX)
        except Exception:
            return pd.DataFrame()

def cart_subtotal(cart):
    return sum(row["qty"] * row["price"] for row in cart)

def format_items_string(cart):
    return "; ".join(
        [
            f'{row["qty"]}x {row["item"]} @ {row["price"]:.2f}'
            for row in cart
        ]
    )

def build_receipt_text(record: dict) -> str:
    lines = []
    lines.append("Bob's DOGZ Receipt")
    lines.append("-" * 24)
    lines.append(f"Date: {record['Date']}")
    lines.append(f"Time: {record['Timestamp'].split(' ')[1]}")
    lines.append(f"Payment: {record['Payment Method']}")
    lines.append("")
    lines.append("Items:")
    for part in str(record["Items"]).split(";"):
        part = part.strip()
        if part:
            lines.append(f"  - {part}")
    lines.append("")
    lines.append(f"Subtotal: ${record['Subtotal']:.2f}")
    lines.append(f"Discount: ${record['Discount']:.2f}")
    lines.append(f"Tax: ${record['Tax']:.2f}")
    lines.append(f"Tip: ${record['Tip']:.2f}")
    lines.append(f"Card Fee: ${record['Card Fee']:.2f}")
    lines.append(f"TOTAL: ${record['Total']:.2f}")
    lines.append("")
    lines.append(f"Cash Received: ${record['Cash Received']:.2f}")
    lines.append(f"Change: ${record['Change']:.2f}")
    if record["Notes"]:
        lines.append("")
        lines.append(f"Notes: {record['Notes']}")
    return "\n".join(lines)

def parse_item_counts(df: pd.DataFrame) -> Counter:
    counts = Counter()
    if "Items" not in df.columns:
        return counts
    for items in df["Items"].dropna():
        for part in str(items).split(";"):
            part = part.strip()
            if not part:
                continue
            # Expect "2x Hotdog @ 3.50"
            try:
                qty_str, rest = part.split("x", 1)
                qty = int(qty_str.strip())
            except Exception:
                continue
            name_part = rest.split("@")[0].strip()
            item_name = name_part
            counts[item_name] += qty
    return counts

# ---------- Session state ----------
if "cart" not in st.session_state:
    st.session_state.cart = []

if "tax_rate" not in st.session_state:
    st.session_state.tax_rate = 0.0

if "card_fee" not in st.session_state:
    st.session_state.card_fee = 3.0  # default 3%

# Default payment method for new sales
if "default_payment" not in st.session_state:
    st.session_state.default_payment = "Cash"

# Current sale's payment method
if "payment" not in st.session_state:
    st.session_state.payment = st.session_state.default_payment

if "clear_note" not in st.session_state:
    st.session_state.clear_note = False

if "clear_cash" not in st.session_state:
    st.session_state.clear_cash = False

if "confirm_undo" not in st.session_state:
    st.session_state.confirm_undo = False

# last receipt text
if "last_receipt" not in st.session_state:
    st.session_state.last_receipt = ""

# ---------- Load menu ----------
MENU = load_menu()

# ---------- Sidebar ----------
st.sidebar.header("Menu & Settings")

with st.sidebar.expander("Edit Menu (change prices, add/remove items)", expanded=False):
    edited_menu = []
    for idx, entry in enumerate(MENU):
        cols = st.columns([6, 4])
        name = cols[0].text_input(
            f"Item name #{idx+1}",
            value=entry["item"],
            key=f"menu_name_{idx}",
        )
        price = cols[1].number_input(
            f"Price #{idx+1} ($)",
            value=float(entry["price"]),
            step=0.25,
            format="%.2f",
            key=f"menu_price_{idx}",
        )
        edited_menu.append({"item": name.strip(), "price": float(price)})

    st.markdown("---")
    new_name = st.text_input("New item name", value="", key="new_item_name")
    new_price = st.number_input(
        "New item price ($)",
        min_value=0.0,
        value=0.0,
        step=0.25,
        format="%.2f",
        key="new_item_price",
    )
    if st.button("Add Item"):
        if new_name.strip():
            edited_menu.append(
                {"item": new_name.strip(), "price": float(new_price)}
            )
            save_menu(edited_menu)
            st.rerun()

    if st.button("Save Menu"):
        cleaned = [e for e in edited_menu if e["item"]]
        save_menu(cleaned)
        st.success("Menu saved")
        st.rerun()

    if st.button("Reset to Default Menu"):
        save_menu(DEFAULT_MENU.copy())
        st.success("Menu reset to defaults")
        st.rerun()

st.sidebar.divider()
st.session_state.tax_rate = st.sidebar.number_input(
    "Sales Tax Rate (%)",
    min_value=0.0,
    max_value=30.0,
    step=0.25,
    value=st.session_state.tax_rate,
)
st.session_state.card_fee = st.sidebar.number_input(
    "Card Fee (%)",
    min_value=0.0,
    max_value=10.0,
    step=0.25,
    value=st.session_state.card_fee,
)

# Default payment for new sale (widget owns st.session_state.default_payment)
_ = st.sidebar.selectbox(
    "Default Payment Method (for new sale)",
    ["Cash", "Card", "Other"],
    index=["Cash", "Card", "Other"].index(
        st.session_state.default_payment
    ),
    key="default_payment",
)

if st.sidebar.button("➕ New Sale", type="primary"):
    st.session_state.cart = []
    st.session_state.clear_note = True
    st.session_state.clear_cash = True
    st.session_state.payment = st.session_state.default_payment
    st.rerun()

# Two-step undo confirmation
if not st.session_state.confirm_undo:
    if st.sidebar.button("↩️ Undo Last Sale", type="secondary", key="undo_btn"):
        st.session_state.confirm_undo = True
        st.rerun()
else:
    st.sidebar.warning("Are you sure you want to remove the last sale?")
    c1, c2 = st.sidebar.columns(2)
    if c1.button("Confirm", key="confirm_undo_btn"):
        if remove_last_sale():
            st.sidebar.success("Last sale removed")
        else:
            st.sidebar.warning("No sales to undo")
        st.session_state.confirm_undo = False
        st.rerun()
    if c2.button("Cancel", key="cancel_undo_btn"):
        st.session_state.confirm_undo = False
        st.rerun()

# ---------- Main ----------
# Optional logo
header_cols = st.columns([1, 3])
with header_cols[0]:
    if LOGO_FILE.exists():
        st.image(str(LOGO_FILE), use_column_width=True)
with header_cols[1]:
    st.title("🌭 Hotdog Stand POS")

# Convenience for card fee rate
card_fee_rate = st.session_state.card_fee / 100.0

# Item buttons
st.subheader("Add Items")
cols_per_row = 3
cols = st.columns(cols_per_row)
for i, entry in enumerate(MENU):
    base_price = float(entry["price"])
    card_price = base_price * (1 + card_fee_rate)
    label = (
        f'{entry["item"]} — '
        f"${base_price:.2f} cash / ${card_price:.2f} card"
    )
    col = cols[i % cols_per_row]
    if col.button(label, key=f"add_{i}", use_container_width=True):
        found = False
        for c in st.session_state.cart:
            if (
                c["item"] == entry["item"]
                and abs(c["price"] - base_price) < 1e-9
            ):
                c["qty"] += 1
                found = True
                break
        if not found:
            st.session_state.cart.append(
                {"item": entry["item"], "price": base_price, "qty": 1}
            )
        st.rerun()

st.divider()

# Cart
st.subheader("Cart")
if not st.session_state.cart:
    st.info("Cart is empty.")
else:
    cart_cols = st.columns([5, 3, 3, 2, 2])
    cart_cols[0].markdown("**Item**")
    cart_cols[1].markdown("**Price (cash / card)**")
    cart_cols[2].markdown("**Qty**")
    cart_cols[3].markdown("**Line Total (cash)**")
    cart_cols[4].markdown("**Actions**")

    remove_indices = []
    for idx, line in enumerate(st.session_state.cart):
        row = st.columns([5, 3, 3, 2, 2])
        row[0].write(line["item"])
        cash_price = line["price"]
        card_price_line = cash_price * (1 + card_fee_rate)
        row[1].write(
            f"${cash_price:.2f} / ${card_price_line:.2f}"
        )

        # Quantity with quick buttons
        q_cols = row[2].columns([1, 1, 1, 1, 1])
        if q_cols[0].button("−", key=f"minus_{idx}"):
            line["qty"] = max(1, line["qty"] - 1)
        q_cols[1].write(line["qty"])
        if q_cols[2].button("+1", key=f"plus1_{idx}"):
            line["qty"] += 1
        if q_cols[3].button("+2", key=f"plus2_{idx}"):
            line["qty"] += 2
        if q_cols[4].button("+5", key=f"plus5_{idx}"):
            line["qty"] += 5

        row[3].write(f"${line['qty'] * line['price']:.2f}")
        if row[4].button("Remove", key=f"rm_{idx}"):
            remove_indices.append(idx)

    for i in sorted(remove_indices, reverse=True):
        st.session_state.cart.pop(i)
    if remove_indices:
        st.rerun()

# Notes with flag reset
default_note = "" if st.session_state.clear_note else st.session_state.get("note", "")
st.text_area("Notes (optional)", key="note", value=default_note)
st.session_state.clear_note = False

# Payment method
st.subheader("Payment Method")
st.session_state.payment = st.radio(
    "Select payment method:",
    ["Cash", "Card", "Other"],
    index=["Cash", "Card", "Other"].index(st.session_state.payment),
    horizontal=True,
)

# Visual feedback
if st.session_state.payment == "Card":
    st.info("💳 Card payment selected – card fee will be applied.")
elif st.session_state.payment == "Cash":
    st.success("💵 Cash payment selected – no card fee.")
else:
    st.warning("Other payment method selected – no automatic fee applied.")

# Discount & Tip
disc_tip_cols = st.columns(2)
disc_tip_cols[0].number_input(
    "Discount ($)",
    min_value=0.0,
    step=0.25,
    key="discount",
)
disc_tip_cols[1].number_input(
    "Tip ($)",
    min_value=0.0,
    step=0.25,
    key="tip",
)

# Cash received
default_cash = (
    0.0 if st.session_state.clear_cash else st.session_state.get("cash_received", 0.0)
)
cash_received = st.number_input(
    "Cash Received",
    min_value=0.0,
    step=0.25,
    value=float(default_cash),
    key="cash_received",
)
st.session_state.clear_cash = False

# Totals
subtotal = cart_subtotal(st.session_state.cart)
discount = float(st.session_state.get("discount", 0.0))
discount = max(0.0, min(discount, subtotal))  # clamp
effective_subtotal = round(subtotal - discount, 2)

tax_amt = round(effective_subtotal * (st.session_state.tax_rate / 100.0), 2)
tip_amt = round(float(st.session_state.get("tip", 0.0)), 2)

base_total = effective_subtotal + tax_amt + tip_amt
card_fee_for_card = round(base_total * card_fee_rate, 2)

cash_total = round(base_total, 2)
card_total = round(base_total + card_fee_for_card, 2)

# Card fee actually applied only if paying by card
card_fee_amt = card_fee_for_card if st.session_state.payment == "Card" else 0.0

# Amount actually due based on chosen payment method
if st.session_state.payment == "Card":
    amount_due = card_total
else:
    amount_due = cash_total

totals = st.columns(5)
totals[0].metric("Subtotal", f"${subtotal:.2f}")
totals[1].metric("Discount", f"-${discount:.2f}")
totals[2].metric("Tax", f"${tax_amt:.2f}")
totals[3].metric("Tip", f"${tip_amt:.2f}")
totals[4].metric("Card Fee (if card)", f"${card_fee_for_card:.2f}")

cash_card_cols = st.columns(2)
cash_card_cols[0].metric("Cash Total", f"${cash_total:.2f}")
cash_card_cols[1].metric("Card Total", f"${card_total:.2f}")

change_due = max(0.0, round(st.session_state.cash_received - amount_due, 2))
st.metric("Change Due (based on selected payment)", f"${change_due:.2f}")

# Checkout
checkout_clicked = st.button(
    "✅ Checkout & Save",
    disabled=len(st.session_state.cart) == 0,
    use_container_width=True,
)

if checkout_clicked:
    # Basic validation for cash sales
    if st.session_state.payment == "Cash" and st.session_state.cash_received + 1e-9 < amount_due:
        st.error(
            f"Cash received (${st.session_state.cash_received:.2f}) "
            f"is less than amount due (${amount_due:.2f})."
        )
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "Timestamp": timestamp,
            "Date": date.today().isoformat(),
            "Items": format_items_string(st.session_state.cart),
            "Subtotal": subtotal,
            "Discount": discount,
            "Tax": tax_amt,
            "Tip": tip_amt,
            "Card Fee": card_fee_amt,  # only non-zero if Card selected
            "Total": amount_due,       # cash or card total depending on payment
            "Payment Method": st.session_state.payment,
            "Notes": st.session_state.note,
            "Cash Received": st.session_state.cash_received,
            "Change": change_due,
        }
        append_sale_to_excel(record)
        st.success("Sale saved!")

        # Save receipt text for display/print
        st.session_state.last_receipt = build_receipt_text(record)

        # Reset for next sale
        st.session_state.cart = []
        st.session_state.clear_note = True
        st.session_state.clear_cash = True
        st.rerun()

# Show last receipt (with print & download options)
if st.session_state.last_receipt:
    st.subheader("🧾 Last Receipt")

    safe_receipt = escape(st.session_state.last_receipt)
    st.markdown(
        f"<div id='receipt-block'><pre>{safe_receipt}</pre></div>",
        unsafe_allow_html=True,
    )

    bcol1, bcol2 = st.columns(2)
    with bcol1:
        st.download_button(
            "⬇️ Download Receipt (.txt)",
            data=st.session_state.last_receipt,
            file_name=f"receipt_{date.today().isoformat()}.txt",
            mime="text/plain",
        )
    with bcol2:
        if st.button("🖨️ Print Receipt"):
            # Trigger browser print dialog – CSS above makes it only print the receipt block
            st.markdown(
                "<script>window.print();</script>",
                unsafe_allow_html=True,
            )

# ---------- Daily Summary ----------
st.subheader("📈 Today’s Summary")
df_sales = safe_read_sales()
if not df_sales.empty and "Date" in df_sales.columns:
    today_str = date.today().isoformat()
    todays = df_sales[df_sales["Date"] == today_str]
    if not todays.empty:
        cols = st.columns(4)
        cols[0].metric("Transactions", f"{len(todays)}")
        cols[1].metric(
            "Revenue (pre-tax subtotal)",
            f"${todays['Subtotal'].sum():.2f}",
        )
        if "Card Fee" in todays.columns:
            cols[2].metric(
                "Card Fees Collected", f"${todays['Card Fee'].sum():.2f}"
            )
        else:
            cols[2].metric("Card Fees Collected", "$0.00")
        cols[3].metric("Revenue (total)", f"${todays['Total'].sum():.2f}")

        # Split by payment type
        cash_sales = todays[todays["Payment Method"] == "Cash"]
        card_sales = todays[todays["Payment Method"] == "Card"]
        other_sales = todays[
            (~todays["Payment Method"].isin(["Cash", "Card"]))
        ]

        cash_rev = cash_sales["Total"].sum() if not cash_sales.empty else 0.0
        card_rev = card_sales["Total"].sum() if not card_sales.empty else 0.0
        other_rev = other_sales["Total"].sum() if not other_sales.empty else 0.0

        # Expected cash drawer (from today's cash sales)
        if (
            "Cash Received" in todays.columns
            and "Change" in todays.columns
        ):
            drawer_cash = (cash_sales["Cash Received"] - cash_sales["Change"]).sum()
        else:
            drawer_cash = cash_rev

        cols2 = st.columns(4)
        cols2[0].metric("Cash Revenue", f"${cash_rev:.2f}")
        cols2[1].metric("Card Revenue", f"${card_rev:.2f}")
        cols2[2].metric("Other Revenue", f"${other_rev:.2f}")
        cols2[3].metric("Expected Cash in Drawer", f"${drawer_cash:.2f}")

        # Tips & discounts
        tip_total = todays["Tip"].sum() if "Tip" in todays.columns else 0.0
        disc_total = todays["Discount"].sum() if "Discount" in todays.columns else 0.0
        cols3 = st.columns(2)
        cols3[0].metric("Tips Collected", f"${tip_total:.2f}")
        cols3[1].metric("Discounts Given", f"${disc_total:.2f}")

        # Top items today
        item_counts = parse_item_counts(todays)
        if item_counts:
            st.markdown("**Top Items Today (by quantity sold)**")
            top_items = item_counts.most_common(10)
            top_df = pd.DataFrame(top_items, columns=["Item", "Quantity Sold"])
            st.table(top_df)
        else:
            st.info("No item breakdown available for today.")

        with st.expander("Show Today’s Sales (raw data)"):
            st.dataframe(todays, use_container_width=True)
    else:
        st.info("No sales today yet.")
else:
    st.info("No sales data yet.")
