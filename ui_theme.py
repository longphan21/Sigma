import streamlit as st

_dialog_decorator = getattr(st, "dialog", getattr(st, "experimental_dialog", None))
_fragment_decorator = getattr(st, "fragment", getattr(st, "experimental_fragment", lambda f: f))


def render_html(html_str: str):
    """Strip leading whitespace so Streamlit renders raw HTML cleanly."""
    clean_html = "\n".join(line.lstrip() for line in html_str.splitlines() if line.strip())
    st.markdown(clean_html, unsafe_allow_html=True)


# ==============================================================================
# 1. CENTER MODAL NOTIFICATION SYSTEM
# ==============================================================================
def queue_popup(title: str, message: str, status_type: str = "success"):
    st.session_state["pending_popup"] = {
        "title": title,
        "message": message,
        "status_type": status_type,
    }


if _dialog_decorator is not None:
    @_dialog_decorator("System Notification")
    def _show_notification_modal(title: str, message: str, status_type: str):
        icon_map = {
            "success": ("✅", "#15803D", "#DCFCE7", "#86EFAC"),
            "warning": ("⚠️", "#B45309", "#FEF3C7", "#FDE68A"),
            "error": ("🗑️", "#B91C1C", "#FEE2E2", "#FCA5A5"),
            "info": ("ℹ️", "#0369A1", "#E0F2FE", "#BAE6FD"),
        }
        ic, color_text, bg_box, border_box = icon_map.get(status_type, icon_map["success"])

        render_html(f"""
        <div style="background-color:{bg_box}; border:1.5px solid {border_box}; border-radius:10px; padding:16px; text-align:center; margin-bottom:14px;">
            <div style="font-size:2rem; line-height:1.1; margin-bottom:8px;">{ic}</div>
            <div style="color:{color_text}; font-size:1.02rem; font-weight:800; margin-bottom:6px;">{title}</div>
            <div style="color:#0A2540; font-size:0.86rem; font-weight:500; line-height:1.45;">{message}</div>
        </div>
        """)
        if st.button("OK", type="primary", use_container_width=True, key="popup_ok_btn"):
            st.rerun()


def render_pending_popup():
    if "pending_popup" in st.session_state and st.session_state["pending_popup"] is not None:
        data = st.session_state.pop("pending_popup")
        if _dialog_decorator is not None:
            _show_notification_modal(data["title"], data["message"], data["status_type"])
        else:
            st.success(f"**{data['title']}**: {data['message']}")


# ==============================================================================
# 2. GLOBAL CSS (UNIFORM INPUT/BUTTON HEIGHTS & SINGLE-LINE LABELS)
# ==============================================================================
def inject_custom_css():
    render_html("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

        html, body, .stApp {
            background-color: #F4FAF6 !important;
            color: #0A2540 !important;
            font-family: 'Be Vietnam Pro', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }

        .block-container,
        [data-testid="stMainBlockContainer"],
        [data-testid="stAppViewBlockContainer"] {
            padding-top: 3.5rem !important;
            padding-bottom: 1.8rem !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
            max-width: 100% !important;
        }

        .tabular-nums, [data-testid="stMetricValue"], [data-testid="stDataFrame"], table td {
            font-variant-numeric: tabular-nums !important;
        }

        [data-testid="stHeaderActionElements"],
        h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {
            display: none !important;
        }

        div[role="dialog"] {
            max-width: 440px !important;
            width: 92vw !important;
            border-radius: 14px !important;
            border: 1.5px solid #A5D6A7 !important;
            box-shadow: 0 14px 36px rgba(10, 37, 64, 0.22) !important;
            background-color: #FFFFFF !important;
        }

        h1, h2, h3, h4, h5, h6 {
            color: #0A2540 !important;
            font-family: 'Be Vietnam Pro', sans-serif !important;
            font-weight: 700 !important;
            letter-spacing: -0.2px;
            margin-top: 0 !important;
        }
        h3 {
            font-size: 0.96rem !important;
            font-weight: 800 !important;
            margin-bottom: 0.5rem !important;
        }
        h4, h5 {
            font-size: 0.88rem !important;
            font-weight: 700 !important;
            margin-bottom: 0.4rem !important;
        }

        /* SIDEBAR TOGGLE */
        [data-testid="stSidebarHeader"] {
            display: flex !important;
            justify-content: flex-end !important;
            padding: 0.4rem 0.6rem 0 0.6rem !important;
        }
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="collapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] button {
            opacity: 1 !important;
            visibility: visible !important;
            background-color: #FFFFFF !important;
            color: #2E7D32 !important;
            border: 1.5px solid #66BB6A !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 3px rgba(10, 37, 64, 0.08) !important;
            width: 34px !important;
            height: 34px !important;
        }
        [data-testid="stSidebarCollapseButton"] button:hover,
        [data-testid="collapsedControl"] button:hover,
        [data-testid="stSidebarCollapsedControl"] button:hover {
            background-color: #2E7D32 !important;
            color: #FFFFFF !important;
            border-color: #1B5E20 !important;
        }
        [data-testid="stSidebarCollapseButton"] button svg,
        [data-testid="collapsedControl"] button svg,
        [data-testid="stSidebarCollapsedControl"] button svg {
            fill: currentColor !important;
        }

        /* SIDEBAR */
        [data-testid="stSidebar"] {
            background-color: #E6F4EA !important;
        }
        [data-testid="stSidebar"][aria-expanded="true"] {
            border-right: 1.5px solid #C8E6C9 !important;
            min-width: 235px !important;
            max-width: 255px !important;
        }
        [data-testid="stSidebar"][aria-expanded="false"] {
            min-width: 0px !important;
            max-width: 0px !important;
            width: 0px !important;
            border-right: none !important;
        }
        [data-testid="stSidebar"] > div:first-child {
            background-color: #E6F4EA !important;
        }
        .sidebar-brand {
            background-color: #FFFFFF;
            padding: 11px 14px;
            border-radius: 10px;
            border: 1.5px solid #A5D6A7;
            border-left: 5px solid #2E7D32;
            margin-bottom: 0.9rem;
            box-shadow: 0 2px 4px rgba(10, 37, 64, 0.04);
        }
        .sidebar-brand-title {
            color: #0A2540 !important;
            font-size: 1.0rem;
            font-weight: 800;
            letter-spacing: -0.2px;
        }
        .sidebar-brand-sub {
            color: #2E7D32 !important;
            font-size: 0.74rem;
            font-weight: 600;
            margin-top: 2px;
        }
        .sidebar-section-label {
            color: #0A2540 !important;
            font-size: 0.70rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            padding: 0 4px;
            margin-bottom: 6px;
        }

        [data-testid="stSidebar"] .stButton {
            width: 100% !important;
            margin-bottom: 2px !important;
        }
        [data-testid="stSidebar"] .stButton > button {
            width: 100% !important;
            min-height: 40px !important;
            height: 40px !important;
            justify-content: flex-start !important;
            text-align: left !important;
            padding: 0 12px !important;
            border-radius: 8px !important;
            font-size: 0.84rem !important;
            font-weight: 700 !important;
            box-shadow: 0 1px 2px rgba(10, 37, 64, 0.04) !important;
            transition: all 0.15s ease !important;
        }
        [data-testid="stSidebar"] .stButton > button > div {
            justify-content: flex-start !important;
            width: 100% !important;
            gap: 8px !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
            background-color: #FFFFFF !important;
            color: #0A2540 !important;
            border: 1.5px solid #C8E6C9 !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="secondary"] p,
        [data-testid="stSidebar"] .stButton > button[kind="secondary"] span {
            color: #0A2540 !important;
            font-weight: 700 !important;
            font-size: 0.84rem !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
            background-color: #D7F0DD !important;
            border-color: #66BB6A !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #2E7D32 0%, #388E3C 100%) !important;
            color: #FFFFFF !important;
            border: 1.5px solid #1B5E20 !important;
            box-shadow: 0 3px 6px rgba(46, 125, 50, 0.22) !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] p,
        [data-testid="stSidebar"] .stButton > button[kind="primary"] span {
            color: #FFFFFF !important;
            font-weight: 800 !important;
            font-size: 0.84rem !important;
        }
        
        /* SUB-MENU ITEMS IN SIDEBAR */
        [class*="st-key-nav_sub_"] {
            padding-left: 14px !important;
        }
        [class*="st-key-nav_sub_"] .stButton > button {
            min-height: 35px !important;
            height: 35px !important;
            font-size: 0.79rem !important;
            border-left: 3px solid #66BB6A !important;
        }

        /* BANNER */
        .page-banner {
            background: linear-gradient(90deg, #E6F4EA 0%, #FFFFFF 100%);
            border: 1px solid #A5D6A7;
            border-left: 5px solid #2E7D32;
            border-radius: 8px;
            padding: 8px 14px;
            margin-top: 2px;
            margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(10, 37, 64, 0.03);
        }
        .page-banner-title {
            color: #0A2540;
            font-size: 1.0rem;
            font-weight: 800;
            margin: 0;
        }
        .page-banner-desc {
            color: #1E3A5F;
            font-size: 0.78rem;
            font-weight: 500;
            margin: 2px 0 0 0;
        }

        .search-result-pill {
            background-color: #E6F4EA;
            border: 1px solid #A5D6A7;
            color: #1B5E20;
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 0.78rem;
            font-weight: 600;
            margin-bottom: 8px;
            display: inline-block;
        }

        /* CARDS & EXPANDERS */
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important;
            border: 1px solid #C8E6C9 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 4px rgba(10, 37, 64, 0.03) !important;
            padding: 0.7rem 0.9rem !important;
            margin-bottom: 0.6rem !important;
        }

        [data-testid="stExpander"] {
            background-color: #FFFFFF !important;
            border: 1px solid #CBE6D0 !important;
            border-radius: 7px !important;
            margin-bottom: 5px !important;
            box-shadow: none !important;
            overflow: hidden;
        }
        [data-testid="stExpander"] summary {
            background-color: #FFFFFF !important;
            padding: 6px 12px !important;
            border-radius: 6px !important;
        }
        [data-testid="stExpander"] summary:hover {
            background-color: #EEF8F0 !important;
        }
        [data-testid="stExpander"] summary p {
            color: #0A2540 !important;
            font-weight: 600 !important;
            font-size: 0.80rem !important;
        }
        [data-testid="stExpanderDetails"] {
            padding: 8px 12px 10px 12px !important;
            border-top: 1px solid #E8F5E9 !important;
            background-color: #FAFDFB !important;
        }

        /* UNIFORM SINGLE-LINE LABELS & 38PX BOX HEIGHT FOR INPUTS AND BUTTONS */
        .stSelectbox label, .stTextInput label, .stDateInput label,
        .stNumberInput label, .stFileUploader label {
            min-height: 20px !important;
            margin-bottom: 4px !important;
        }
        .stSelectbox label p, .stTextInput label p, .stDateInput label p,
        .stNumberInput label p, .stFileUploader label p {
            color: #0A2540 !important;
            font-weight: 700 !important;
            font-size: 0.78rem !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            line-height: 1.25 !important;
            margin: 0 !important;
        }

        div[data-baseweb="select"] > div,
        div[data-baseweb="input"],
        div[data-baseweb="base-input"] {
            background-color: #FFFFFF !important;
            border: 1px solid #A5D6A7 !important;
            border-radius: 7px !important;
            color: #0A2540 !important;
            font-weight: 600 !important;
            font-size: 0.75rem !important;
            height: 36px !important;
            min-height: 36px !important;
            max-height: 36px !important;
            box-sizing: border-box !important;
        }
        div[data-baseweb="select"] > div > div:first-child {
            padding-left: 8px !important;
            padding-right: 2px !important;
        }
        div[data-baseweb="input"] > div {
            border: none !important;
            background: transparent !important;
            height: 34px !important;
            min-height: 34px !important;
        }

        /* LOCKED / DISABLED STEP CONTROLS */
        div[data-baseweb="select"][aria-disabled="true"] > div,
        div[data-baseweb="input"]:has(input:disabled),
        div[data-baseweb="base-input"]:has(input:disabled) {
            background-color: #EFF6F0 !important;
            border-color: #B7DFB9 !important;
            opacity: 0.92 !important;
        }

        /* DROPDOWN POPOVER: COMPACT FONT & FULL INSTRUMENT NAME */
        div[data-baseweb="popover"] {
            min-width: 270px !important;
            width: auto !important;
            max-width: 440px !important;
        }
        ul[data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="popover"] li,
        div[data-baseweb="popover"] [role="option"] {
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            color: #0A2540 !important;
            white-space: normal !important;
            word-break: break-word !important;
            line-height: 1.3 !important;
            padding-top: 5px !important;
            padding-bottom: 5px !important;
        }
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="input"]:focus-within {
            border-color: #2E7D32 !important;
            box-shadow: 0 0 0 1px #2E7D32 !important;
        }

        div[data-baseweb="select"],
        div[data-baseweb="select"] * {
            cursor: pointer !important;
            user-select: none !important;
            -webkit-user-select: none !important;
        }
        div[data-baseweb="select"] input {
            caret-color: transparent !important;
            pointer-events: none !important;
        }

        /* MAIN CONTENT BUTTONS - EXACT 38PX HEIGHT TO MATCH INPUTS */
        .main .stButton > button[kind="primary"],
        div[role="dialog"] .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #388E3C 0%, #2E7D32 100%) !important;
            color: #FFFFFF !important;
            font-weight: 700 !important;
            font-size: 0.81rem !important;
            border: none !important;
            border-radius: 7px !important;
            padding: 0 0.9rem !important;
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            white-space: nowrap !important;
        }
        .main .stButton > button[kind="primary"] p,
        div[role="dialog"] .stButton > button[kind="primary"] p {
            color: #FFFFFF !important;
            font-weight: 700 !important;
            font-size: 0.81rem !important;
            white-space: nowrap !important;
        }
        .main .stButton > button[kind="secondary"],
        .stDownloadButton > button,
        div[role="dialog"] .stButton > button[kind="secondary"] {
            background-color: #E8F5E9 !important;
            color: #0A2540 !important;
            font-weight: 600 !important;
            font-size: 0.80rem !important;
            border: 1px solid #81C784 !important;
            border-radius: 7px !important;
            padding: 0 0.85rem !important;
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            white-space: nowrap !important;
        }
        .main .stButton > button[kind="secondary"] p,
        .stDownloadButton > button p,
        div[role="dialog"] .stButton > button[kind="secondary"] p {
            color: #0A2540 !important;
            font-weight: 600 !important;
            font-size: 0.80rem !important;
            white-space: nowrap !important;
        }

        /* METRICS */
        [data-testid="stMetric"] {
            background-color: #F1F8F3 !important;
            border: 1px solid #C8E6C9 !important;
            border-radius: 8px !important;
            padding: 7px 10px !important;
        }
        [data-testid="stMetricLabel"] p {
            color: #1B4F72 !important;
            font-weight: 700 !important;
            font-size: 0.75rem !important;
            white-space: nowrap !important;
        }
        [data-testid="stMetricValue"] {
            color: #0A2540 !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-weight: 800 !important;
            font-size: 1.02rem !important;
        }

        /* STATUS BADGES */
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            padding: 1px 8px;
            border-radius: 999px;
            font-size: 0.71rem;
            font-weight: 700;
            line-height: 1.35;
            white-space: nowrap;
        }
        .badge-pass {
            background-color: #DCFCE7;
            color: #15803D;
            border: 1px solid #86EFAC;
        }
        .badge-fail {
            background-color: #FEE2E2;
            color: #B91C1C;
            border: 1px solid #FCA5A5;
        }
        .badge-warn {
            background-color: #FEF3C7;
            color: #B45309;
            border: 1px solid #FDE68A;
        }

        .eval-result-box {
            background-color: #FFFFFF;
            border: 1px solid #C8E6C9;
            border-radius: 7px;
            padding: 6px 10px;
            margin-top: 4px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 0.80rem;
            color: #0A2540;
        }
        .eval-result-pass {
            border-left: 4px solid #2E7D32;
            background-color: #F4FBF6;
        }
        .eval-result-fail {
            border-left: 4px solid #C62828;
            background-color: #FEF2F2;
        }

        /* META BAR & LAB TABLES */
        .history-meta-bar {
            background-color: #FFFFFF;
            border: 1px solid #DCEEE0;
            border-radius: 6px;
            padding: 5px 10px;
            margin-bottom: 6px;
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            color: #0A2540;
            font-size: 0.77rem;
        }
        .date-pill {
            background-color: #2E7D32;
            color: #FFFFFF;
            padding: 1px 7px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            font-size: 0.74rem;
        }
        .lot-pill {
            background-color: #E3F2FD;
            color: #0A2540;
            border: 1px solid #90CAF9;
            padding: 1px 7px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            font-size: 0.74rem;
        }

        .lab-table-wrapper {
            max-height: 280px;
            overflow-x: auto;
            overflow-y: auto;
            border: 1px solid #DCEEE0;
            border-radius: 6px;
            background-color: #FFFFFF;
            margin-bottom: 4px;
        }
        .lab-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.77rem;
            color: #0A2540;
        }
        .lab-table thead th {
            position: sticky;
            top: 0;
            background-color: #F1F8F3;
            color: #334E68;
            font-weight: 700;
            padding: 5px 8px;
            border-bottom: 1px solid #C8E6C9;
            white-space: nowrap;
            z-index: 1;
        }
        .lab-table tbody td {
            padding: 4px 8px;
            border-bottom: 1px solid #F0F7F1;
            font-variant-numeric: tabular-nums;
            font-weight: 500;
            white-space: nowrap;
        }
        .lab-table tbody tr:nth-child(even) {
            background-color: #FAFDFB;
        }
        .lab-table tbody tr:hover {
            background-color: #E8F5E9;
        }
        .text-left { text-align: left !important; }
        .text-right { text-align: right !important; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; }
        .text-center { text-align: center !important; }

        /* COMPACT LIST */
        .overview-list-card {
            background-color: #FFFFFF;
            border: 1px solid #DCEEE0;
            border-radius: 8px;
            margin-top: 6px;
            margin-bottom: 10px;
            overflow: hidden;
        }
        .overview-group-header {
            display: grid;
            grid-template-columns: 2.3fr 1.2fr 1fr 0.9fr 0.8fr;
            align-items: center;
            padding: 6px 12px;
            background-color: #F4FAF6;
            border-bottom: 1px solid #DCEEE0;
            font-size: 0.73rem;
            font-weight: 700;
            color: #52667A;
        }
        .overview-mach-title {
            color: #0A2540;
            font-weight: 800;
            font-size: 0.78rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        details.overview-item {
            border-bottom: 1px solid #F0F5F1;
            background-color: #FFFFFF;
        }
        details.overview-item:last-child {
            border-bottom: none;
        }
        summary.overview-row {
            display: grid;
            grid-template-columns: 2.3fr 1.2fr 1fr 0.9fr 0.8fr;
            align-items: center;
            padding: 6px 12px;
            font-size: 0.78rem;
            color: #0A2540;
            cursor: pointer;
            list-style: none;
        }
        summary.overview-row::-webkit-details-marker {
            display: none;
        }
        summary.overview-row:hover {
            background-color: #F4FBF6;
        }
        .item-name-cell {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            color: #0A2540;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .item-avatar {
            width: 21px;
            height: 21px;
            border-radius: 50%;
            background-color: #E6F4EA;
            border: 1px dashed #66BB6A;
            color: #2E7D32;
            font-size: 0.68rem;
            font-weight: 800;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .item-lot-cell {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.76rem;
            font-weight: 700;
            color: #1B5E20;
        }
        .item-date-cell {
            color: #64748B;
            font-size: 0.76rem;
            font-variant-numeric: tabular-nums;
        }
        .item-action-cell {
            text-align: right;
            font-size: 0.74rem;
            font-weight: 600;
            color: #2E7D32;
        }
        .overview-subbox {
            padding: 6px 14px 10px 38px;
            background-color: #FAFDFB;
            border-top: 1px dashed #DCEEE0;
        }
    </style>
    """)


# ==============================================================================
# 3. SHARED UI HELPERS
# ==============================================================================
def init_theme(page_title: str = "EQA Six Sigma System", layout: str = "wide", initial_sidebar_state: str = "expanded"):
    st.set_page_config(
        page_title=page_title,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )
    inject_custom_css()
    render_pending_popup()


def render_sidebar_menu(
    brand_title: str,
    brand_subtitle: str,
    menu_items: list,
    section_label: str = "NAVIGATION",
    state_key: str = "active_menu_page",
) -> str:
    if not menu_items:
        return ""

    valid_labels = []
    for m in menu_items:
        if len(m) >= 3 and m[2]:
            valid_labels.extend([sub[0] for sub in m[2]])
        else:
            valid_labels.append(m[0])

    default_page = valid_labels[0]
    if state_key not in st.session_state or st.session_state[state_key] not in valid_labels:
        st.session_state[state_key] = default_page

    def _switch_menu_page(target_page: str):
        st.session_state[state_key] = target_page

    with st.sidebar:
        render_html(f"""
        <div class="sidebar-brand">
            <div class="sidebar-brand-title">{brand_title}</div>
            <div class="sidebar-brand-sub">{brand_subtitle}</div>
        </div>
        <div class="sidebar-section-label">{section_label}</div>
        """)

        for item in menu_items:
            item_label = item[0]
            item_icon = item[1] if len(item) > 1 else ""
            sub_items = item[2] if len(item) >= 3 else None

            if sub_items:
                sub_labels = [s[0] for s in sub_items]
                is_group_active = st.session_state[state_key] in sub_labels
                arrow = "▾" if is_group_active else "▸"
                btn_text = f"{item_icon}  {item_label} {arrow}" if item_icon else f"{item_label} {arrow}"
                target_on_click = st.session_state[state_key] if is_group_active else sub_labels[0]

                st.button(
                    btn_text,
                    key=f"nav_btn_{state_key}_{item_label}",
                    type="primary" if is_group_active else "secondary",
                    use_container_width=True,
                    on_click=_switch_menu_page,
                    args=(target_on_click,),
                )

                if is_group_active:
                    for sub_label, sub_icon in sub_items:
                        is_sub_active = st.session_state[state_key] == sub_label
                        sub_text = f"{sub_icon}  {sub_label}" if sub_icon else f"↳ {sub_label}"
                        st.button(
                            sub_text,
                            key=f"nav_sub_{state_key}_{sub_label}",
                            type="primary" if is_sub_active else "secondary",
                            use_container_width=True,
                            on_click=_switch_menu_page,
                            args=(sub_label,),
                        )
            else:
                is_active = st.session_state[state_key] == item_label
                btn_text = f"{item_icon}  {item_label}" if item_icon else item_label
                st.button(
                    btn_text,
                    key=f"nav_btn_{state_key}_{item_label}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                    on_click=_switch_menu_page,
                    args=(item_label,),
                )

    return st.session_state[state_key]


def render_page_banner(title: str, desc: str = ""):
    desc_html = f'<div class="page-banner-desc">{desc}</div>' if desc else ""
    render_html(f"""
    <div class="page-banner">
        <div class="page-banner-title">{title}</div>
        {desc_html}
    </div>
    """)


def format_status_badge_html(status_val: str) -> str:
    s = str(status_val).strip().upper()
    if s in ("PASS", "ĐẠT", "ACTIVE", "✅ ĐẠT", "✓ ACTIVE"):
        label = "✓ Active" if "ACTIVE" in s else "✓ PASS"
        return f'<span class="status-badge badge-pass">{label}</span>'
    if s in ("FAIL", "TRƯỢT", "KHÔNG ĐẠT", "❌ TRƯỢT"):
        return '<span class="status-badge badge-fail">✕ FAIL</span>'
    if s in ("INACTIVE", "⏸ INACTIVE"):
        return '<span class="status-badge badge-warn">⏸ Inactive</span>'
    return f'<span class="status-badge badge-warn">{status_val}</span>'


# ==============================================================================
# 4. STATE PERSISTENCE & STEP-BY-STEP LOCKING HELPERS
# ==============================================================================
def persistent_selectbox(
    container,
    label: str,
    options: list,
    persist_key: str,
    default_value=None,
    format_func=None,
    disabled: bool = False,
    on_value_change=None,
    label_visibility: str = "visible",
):
    """
    Selectbox có State Persistence:
    - Lưu giá trị vào persist_key (non-widget key) để không bao giờ bị Streamlit reset
      về index 0 khi Save, khi format_func đổi nhãn (thêm ✅ / số lots), đóng popup OK,
      hay khi chuyển qua lại giữa các tab Sidebar.
    """
    if not options:
        return None

    saved_val = st.session_state.get(persist_key)
    if saved_val not in options:
        if default_value is not None and default_value in options:
            saved_val = default_value
        else:
            saved_val = options[0]
        st.session_state[persist_key] = saved_val

    w_key = f"_w_{persist_key}"
    st.session_state[w_key] = saved_val

    def _handle_change():
        new_val = st.session_state.get(w_key)
        if new_val in options:
            st.session_state[persist_key] = new_val
            if on_value_change is not None:
                on_value_change(new_val)

    kwargs = {
        "label": label,
        "options": options,
        "key": w_key,
        "disabled": disabled,
        "on_change": _handle_change,
        "label_visibility": label_visibility,
    }
    if format_func is not None:
        kwargs["format_func"] = format_func

    val = container.selectbox(**kwargs)
    if val in options:
        st.session_state[persist_key] = val
    return val


def render_step_lock_header(
    title_md: str,
    lock_key: str,
    step_label: str = "Step 1",
    lock_also_keys: list = None,
    unlock_also_keys: list = None,
) -> bool:
    """
    Hiển thị thanh tiêu đề Bước kèm nút Lock / Unlock (Step-by-Step Locking).
    Trả về True nếu bước hiện tại đang bị khóa.
    """
    if lock_key not in st.session_state:
        st.session_state[lock_key] = False

    is_locked = bool(st.session_state[lock_key])

    def _toggle_lock():
        new_state = not bool(st.session_state.get(lock_key, False))
        st.session_state[lock_key] = new_state
        if new_state and lock_also_keys:
            for k in lock_also_keys:
                st.session_state[k] = True
        elif not new_state and unlock_also_keys:
            for k in unlock_also_keys:
                st.session_state[k] = False

    hdr_l, hdr_r = st.columns([3.8, 1.2], vertical_alignment="center")
    with hdr_l:
        lock_suffix = " &nbsp; `🔒 Locked`" if is_locked else ""
        st.markdown(f"{title_md}{lock_suffix}")
    with hdr_r:
        btn_label = (
            f":material/lock_open: Unlock {step_label}"
            if is_locked
            else f":material/lock: Lock {step_label}"
        )
        st.button(
            btn_label,
            key=f"_btn_lock_{lock_key}",
            type="primary" if is_locked else "secondary",
            use_container_width=True,
            on_click=_toggle_lock,
        )

    return is_locked
