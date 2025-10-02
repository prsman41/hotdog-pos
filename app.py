# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from pathlib import Path

st.set_page_config(page_title="Hotdog Stand POS", layout="wide")

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
    df = pd.DataFrame(menu_list)
    df.to_csv(MENU_CSV, index=False)

def ensure_sales_file_exists():
    if not SALES_XLSX.exists():
        cols = ["Timestamp", "Date", "Items", "Subtotal", "Tax", "Total",
                "Payment Method", "Notes", "Cash Received", "Change"]
        pd.DataFrame(columns=cols).to_excel(SALES_XLSX, sheet_name=SALES_SHEET, index=False)

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

def safe_read_sales():
    """Safe load of sales.xlsx"""
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
    return "; ".join([f'{row["qty"]}x {row["item"]} @ {row["price"]:.2f}' for row in cart])

# ---------- Session state ----------
if "cart" not in st.session_state:
    st.session_state.cart = []
if "tax_rate" not in st.session_state:
    st.session_state.tax_rate = 0.0
if "payment" not in st.session_state:
    st.session_state.payment = "Cash"
if "cash_received" not in st.session_state:
    st.session_state.cash_received = 0.0
if "clear_note" not in st.session_state:
    st.session_state.clear_note = False

# ---------- Load menu ----------
MENU = load_menu()

# ---------- Sidebar ----------
st.sidebar.header("Menu & Settings")

with st.sidebar.expander("Edit Menu (change prices, add/remove items)", expanded=False):
    edited_menu = []
    for idx, entry in enumerate(MENU):
        cols = st.columns([6, 4])
        name = cols[0].text_input(f"Item name #{idx+1}", value=entry["item"], key=f"menu_name_{idx}")
        price = cols[1].number_input(f"Price #{idx+1} ($)", value=float(entry["price"]), step=0.25,
                                     format="%.2f", key=f"menu_price_{idx}")
        edited_menu.append({"item": name.strip(), "price": float(price)})

    st.markdown("---")
    new_name = st.text_input("New item name", value="", key="new_item_name")
    new_price = st.number_input("New item price ($)", min_value=0.0, value=0.0, step=0.25,
                                format="%.2f", key="new_item_price")
    if st.button("Add Item"):
        if new_name.strip():
            edited_menu.append({"item": new_name.strip(), "price": float(new_price)})
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
st.session_state.tax_rate = st.sidebar.number_input("Sales Tax Rate (%)", min_value=0.0, max_value=30.0,
                                                    step=0.25, value=st.session_state.tax_rate)
st.session_state.payment = st.sidebar.selectbox("Default Payment Method", ["Cash", "Card", "Other"],
                                                index=["Cash","Card","Other"].index(st.session_state.payment))

if st.sidebar.button("➕ New Sale", type="primary"):
    st.session_state.cart = []
    st.session_state.cash_received = 0.0
    st.session_state.clear_note = True
    st.rerun()

# ---------- Main ----------
st.title("🌭 Hotdog Stand POS")

# Item buttons
st.subheader("Add Items")
cols_per_row = 3
cols = st.columns(cols_per_row)
for i, entry in enumerate(MENU):
    col = cols[i % cols_per_row]
    if col.button(f'{entry["item"]} — ${float(entry["price"]):.2f}', key=f"add_{i}", use_container_width=True):
        found = False
        for c in st.session_state.cart:
            if c["item"] == entry["item"] and abs(c["price"] - float(entry["price"])) < 1e-9:
                c["qty"] += 1
                found = True
                break
        if not found:
            st.session_state.cart.append({"item": entry["item"], "price": float(entry["price"]), "qty": 1})
        st.rerun()

st.divider()

# Cart
st.subheader("Cart")
if not st.session_state.cart:
    st.info("Cart is empty.")
else:
    cart_cols = st.columns([5,2,2,2,2])
    cart_cols[0].markdown("**Item**")
    cart_cols[1].markdown("**Price**")
    cart_cols[2].markdown("**Qty**")
    cart_cols[3].markdown("**Line Total**")
    cart_cols[4].markdown("**Actions**")

    remove_indices = []
    for idx, line in enumerate(st.session_state.cart):
        row = st.columns([5,2,2,2,2])
        row[0].write(line["item"])
        row[1].write(f"${line['price']:.2f}")
        q1, q2, q3 = row[2].columns([1,1,2])
        if q1.button("−", key=f"minus_{idx}"):
            line["qty"] = max(1, line["qty"] - 1)
        q2.write(line["qty"])
        if q3.button("+", key=f"plus_{idx}"):
            line["qty"] += 1
        row[3].write(f"${line['qty'] * line['price']:.2f}")
        if row[4].button("Remove", key=f"rm_{idx}"):
            remove_indices.append(idx)

    for i in sorted(remove_indices, reverse=True):
        st.session_state.cart.pop(i)
    if remove_indices:
        st.rerun()

# Notes handling with flag
default_note = ""
if st.session_state.clear_note:
    default_note = ""
    st.session_state.clear_note = False
else:
    default_note = st.session_state.get("note", "")

st.text_area("Notes (optional)", key="note", value=default_note)

# Cash input
cash_received = st.number_input("Cash Received", min_value=0.0, step=0.25,
                                value=float(st.session_state.cash_received))
st.session_state.cash_received = float(cash_received)

# Totals
subtotal = cart_subtotal(st.session_state.cart)
tax_amt = round(subtotal * (st.session_state.tax_rate/100.0), 2)
total = round(subtotal + tax_amt, 2)

totals = st.columns(3)
totals[0].metric("Subtotal", f"${subtotal:.2f}")
totals[1].metric("Tax", f"${tax_amt:.2f}")
totals[2].metric("Total", f"${total:.2f}")

change_due = max(0.0, round(st.session_state.cash_received - total, 2))
st.metric("Change Due", f"${change_due:.2f}")

# Checkout
if st.button("✅ Checkout & Save", disabled=len(st.session_state.cart)==0, use_container_width=True):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "Timestamp": timestamp,
        "Date": date.today().isoformat(),
        "Items": format_items_string(st.session_state.cart),
        "Subtotal": subtotal,
        "Tax": tax_amt,
        "Total": total,
        "Payment Method": st.session_state.payment,
        "Notes": st.session_state.note,
        "Cash Received": st.session_state.cash_received,
        "Change": change_due,
    }
    append_sale_to_excel(record)
    st.success("Sale saved!")

    st.session_state.cart = []
    st.session_state.cash_received = 0.0
    st.session_state.clear_note = True  # flag for clearing notes
    st.rerun()

# ---------- Daily Summary ----------
st.subheader("📈 Today’s Summary")
df_sales = safe_read_sales()
if not df_sales.empty and "Date" in df_sales.columns:
    today_str = date.today().isoformat()
    todays = df_sales[df_sales["Date"] == today_str]
    if not todays.empty:
        cols = st.columns(3)
        cols[0].metric("Transactions", f"{len(todays)}")
        cols[1].metric("Revenue (pre-tax)", f"${todays['Subtotal'].sum():.2f}")
        cols[2].metric("Revenue (total)", f"${todays['Total'].sum():.2f}")
        with st.expander("Show Today’s Sales"):
            st.dataframe(todays, use_container_width=True)
    else:
        st.info("No sales today yet.")
else:
    st.info("No sales data yet.")
