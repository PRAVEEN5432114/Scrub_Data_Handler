import io
import re
import pandas as pd
import streamlit as st
from formatter import parse_delimited_file, format_dataframe, decode_file_bytes, DEFAULT_NULL_STRINGS

# Page Configuration
st.set_page_config(
    page_title="Delimited File Cleaner & Formatter",
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
</style>
""", unsafe_allow_html=True)

# Sample Data for Text and CSV
DEMO_TXT = """# Monthly Scrub Data Report
# Export Source: Legacy Database System
| EMP_ID | FULL_NAME | JOIN_DATE | SALARY | CITY | NOTES |
|:-------|:----------|:----------|:-------|:-----|:------|
| 101 | john doe | 2023/04/15 | 75000.5 | new york | active |
| 102 | JANE SMITH | 15-05-2022 | 89200.0 |   | NULL |
| 103 | robert brown | 2021-12-01 | | chicago | N/A |
| 104 | | 01/20/2024 | 95000.75 | seattle | None |
| 105 | william wilson | | 51000 | - | |
# End of report"""

# Sidebar - Configuration
with st.sidebar:
    st.header("⚙️ Delimiter & Parsing Rules")

    delimiter_choice = st.selectbox(
        "Delimiter Strategy",
        options=[
            ("Smart Pipe: Handles | , || , and |   |", "smart_pipe_empty"),
            ("Mixed Delimiters: || and | with |   | empty", "mixed_delimiters_with_empty"),
            ("Strict Double Pipe: || only", "strict_double_pipe"),
            ("Custom Regex", "custom_regex")
        ],
        format_func=lambda x: x[0],
        index=0,
        help="Select how consecutive pipes and space-separated pipes should be parsed."
    )[1]

    custom_regex = r"\|{1,2}"
    if delimiter_choice == "custom_regex":
        custom_regex = st.text_input("Enter Delimiter Regex", value=r"\|{1,2}")

    st.subheader("🧹 .TXT & CSV Cleaners")
    handle_space_pipes = st.checkbox(
        "Treat '|   |' (pipes with spaces) as Empty/Null",
        value=True,
        help="Converts cells containing only whitespace between pipes into null/empty values."
    )
    
    clean_null_strings = st.checkbox(
        "Treat 'NULL', 'None', 'N/A', '-' as Null",
        value=True,
        help="Recognizes placeholder text like NULL, None, N/A, and dashes as true missing values."
    )

    strip_dividers = st.checkbox(
        "Ignore Table Dividers (|---|---| or +---+)",
        value=True,
        help="Filters out markdown/ASCII separator lines commonly found in .txt files."
    )

    strip_borders = st.checkbox(
        "Strip boundary pipes (|...| table style)",
        value=True,
        help="Removes leading and trailing boundary pipes so no phantom blank columns appear."
    )

    has_header = st.checkbox("First row contains headers", value=True)
    clean_col_names = st.checkbox("Standardize column names (snake_case)", value=True)

    st.divider()
    st.subheader("📤 Output Preferences")
    null_fill_choice = st.selectbox(
        "Display/Export Nulls as:",
        options=[
            ('Empty space ("")', ""),
            ('Text "NULL"', "NULL"),
            ('Text "NA"', "NA"),
            ('Dash ("-")', "-")
        ],
        format_func=lambda x: x[0],
        index=0
    )[1]

# Main Header
st.markdown('<div class="main-header">📊 Delimited File Cleaner & Formatter</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Clean and format <b>.txt</b>, <b>.csv</b>, and <b>.tsv</b> files with <code>|</code>, <code>||</code>, <code>|   |</code>, and table borders.</div>', unsafe_allow_html=True)

# Input method selection: Upload vs Paste Text
input_method = st.radio("Choose Input Method:", ["📁 Upload File (.txt, .csv, .tsv, .dat)", "📝 Paste Raw Text Directly"], horizontal=True)

file_content = None

if input_method == "📁 Upload File (.txt, .csv, .tsv, .dat)":
    col_upload, col_demo = st.columns([3, 1])
    with col_upload:
        uploaded_file = st.file_uploader(
            "Upload file (.txt, .csv, .tsv, .dat)",
            type=["txt", "csv", "tsv", "dat", "log"],
            help="Upload any delimited text or CSV file."
        )
    with col_demo:
        st.write("Or try sample text file:")
        use_demo = st.button("Load Demo .TXT File", use_container_width=True)

    if uploaded_file is not None:
        file_content = decode_file_bytes(uploaded_file.getvalue())
    elif use_demo:
        file_content = DEMO_TXT
        st.info("Loaded sample .txt table report with comments and markdown dividers.")

else:
    # Direct paste text area
    col_paste, col_paste_demo = st.columns([3, 1])
    with col_paste_demo:
        if st.button("Load Demo Text into Box"):
            st.session_state["pasted_text_input"] = DEMO_TXT
    
    default_text = st.session_state.get("pasted_text_input", "")
    pasted_text = st.text_area("Paste delimited text lines here:", value=default_text, height=220)
    if pasted_text.strip():
        file_content = pasted_text

if not file_content:
    st.info("👆 Please upload a **.txt** or **.csv** file, or paste text above to begin.")
    st.stop()

# Parse the raw content
try:
    df_raw = parse_delimited_file(
        file_content=file_content,
        delimiter_mode=delimiter_choice,
        custom_regex=custom_regex,
        has_header=has_header,
        handle_space_pipes=handle_space_pipes,
        strip_borders=strip_borders,
        skip_table_dividers=strip_dividers,
        null_strings=DEFAULT_NULL_STRINGS if clean_null_strings else set()
    )
except Exception as e:
    st.error(f"Error parsing file: {e}")
    st.stop()

if df_raw.empty:
    st.warning("The parsed file is empty. Please verify your file contents and delimiter settings.")
    st.stop()

# Overview Metrics
metric_cols = st.columns(4)
metric_cols[0].metric("Total Rows", f"{len(df_raw):,}")
metric_cols[1].metric("Total Columns", f"{len(df_raw.columns):,}")
metric_cols[2].metric("Empty / Null Cells", f"{df_raw.isna().sum().sum():,}")
metric_cols[3].metric("Delimiter Mode", delimiter_choice)

st.write("---")

# Column Formatting Rules Configuration
st.subheader("🛠️ Column Formatting Rules")
st.write("Configure format settings per column. Smart defaults are auto-suggested based on column names.")

with st.expander("Click to Configure Column Rules", expanded=True):
    col_rules = {}
    cols_to_keep = []

    for col in df_raw.columns:
        col_lower = str(col).lower()
        
        # Smart guesses for types
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
                pad_len = st.number_input("Pad zeros to length (0 = no pad)", min_value=0, max_value=20, value=default_pad, key=f"pad_{col}")
                rule_options["id_pad_zeros"] = int(pad_len)

        with c4:
            new_name = st.text_input("Rename Column", value=col, key=f"rename_{col}")
            rule_options["new_name"] = new_name
            rule_options["type"] = selected_type

        col_rules[col] = rule_options
        st.write("---")

# Filter DataFrame to selected columns
df_selected = df_raw[cols_to_keep] if cols_to_keep else df_raw

# Apply Formatting & Null replacements
df_formatted = format_dataframe(
    df=df_selected,
    column_rules=col_rules,
    clean_column_names=clean_col_names,
    null_fill_value=null_fill_choice
)

# Tabs for Data Preview
st.subheader("👁️ Preview Data")
tab_clean, tab_raw, tab_stats = st.tabs(["✨ Formatted Output", "📄 Raw Parsed Data", "📈 Null & Data Profile"])

with tab_clean:
    st.dataframe(df_formatted, use_container_width=True)

with tab_raw:
    st.dataframe(df_raw, use_container_width=True)

with tab_stats:
    stats_df = pd.DataFrame({
        "Column": df_raw.columns,
        "Total Rows": len(df_raw),
        "Null / Empty Count": df_raw.isna().sum().values,
        "Fill Rate (%)": ((df_raw.notna().sum() / len(df_raw)) * 100).round(1).values
    })
    st.dataframe(stats_df, use_container_width=True)

# Export Section
st.subheader("📥 Download Clean File")
export_col1, export_col2, export_col3 = st.columns([1.5, 1.5, 1.5])

with export_col1:
    out_delimiter = st.selectbox(
        "Export Delimiter",
        options=[("Comma (,)", ","), ("Pipe (|)", "|"), ("Tab (\\t)", "\t"), ("Semicolon (;)", ";")],
        format_func=lambda x: x[0],
        index=0
    )[1]
    
    csv_bytes = df_formatted.to_csv(index=False, sep=out_delimiter).encode("utf-8")
    st.download_button(
        label="⬇️ Download Clean CSV",
        data=csv_bytes,
        file_name="clean_formatted_data.csv",
        mime="text/csv",
        use_container_width=True
    )

with export_col2:
    txt_bytes = df_formatted.to_csv(index=False, sep=out_delimiter).encode("utf-8")
    st.download_button(
        label="⬇️ Download Clean .TXT",
        data=txt_bytes,
        file_name="clean_formatted_data.txt",
        mime="text/plain",
        use_container_width=True
    )

with export_col3:
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_formatted.to_excel(writer, index=False, sheet_name="Cleaned Data")
    excel_bytes = excel_buffer.getvalue()

    st.download_button(
        label="⬇️ Download Excel (.xlsx)",
        data=excel_bytes,
        file_name="clean_formatted_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
