import io
import re
import pandas as pd
import streamlit as st
from formatter import parse_delimited_file, format_dataframe

# Page Configuration
st.set_page_config(
    page_title="Pipe Delimited File Cleaner & Formatter",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .stMetric {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        padding: 12px;
        border-radius: 8px;
    }
    .badge-info {
        background-color: #EFF6FF;
        color: #1D4ED8;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Sample Data Generator for Demo
DEMO_CSV = """EMP_ID||FULL_NAME|JOIN_DATE||SALARY||CITY|PHONE
101||john doe|2023/04/15||75000.5||new york|1234567890
102||JANE SMITH|15-05-2022||89200.0||san francisco|9876543210
103||robert brown|2021-12-01||62400||chicago||3456789012
104||EMILY DAVIS|01/20/2024||95000.75||seattle|4567890123
105||william wilson|2022-08-10||51000||boston|5678901234"""

# Sidebar - Configuration
with st.sidebar:
    st.header("⚙️ Delimiter & Parse Settings")

    delimiter_choice = st.selectbox(
        "Delimiter Mode",
        options=[
            ("Smart Mixed (| and || as splitters)", "smart_mixed"),
            ("Standard Pipe | (|| is empty field)", "pipe_with_empty"),
            ("Double Pipe || strictly (| is text)", "double_pipe"),
            ("Custom Regex", "custom_regex")
        ],
        format_func=lambda x: x[0],
        index=0,
        help="Choose how the engine splits lines containing single and double pipes."
    )[1]

    custom_regex = r"\|{1,2}"
    if delimiter_choice == "custom_regex":
        custom_regex = st.text_input("Enter Delimiter Regex", value=r"\|{1,2}")

    has_header = st.checkbox("First row contains headers", value=True)
    clean_col_names = st.checkbox("Standardize column names (snake_case/no spaces)", value=True)
    
    st.divider()
    st.subheader("💡 Need Help?")
    st.caption(
        "Upload any text/CSV file with pipe delimiters. "
        "The app parses, transforms each column based on its name/rules, and gives you clean CSV/Excel output."
    )

# Main Header
st.markdown('<div class="main-header">📊 Delimited File Cleaner & Formatter</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Easily parse files with mixed <code>|</code> and <code>||</code> delimiters and format columns.</div>', unsafe_allow_html=True)

# File Input Section
col_upload, col_demo = st.columns([3, 1])

with col_upload:
    uploaded_file = st.file_uploader(
        "Upload CSV or Delimited Text File",
        type=["csv", "txt", "tsv", "dat"],
        help="Upload files delimited with | or ||"
    )

with col_demo:
    st.write("Or try sample data:")
    use_demo = st.button("Load Demo File", use_container_width=True)

# Determine file content
file_content = None
if uploaded_file is not None:
    try:
        file_content = uploaded_file.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        file_content = uploaded_file.getvalue().decode("latin-1")
elif use_demo:
    file_content = DEMO_CSV
    st.info("Loaded sample demo dataset.")

if not file_content:
    st.info("👆 Please upload a file or click **'Load Demo File'** to begin.")
    st.stop()

# Parse the raw content
try:
    df_raw = parse_delimited_file(
        file_content=file_content,
        delimiter_mode=delimiter_choice,
        custom_regex=custom_regex,
        has_header=has_header
    )
except Exception as e:
    st.error(f"Error parsing file: {e}")
    st.stop()

if df_raw.empty:
    st.warning("The parsed file is empty. Please check your file content and delimiter settings.")
    st.stop()

# Overview Metrics
metric_cols = st.columns(4)
metric_cols[0].metric("Total Rows", f"{len(df_raw):,}")
metric_cols[1].metric("Total Columns", f"{len(df_raw.columns):,}")
metric_cols[2].metric("Empty Cells", f"{df_raw.isna().sum().sum():,}")
metric_cols[3].metric("Delimiter Mode", delimiter_choice)

st.write("---")

# Column Formatting Rules Configuration
st.subheader("🛠️ Column Formatting Rules")
st.write("Configure format settings per column. Smart defaults are auto-suggested based on column names.")

with st.expander("Click to Configure Column Rules", expanded=True):
    col_rules = {}
    cols_to_keep = []

    # Display columns in a responsive grid
    for col in df_raw.columns:
        col_lower = str(col).lower()
        
        # Guess column type based on column name
        default_type = "text"
        default_date_fmt = "%Y-%m-%d"
        default_case = "none"
        default_symbol = "$"
        default_decimals = 2
        default_pad = 0

        if any(k in col_lower for k in ["date", "time", "dt", "dob", "joined", "created"]):
            default_type = "date"
        elif any(k in col_lower for k in ["salary", "price", "amount", "cost", "total", "fee", "rev"]):
            default_type = "currency"
        elif any(k in col_lower for k in ["qty", "count", "num", "score", "age"]):
            default_type = "number"
            default_decimals = 0
        elif any(k in col_lower for k in ["id", "code", "zip", "pin", "ssn"]):
            default_type = "id"
            default_pad = 5
        elif any(k in col_lower for k in ["name", "city", "state", "country"]):
            default_type = "text"
            default_case = "title"

        st.markdown(f"#### Column: `{col}`")
        c1, c2, c3, c4 = st.columns([1, 1.2, 1.2, 1.2])

        with c1:
            keep = st.checkbox(f"Include in export", value=True, key=f"keep_{col}")
            if keep:
                cols_to_keep.append(col)

        with c2:
            type_options = ["text", "date", "currency", "number", "id"]
            type_idx = type_options.index(default_type) if default_type in type_options else 0
            selected_type = st.selectbox(
                "Data Type",
                options=type_options,
                index=type_idx,
                key=f"type_{col}"
            )

        with c3:
            rule_options = {}
            if selected_type == "text":
                case_options = [("None", "none"), ("Title Case", "title"), ("UPPERCASE", "upper"), ("lowercase", "lower")]
                case_idx = [x[1] for x in case_options].index(default_case)
                selected_case = st.selectbox("Text Case", options=case_options, format_func=lambda x: x[0], index=case_idx, key=f"case_{col}")[1]
                rule_options["case"] = selected_case
            elif selected_type == "date":
                date_fmt = st.selectbox(
                    "Target Date Format",
                    options=["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y%m%d"],
                    index=0,
                    key=f"date_fmt_{col}"
                )
                rule_options["date_format"] = date_fmt
            elif selected_type in ("currency", "number"):
                decimals = st.number_input("Decimal Places", min_value=0, max_value=6, value=default_decimals, key=f"dec_{col}")
                rule_options["decimals"] = int(decimals)
                if selected_type == "currency":
                    symbol = st.text_input("Currency Symbol", value=default_symbol, key=f"sym_{col}")
                    rule_options["currency_symbol"] = symbol
            elif selected_type == "id":
                pad_len = st.number_input("Pad with zeros to length (0 = no pad)", min_value=0, max_value=20, value=default_pad, key=f"pad_{col}")
                rule_options["id_pad_zeros"] = int(pad_len)

        with c4:
            new_name = st.text_input("Rename Column", value=col, key=f"rename_{col}")
            rule_options["new_name"] = new_name
            rule_options["type"] = selected_type

        col_rules[col] = rule_options
        st.write("---")

# Filter DataFrame to kept columns
df_selected = df_raw[cols_to_keep] if cols_to_keep else df_raw

# Apply Formatting
df_formatted = format_dataframe(
    df=df_selected,
    column_rules=col_rules,
    clean_column_names=clean_col_names
)

# Tabs for Data Preview
st.subheader("👁️ Preview Data")
tab_clean, tab_raw, tab_stats = st.tabs(["✨ Formatted Output", "📄 Raw Parsed Data", "📈 Data Profile"])

with tab_clean:
    st.dataframe(df_formatted, use_container_width=True)

with tab_raw:
    st.dataframe(df_raw, use_container_width=True)

with tab_stats:
    st.write("Column non-null counts and unique values:")
    stats_df = pd.DataFrame({
        "Column": df_formatted.columns,
        "Non-Null Count": df_formatted.notnull().sum().values,
        "Null Count": df_formatted.isnull().sum().values,
        "Unique Values": df_formatted.nunique().values
    })
    st.dataframe(stats_df, use_container_width=True)

# Export Section
st.subheader("📥 Download Formatted File")
export_col1, export_col2, export_col3 = st.columns([1.5, 1.5, 3])

with export_col1:
    out_delimiter = st.selectbox(
        "Export CSV Delimiter",
        options=[("Comma (,)", ","), ("Pipe (|)", "|"), ("Tab (\\t)", "\t"), ("Semicolon (;)", ";")],
        format_func=lambda x: x[0],
        index=0
    )[1]
    
    csv_bytes = df_formatted.to_csv(index=False, sep=out_delimiter).encode("utf-8")
    st.download_button(
        label="⬇️ Download Clean CSV",
        data=csv_bytes,
        file_name="formatted_data.csv",
        mime="text/csv",
        use_container_width=True
    )

with export_col2:
    # Excel output
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_formatted.to_excel(writer, index=False, sheet_name="Cleaned Data")
    excel_bytes = excel_buffer.getvalue()

    st.download_button(
        label="⬇️ Download Excel (.xlsx)",
        data=excel_bytes,
        file_name="formatted_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

