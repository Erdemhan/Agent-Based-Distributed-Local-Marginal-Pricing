import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from agents.market_operator import MarketOperator
from utils.data_io import load_config, export_to_excel, generate_default_template

# Design System Tokens (Ritualistic Sage theme)
COLOR_BACKGROUND = "#F4F3EF"
COLOR_CARD = "#EAE9E3"
COLOR_BORDER = "#D3D0C6"
COLOR_TEXT_PRIMARY = "#2A3439"
COLOR_TEXT_SECONDARY = "#3A474D"
COLOR_TEXT_MUTED = "#6B7280"

COLOR_SLACK = "#4A7C59"
COLOR_LOAD = "#8E9A90"
COLOR_DER = "#2E7D32"
COLOR_PROSUMER = "#E65100"
COLOR_SELECTED = "#E63946"

def draw_topology_fig(df_config, selected_bus=None):
    import pandapower as pp
    import pandapower.networks as pn
    net = pn.case33bw()
    
    # Dikey Koordinat Haritalaması (Bara 1 en üstte, omurga aşağı doğru uzanır)
    coords = [
        # Ana Besleme Hattı (Bara 1 - 18) - Dikey olarak aşağı doğru (dy = -2.0)
        (0, 0), (0, -2.0), (0, -4.0), (0, -6.0), (0, -8.0), (0, -10.0), (0, -12.0), (0, -14.0), (0, -16.0), (0, -18.0), (0, -20.0), (0, -22.0), (0, -24.0), (0, -26.0), (0, -28.0), (0, -30.0), (0, -32.0), (0, -34.0),
        # 1. Yan Kol (Bara 19 - 22) - Bara 2'den sola doğru yatay, sonra aşağı (x = -0.4)
        (-0.4, -2.0), (-0.4, -4.0), (-0.4, -6.0), (-0.4, -8.0),
        # 2. Yan Kol (Bara 23 - 25) - Bara 3'ten sağa doğru yatay, sonra aşağı (x = 0.8)
        (0.8, -4.0), (0.8, -6.0), (0.8, -8.0),
        # 3. Yan Kol (Bara 26 - 33) - Bara 6'dan sağa doğru yatay, sonra aşağı (x = 0.4)
        (0.4, -10.0), (0.4, -12.0), (0.4, -14.0), (0.4, -16.0), (0.4, -18.0), (0.4, -20.0), (0.4, -22.0), (0.4, -24.0)
    ]
    
    fig = go.Figure()
    
    # 1. Hatları Çiz (Edges)
    edge_x = []
    edge_y = []
    for idx, line in net.line.iterrows():
        if not line.in_service:
            continue
        f_bus = int(line.from_bus)
        t_bus = int(line.to_bus)
        x0, y0 = coords[f_bus]
        x1, y1 = coords[t_bus]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=2, color='#A3A3A3'),
        hoverinfo='none',
        mode='lines',
        showlegend=False
    ))
    
    # 2. Baraları Çiz (Nodes)
    node_x = [coords[i][0] for i in range(33)]
    node_y = [coords[i][1] for i in range(33)]
    
    # Rollerine göre renklendir
    colors = []
    sizes = []
    symbols = []
    role_colors = {
        "Slack/Grid": COLOR_SLACK,
        "PQ Load": COLOR_LOAD,
        "DER": COLOR_DER,
        "Prosumer": COLOR_PROSUMER
    }
    
    # st.data_editor tarafından üretilen df_config'i sirala
    df_sorted = df_config.sort_values("bus_id")
    
    for idx, row in df_sorted.iterrows():
        role = row["role"]
        bus_id = int(row["bus_id"])
        
        colors.append(role_colors.get(role, COLOR_LOAD))
        sizes.append(18 if role != "Slack/Grid" else 22)
        symbols.append("circle" if role != "Slack/Grid" else "diamond")
            
    # Hover (Bilgi Kartı) Metinleri
    hover_texts = []
    for idx, row in df_sorted.iterrows():
        bus_id = int(row["bus_id"])
        role = row["role"]
        pd_add = float(row["add_Pd_MW"])
        pmax = float(row["Pmax_MW"])
        hover_texts.append(
            f"Bara {bus_id}<br>Rol: {role}<br>Ek Yük: {pd_add:.2f} MW<br>Max Üretim: {pmax:.2f} MW"
        )
        
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=[str(i) for i in range(1, 34)],
        textposition="top center",
        textfont=dict(color=COLOR_TEXT_PRIMARY, size=10, weight='bold'),
        marker=dict(
            symbol=symbols,
            size=sizes,
            color=colors,
            line=dict(color=COLOR_BACKGROUND, width=1.5)
        ),
        hovertext=hover_texts,
        hoverinfo='text',
        showlegend=False
    ))
    
    fig.update_layout(
        showlegend=False,
        hovermode='closest',
        margin=dict(b=5, l=5, r=5, t=5),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1.2, 1.4], fixedrange=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-36, 1], fixedrange=True),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        height=750,
        dragmode=False
    )
    
    return fig


# Sayfa Genişliği ve Stil Ayarları
st.set_page_config(
    page_title="DLMP Ajan Tabanlı Simülasyon Arayüzü",
    page_icon="⚡",
    layout="wide"
)

# Custom Premium Styling (Ritualistic Sage CSS)
st.markdown(f"""
<style>
    /* Global Page & Theme Variable Overrides */
    :root, .stApp {{
        --background-color: {COLOR_BACKGROUND} !important;
        --secondary-background-color: {COLOR_CARD} !important;
        --text-color: {COLOR_TEXT_PRIMARY} !important;
        --primary-color: {COLOR_SLACK} !important;
    }}
    
    .stApp {{
        background-color: {COLOR_BACKGROUND} !important;
    }}
    [data-testid="stAppViewContainer"] {{
        background-color: {COLOR_BACKGROUND} !important;
        color: {COLOR_TEXT_SECONDARY} !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {COLOR_CARD} !important;
    }}
    [data-testid="stHeader"] {{
        background-color: rgba(0, 0, 0, 0) !important;
    }}
    
    /* Headers & Text */
    h1, h2, h3, h4, h5, h6 {{
        color: {COLOR_TEXT_PRIMARY} !important;
        font-family: 'Inter', sans-serif !important;
    }}
    
    /* Widget Labels & Markdown Paragraphs (Ensures text visibility) */
    label, [data-testid="stWidgetLabel"] p, .stWidgetLabel p, [data-testid="stMarkdownContainer"] p {{
        color: {COLOR_TEXT_PRIMARY} !important;
        font-weight: 600 !important;
    }}
    
    /* Input Fields, Text Inputs & Selectboxes Styling (Deep Transparency) */
    div[data-baseweb="select"] > div {{
        background-color: {COLOR_BACKGROUND} !important;
        color: {COLOR_TEXT_PRIMARY} !important;
        border: 1px solid {COLOR_BORDER} !important;
        border-radius: 8px !important;
    }}
    div[data-baseweb="select"] div, div[data-baseweb="select"] span {{
        background-color: transparent !important;
        color: {COLOR_TEXT_PRIMARY} !important;
    }}
    div[data-baseweb="input"] {{
        background-color: {COLOR_BACKGROUND} !important;
        color: {COLOR_TEXT_PRIMARY} !important;
        border: 1px solid {COLOR_BORDER} !important;
        border-radius: 8px !important;
    }}
    div[data-baseweb="input"] input, div[data-baseweb="input"] div {{
        background-color: transparent !important;
        color: {COLOR_TEXT_PRIMARY} !important;
    }}
    
    /* Increment/Decrement Buttons for Number Inputs */
    div[data-baseweb="input"] button {{
        background-color: {COLOR_BORDER} !important;
        color: {COLOR_TEXT_PRIMARY} !important;
    }}
    div[data-baseweb="input"] button:hover {{
        background-color: #BDB9AC !important;
    }}
    
    /* Focusable Card Containers */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: {COLOR_CARD} !important;
        border: 1px solid {COLOR_BORDER} !important;
        border-radius: 12px !important;
        padding: 18px !important;
        transition: all 0.25s ease-in-out !important;
        margin-bottom: 12px !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
        border-color: {COLOR_SLACK} !important;
        box-shadow: 0 4px 15px rgba(74, 124, 89, 0.12) !important;
    }}
    
    /* Buttons global style (Sage Accent) */
    div.stButton > button:first-child {{
        background-color: {COLOR_SLACK} !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }}
    div.stButton > button:first-child:hover {{
        background-color: #3b6448 !important;
        color: white !important;
    }}
    
    /* Card Styles */
    .metric-card {{
        background-color: {COLOR_CARD};
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
        border: 1px solid {COLOR_BORDER};
        text-align: center;
    }}
    .metric-title {{
        color: {COLOR_TEXT_MUTED};
        font-size: 14px;
        font-weight: 500;
        margin-bottom: 8px;
    }}
    .metric-value {{
        color: {COLOR_TEXT_PRIMARY};
        font-size: 28px;
        font-weight: 700;
        font-family: 'Inter', sans-serif;
    }}
    .status-box {{
        background-color: {COLOR_CARD};
        padding: 12px 20px;
        border-radius: 8px;
        border-left: 5px solid {COLOR_SLACK};
        color: {COLOR_TEXT_SECONDARY};
        border-top: 1px solid {COLOR_BORDER};
        border-right: 1px solid {COLOR_BORDER};
        border-bottom: 1px solid {COLOR_BORDER};
        margin-bottom: 25px;
    }}
</style>

<script>
    (function() {{
        const applyThemeJS = () => {{
            // Style dropdown wrapper divs
            document.querySelectorAll('div[data-baseweb="select"]').forEach(el => {{
                const control = el.firstElementChild;
                if (control) {{
                    control.style.backgroundColor = '#F4F3EF';
                    control.style.setProperty('background-color', '#F4F3EF', 'important');
                    control.style.color = '#2A3439';
                    control.style.setProperty('color', '#2A3439', 'important');
                }}
                el.querySelectorAll('div').forEach(d => {{
                    d.style.backgroundColor = 'transparent';
                    d.style.setProperty('background-color', 'transparent', 'important');
                    d.style.color = '#2A3439';
                    d.style.setProperty('color', '#2A3439', 'important');
                }});
                el.querySelectorAll('span').forEach(s => {{
                    s.style.color = '#2A3439';
                    s.style.setProperty('color', '#2A3439', 'important');
                }});
            }});
            
            // Style input boxes
            document.querySelectorAll('div[data-baseweb="input"]').forEach(el => {{
                el.style.backgroundColor = '#F4F3EF';
                el.style.setProperty('background-color', '#F4F3EF', 'important');
                el.style.borderColor = '#D3D0C6';
                el.style.setProperty('border-color', '#D3D0C6', 'important');
                
                el.querySelectorAll('input').forEach(i => {{
                    i.style.color = '#2A3439';
                    i.style.setProperty('color', '#2A3439', 'important');
                }});
                
                el.querySelectorAll('div').forEach(d => {{
                    d.style.backgroundColor = 'transparent';
                    d.style.setProperty('background-color', 'transparent', 'important');
                }});
            }});
            
            // Set up Plotly click events and highlight selected node
            const gd = document.querySelector('.js-plotly-plot');
            const hiddenInput = Array.from(document.querySelectorAll('input')).find(el => el.ariaLabel === "hidden_selected_bus");
            
            if (gd && gd.data && gd.data.length >= 2) {{
                // Bind plotly click event once
                if (!gd.dataset.clickAttached) {{
                    gd.dataset.clickAttached = "true";
                    gd.on('plotly_click', function(data) {{
                        const point = data.points[0];
                        if (point && point.curveNumber === 1) {{
                            const clickedIndex = point.pointIndex;
                            const busId = clickedIndex + 1;
                            
                            // Highlight instantly in Plotly
                            highlightNodeJS(gd, clickedIndex);
                            
                            // Update Streamlit hidden input widget to trigger rerun
                            if (hiddenInput) {{
                                hiddenInput.value = String(busId);
                                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
                                nativeInputValueSetter.call(hiddenInput, String(busId));
                                const event = new Event('input', {{ bubbles: true }});
                                hiddenInput.dispatchEvent(event);
                            }}
                        }}
                    }});
                }}
                
                // Keep selected node highlighted based on hiddenInput value (e.g. from dropdown updates)
                if (hiddenInput && hiddenInput.value) {{
                    const currentSelectedId = parseInt(hiddenInput.value);
                    if (!isNaN(currentSelectedId)) {{
                        highlightNodeJS(gd, currentSelectedId - 1);
                    }}
                }}
            }}
        }};
        
        const highlightNodeJS = (gd, targetIndex) => {{
            const trace = gd.data[1];
            if (!trace || !trace.marker) return;
            
            // Store original colors and shapes
            if (!gd.dataset.originalColors) {{
                gd.dataset.originalColors = JSON.stringify(trace.marker.color);
                gd.dataset.originalSizes = JSON.stringify(trace.marker.size);
                gd.dataset.originalSymbols = JSON.stringify(trace.marker.symbol);
            }}
            
            const originalColors = JSON.parse(gd.dataset.originalColors);
            const originalSizes = JSON.parse(gd.dataset.originalSizes);
            const originalSymbols = JSON.parse(gd.dataset.originalSymbols);
            
            if (gd.dataset.currentSelectedIndex === String(targetIndex)) {{
                return; // Already highlighted
            }}
            
            const newColors = [...originalColors];
            const newSizes = [...originalSizes];
            const newSymbols = [...originalSymbols];
            
            // Apply selected styling (Red square, size 26)
            newColors[targetIndex] = '#E63946';
            newSizes[targetIndex] = 26;
            newSymbols[targetIndex] = 'square';
            
            gd.dataset.currentSelectedIndex = String(targetIndex);
            
            Plotly.restyle(gd, {{
                'marker.color': [newColors],
                'marker.size': [newSizes],
                'marker.symbol': [newSymbols]
            }}, [1]);
        }};
        
        applyThemeJS();
        setInterval(applyThemeJS, 250);
    }})();
</script>


""", unsafe_allow_html=True)

# Initialize session state for config_df
if "config_df" not in st.session_state:
    rows = []
    for bus_id in range(1, 34):
        role = "Slack/Grid" if bus_id == 1 else "PQ Load"
        c2_val = 0.020 if bus_id == 1 else 0.0
        c1_val = 80.0 if bus_id == 1 else 0.0
        rows.append({
            "bus_id": bus_id,
            "role": role,
            "add_Pd_MW": 0.0,
            "pf": 0.90,
            "Vmin_pu": 0.90,
            "Vmax_pu": 1.05,
            "Pmin_MW": 0.0,
            "Pmax_MW": 100.0 if bus_id == 1 else 0.0,
            "Qmin_MVAr": -100.0 if bus_id == 1 else 0.0,
            "Qmax_MVAr": 100.0 if bus_id == 1 else 0.0,

            "c2_min": c2_val,
            "c2_max": c2_val,
            "c1_min": c1_val,
            "c1_max": c1_val,
            "c0": 0.0
        })
    st.session_state.config_df = pd.DataFrame(rows)

# Başlık ve Açıklamalar
st.title("⚡ DLMP Agent-Based Simulation (ABM)")
st.caption("PandaPower & Ray RLlib Altyapılı Akıllı Şebeke Simülasyon Paneli")

# 1. Sidebar Yapılandırması
st.sidebar.header("📁 Girdi Dosyaları ve Ayarlar")

# Şablon İndirme Mekanizması
template_buffer = io.BytesIO()
generate_default_template(template_buffer)
template_buffer.seek(0)

btn_download = st.sidebar.download_button(
    label="📥 Varsayılan Excel Şablonunu İndir",
    data=template_buffer,
    file_name="varsayilan_sablon.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader(
    "Rol/Ajan Konfigürasyon Dosyası Yükleyin (.xlsx veya .mat)",
    type=["xlsx", "xls", "mat"]
)

if uploaded_file:
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("last_uploaded_file") != file_key:
        temp_file_name = f"temp_upload{os.path.splitext(uploaded_file.name)[1]}"
        with open(temp_file_name, "wb") as f:
            f.write(uploaded_file.getbuffer())
        try:
            parsed_df = load_config(temp_file_name)
            st.session_state.config_df = parsed_df
            st.session_state.last_uploaded_file = file_key
            st.sidebar.success("Dosyadan yeni konfigürasyon yüklendi!")
        except Exception as e:
            st.sidebar.error(f"Dosya okuma hatası: {e}")
        finally:
            if os.path.exists(temp_file_name):
                os.remove(temp_file_name)

st.sidebar.subheader("🌍 Küresel Ortam Koşulları")
season = st.sidebar.selectbox("Mevsim (Season)", ["Kış", "Yaz"], index=0)
case_time = st.sidebar.selectbox("Günün Saati (Case Time)", ["Gece", "Öğleden önce", "Öğle", "Akşam üstü"], index=2)
pdf_option = st.sidebar.selectbox("Maliyet Örnekleme PDF'i", ["Uniform", "Normal-Truncated", "Triangular", "Beta(2,2)-Bounded", "Lognormal-Truncated", "Two-Peak Mixture"], index=0)

output_file_name = st.sidebar.text_input("Çıktı Excel Dosya Adı", value="dlmp_sonuclari.xlsx")

st.sidebar.markdown("---")
# Slack/Grid Global Parametreleri
st.sidebar.subheader("🔌 Grid / Slack Maliyet Katsayıları")
grid_c2 = st.sidebar.number_input("Grid c2 (katsayı)", value=0.020, format="%.4f")
grid_c1 = st.sidebar.number_input("Grid c1 (katsayı)", value=80.0, format="%.2f")
grid_c0 = st.sidebar.number_input("Grid c0 (sabit)", value=0.0, format="%.2f")

# Market Operator Tanımla
@st.cache_resource
def get_market_operator():
    return MarketOperator()

mo = get_market_operator()
# Grid maliyetlerini güncelle
mo.grid_c2 = grid_c2
mo.grid_c1 = grid_c1
mo.grid_c0 = grid_c0

# Simülasyon Çalıştırma
run_simulation = st.sidebar.button("🚀 Simülasyonu Başlat", use_container_width=True)

if "latest_results" in st.session_state:
    import io
    from utils.data_io import export_to_excel
    
    excel_buffer = io.BytesIO()
    export_to_excel(excel_buffer, st.session_state.latest_results["mo"], st.session_state.latest_results["summary"])
    excel_buffer.seek(0)
    
    st.sidebar.download_button(
        label="📥 Sonuçları Excel Olarak İndir",
        data=excel_buffer,
        file_name=st.session_state.latest_results["output_file_name"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# 2. Main Page - Interactive Data Editor & Simulation Outputs
role_options = ["PQ Load", "DER", "Prosumer", "Slack/Grid"]

column_config = {
    "bus_id": st.column_config.NumberColumn("Bara ID", help="Bara Numarası (1-33)", disabled=True),
    "role": st.column_config.SelectboxColumn("Rolü", help="Ajanın şebekedeki rolü", options=role_options, required=True),
    "add_Pd_MW": st.column_config.NumberColumn("Ek Pd (MW)", help="Ek aktif yük talebi (MW)", min_value=0.0, max_value=10.0, step=0.01, format="%.4f"),
    "pf": st.column_config.NumberColumn("pf", help="Güç faktörü (0, 1]", min_value=0.01, max_value=1.0, step=0.01, format="%.2f"),
    "Vmin_pu": st.column_config.NumberColumn("Vmin (pu)", min_value=0.8, max_value=1.2, step=0.01, format="%.2f"),
    "Vmax_pu": st.column_config.NumberColumn("Vmax (pu)", min_value=0.8, max_value=1.2, step=0.01, format="%.2f"),
    "Pmin_MW": st.column_config.NumberColumn("Pmin (MW)", min_value=0.0, step=0.1, format="%.4f"),
    "Pmax_MW": st.column_config.NumberColumn("Pmax (MW)", min_value=0.0, step=0.1, format="%.4f"),
    "Qmin_MVAr": st.column_config.NumberColumn("Qmin (MVAr)", step=0.1, format="%.4f"),
    "Qmax_MVAr": st.column_config.NumberColumn("Qmax (MVAr)", step=0.1, format="%.4f"),
    "c2_min": st.column_config.NumberColumn("c2 Min", step=0.001, format="%.5f"),
    "c2_max": st.column_config.NumberColumn("c2 Max", step=0.001, format="%.5f"),
    "c1_min": st.column_config.NumberColumn("c1 Min", step=0.1, format="%.2f"),
    "c1_max": st.column_config.NumberColumn("c1 Max", step=0.1, format="%.2f"),
    "c0": st.column_config.NumberColumn("c0 Sabit", step=1.0, format="%.2f")
}

col_left_topology, col_right_editor = st.columns([2, 1])

# Initialize selected_bus_id
if "selected_bus_id" not in st.session_state:
    st.session_state.selected_bus_id = 1

# Hidden selected bus widget to bypass plotly rerun blinks
st.markdown('<div style="display:none;">', unsafe_allow_html=True)
hidden_selected_bus_val = st.text_input("hidden_selected_bus", value=str(st.session_state.selected_bus_id), key="hidden_selected_bus_widget")
st.markdown('</div>', unsafe_allow_html=True)

if hidden_selected_bus_val and hidden_selected_bus_val.isdigit():
    st.session_state.selected_bus_id = int(hidden_selected_bus_val)

selected_bus_id = st.session_state.selected_bus_id

with col_left_topology:
    st.subheader("🕸️ 33 Baralı Şebeke Topolojisi (Tıklanabilir)")
    st.markdown("Düzenlemek istediğiniz baraya **grafik üzerinden doğrudan tıklayabilir** veya sağdaki listeden seçebilirsiniz:")
    
    # Draw figure statically
    fig_topo = draw_topology_fig(st.session_state.config_df, selected_bus=None)
    
    # Show plotly chart statically (no rerun on select event)
    st.plotly_chart(
        fig_topo,
        use_container_width=True,
        key="topology_scatter",
        config={'displayModeBar': False, 'scrollZoom': False}
    )

with col_right_editor:
    st.subheader("✏️ Seçili Bara Editörü")
    
    # Card 1: Basic Info
    with st.container(border=True):
        st.markdown("### 🏷️ Temel Bilgiler")
        selected_bus_id = st.selectbox(
            "Düzenlenecek Bara Numarası:",
            range(1, 34),
            index=selected_bus_id - 1,
            key="bus_dropdown_selector"
        )
        st.session_state.selected_bus_id = selected_bus_id
        
        # Load properties of selected bus
        bus_row = st.session_state.config_df[st.session_state.config_df.bus_id == selected_bus_id].iloc[0]
        
        role = st.selectbox(
            "Ajan Rolü:",
            ["PQ Load", "DER", "Prosumer", "Slack/Grid"],
            index=["PQ Load", "DER", "Prosumer", "Slack/Grid"].index(bus_row["role"]),
            key="role_selectbox_editor"
        )
    
    # Dynamic fields based on role
    add_Pd_MW = 0.0
    pf = 0.90
    Pmin_MW = 0.0
    Pmax_MW = 0.0
    Qmin_MVAr = 0.0
    Qmax_MVAr = 0.0
    c2_min = 0.0
    c2_max = 0.0
    c1_min = 0.0
    c1_max = 0.0
    c0 = 0.0
    Vmin_pu = float(bus_row["Vmin_pu"])
    Vmax_pu = float(bus_row["Vmax_pu"])
    
    # Card 2: Power and Load Settings (Only if role is PQ Load or Prosumer)
    if role in ["PQ Load", "Prosumer"]:
        with st.container(border=True):
            st.markdown("### 📉 Güç & Yük Ayarları")
            add_Pd_MW = st.number_input("Ek Aktif Yük (add_Pd_MW - MW):", min_value=0.0, max_value=10.0, value=float(bus_row["add_Pd_MW"]), step=0.01, format="%.4f")
            pf = st.number_input("Güç Faktörü (pf):", min_value=0.01, max_value=1.0, value=float(bus_row["pf"]), step=0.01, format="%.2f")
        
    # Card 3: Generation & Cost Settings (Only if role is DER, Prosumer, or Slack/Grid)
    if role in ["DER", "Prosumer", "Slack/Grid"]:
        with st.container(border=True):
            st.markdown("### ⚡ Üretim & Maliyet Parametreleri")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                Pmin_MW = st.number_input("Min Üretim (Pmin - MW):", min_value=0.0, value=float(bus_row["Pmin_MW"]), step=0.1, format="%.4f")
                Qmin_MVAr = st.number_input("Min Reaktif (Qmin - MVAr):", value=float(bus_row["Qmin_MVAr"]), step=0.1, format="%.4f")
            with col_g2:
                Pmax_MW = st.number_input("Max Üretim (Pmax - MW):", min_value=0.0, value=float(bus_row["Pmax_MW"]), step=0.1, format="%.4f")
                Qmax_MVAr = st.number_input("Max Reaktif (Qmax - MVAr):", value=float(bus_row["Qmax_MVAr"]), step=0.1, format="%.4f")
                
            st.markdown("**Maliyet Katsayıları:**")
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                c2_min = st.number_input("c2 Min:", value=float(bus_row["c2_min"]), step=0.001, format="%.5f")
                c1_min = st.number_input("c1 Min:", value=float(bus_row["c1_min"]), step=0.1, format="%.2f")
            with col_c2:
                c2_max = st.number_input("c2 Max:", value=float(bus_row["c2_max"]), step=0.001, format="%.5f")
                c1_max = st.number_input("c1 Max:", value=float(bus_row["c1_max"]), step=0.1, format="%.2f")
                
            c0 = st.number_input("c0 Sabit Maliyet:", value=float(bus_row["c0"]), step=1.0, format="%.2f")
        
    # Card 4: Voltage Limits
    with st.container(border=True):
        st.markdown("### 📊 Gerilim Sınırları")
        Vmin_pu = st.number_input("Minimum Gerilim Limiti (Vmin - pu):", min_value=0.8, max_value=1.2, value=Vmin_pu, step=0.01, format="%.2f")
        Vmax_pu = st.number_input("Maksimum Gerilim Limiti (Vmax - pu):", min_value=0.8, max_value=1.2, value=Vmax_pu, step=0.01, format="%.2f")
    
    # Save the edited values back to config_df in session state
    idx_to_update = st.session_state.config_df[st.session_state.config_df.bus_id == selected_bus_id].index[0]
    st.session_state.config_df.at[idx_to_update, "role"] = role
    st.session_state.config_df.at[idx_to_update, "add_Pd_MW"] = add_Pd_MW
    st.session_state.config_df.at[idx_to_update, "pf"] = pf
    st.session_state.config_df.at[idx_to_update, "Pmin_MW"] = Pmin_MW
    st.session_state.config_df.at[idx_to_update, "Pmax_MW"] = Pmax_MW
    st.session_state.config_df.at[idx_to_update, "Qmin_MVAr"] = Qmin_MVAr
    st.session_state.config_df.at[idx_to_update, "Qmax_MVAr"] = Qmax_MVAr
    st.session_state.config_df.at[idx_to_update, "c2_min"] = c2_min
    st.session_state.config_df.at[idx_to_update, "c2_max"] = c2_max
    st.session_state.config_df.at[idx_to_update, "c1_min"] = c1_min
    st.session_state.config_df.at[idx_to_update, "c1_max"] = c1_max
    st.session_state.config_df.at[idx_to_update, "c0"] = c0
    st.session_state.config_df.at[idx_to_update, "Vmin_pu"] = Vmin_pu
    st.session_state.config_df.at[idx_to_update, "Vmax_pu"] = Vmax_pu

# Bulk editor in an expander below
with st.expander("📋 Toplu Bara Rol ve Parametre Düzenleme Listesi"):
    edited_df = st.data_editor(
        st.session_state.config_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        key="bulk_data_editor"
    )
    st.session_state.config_df = edited_df

status_container = st.empty()
metrics_container = st.empty()
tabs_container = st.empty()

# Durum Bilgisi Başlangıç
if run_simulation:
    status_container.markdown("""
    <div class="status-box" style="border-left-color: #3b82f6;">
        ⏳ <strong>Simülasyon Koşuyor:</strong> Düzenlenen veriler üzerinden PandaPower AC OPF çözülüyor, marjinal fiyatlar hesaplanıyor...
    </div>
    """, unsafe_allow_html=True)
    
    try:
        from utils.data_io import load_config_from_dataframe
        # Ajanları ve rolleri düzenlenmiş tablodan yükle
        load_config_from_dataframe(edited_df, mo, pdf_option)
        # Ortamı set et
        mo.set_environment(season, case_time)
        # Simülasyonu koştur
        summary = mo.run_market()
        
        # Sonuçları hafızaya kaydet, disk dosyası üretme
        st.session_state.latest_results = {
            "mo": mo,
            "summary": summary,
            "output_file_name": output_file_name
        }
        
        # Yeniden yükleme yaparak indirme butonunu göster
        st.rerun()
            
    except Exception as e:
        st.error(f"Simülasyon çözümü sırasında bir hata oluştu: {str(e)}")
        st.exception(e)

if "latest_results" in st.session_state:
    results = st.session_state.latest_results
    mo_res = results["mo"]
    summary_res = results["summary"]
    file_name_res = results["output_file_name"]
    
    status_container.markdown(f"""
    <div class="status-box" style="border-left-color: #22c55e;">
        🎉 <strong>Simülasyon Başarıyla Tamamlandı!</strong> Sonuçları sol menüdeki <strong>Sonuçları Excel Olarak İndir</strong> butonunu kullanarak kaydedebilirsiniz. 
        Aşağıdaki sekmelerden ayrıntıları inceleyebilirsiniz.
    </div>
    """, unsafe_allow_html=True)
    
    # 3. Metrik Kartlarını Göster
    with metrics_container.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Optimal Şebeke Maliyeti</div>
                <div class="metric-value">{summary_res['objective_cost']:.2f} $/h</div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Toplam Aktif Yük</div>
                <div class="metric-value">{summary_res['total_load_MW']:.4f} MW</div>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Toplam Aktif Hat Kaybı</div>
                <div class="metric-value">{summary_res['total_loss_MW']:.4f} MW</div>
            </div>
            """, unsafe_allow_html=True)
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Tüketici Toplam Faturası</div>
                <div class="metric-value">{summary_res['cost_to_load_total']:.2f} $/h</div>
            </div>
            """, unsafe_allow_html=True)
            
    # 4. Sekmeli Gösterim
    with tabs_container.container():
        tab_plots, tab_bus, tab_gen, tab_branch = st.tabs([
            "📊 Şebeke Grafikleri", 
            "📍 Bara Sonuçları", 
            "🔥 Jeneratör Sonuçları", 
            "⚡ Hat Sonuçları"
        ])
        
        # --- Sekme 1: Grafikler ---
        with tab_plots:
            st.subheader("Simülasyon Grafikleri")
            
            # Ajan bilgilerini dataframe'e dök
            bus_data = []
            for agent_id, agent in mo_res.agents.items():
                if not agent_id.startswith("slack_"): # Slack agent generates duplicates for reporting
                    bus_data.append({
                        "bus_id": agent.bus_id,
                        "role": agent.__class__.__name__.replace("Agent", ""),
                        "V_pu": agent.V_actual,
                        "DLMP_P": agent.DLMP_active,
                        "DLMP_Q": agent.DLMP_reactive
                    })
            df_bus_plot = pd.DataFrame(bus_data).sort_values("bus_id")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                # 1. Gerilim Profili
                fig_v = go.Figure()
                fig_v.add_trace(go.Scatter(
                    x=df_bus_plot["bus_id"], y=df_bus_plot["V_pu"],
                    mode='lines+markers', name='Bara Gerilimi (V_actual)',
                    line=dict(color='#3b82f6', width=2),
                    marker=dict(size=6)
                ))
                fig_v.add_trace(go.Scatter(
                    x=[1, 33], y=[0.90, 0.90],
                    mode='lines', name='Vmin Limiti (0.90 p.u.)',
                    line=dict(color='red', dash='dash')
                ))
                fig_v.add_trace(go.Scatter(
                    x=[1, 33], y=[1.05, 1.05],
                    mode='lines', name='Vmax Limiti (1.05 p.u.)',
                    line=dict(color='red', dash='dash')
                ))
                fig_v.update_layout(
                    title="Bara Gerilim Profili (Voltage Profile)",
                    xaxis_title="Bara No", yaxis_title="Gerilim (p.u.)",
                    legend=dict(x=0.01, y=0.99),
                    template="plotly_dark"
                )
                st.plotly_chart(fig_v, use_container_width=True)

            with col_right:
                # 2. DLMP Profili
                fig_dlmp = go.Figure()
                fig_dlmp.add_trace(go.Scatter(
                    x=df_bus_plot["bus_id"], y=df_bus_plot["DLMP_P"],
                    mode='lines+markers', name='Aktif Güç DLMP (λ_P)',
                    line=dict(color='#10b981', width=2),
                    marker=dict(size=6)
                ))
                fig_dlmp.add_trace(go.Scatter(
                    x=df_bus_plot["bus_id"], y=df_bus_plot["DLMP_Q"],
                    mode='lines+markers', name='Reaktif Güç DLMP (λ_Q)',
                    line=dict(color='#f59e0b', width=2),
                    marker=dict(size=6)
                ))
                fig_dlmp.update_layout(
                    title="Nodal Konumsal Marjinal Fiyatlar (DLMP)",
                    xaxis_title="Bara No", yaxis_title="Fiyat ($/MWh)",
                    legend=dict(x=0.01, y=0.99),
                    template="plotly_dark"
                )
                st.plotly_chart(fig_dlmp, use_container_width=True)

            col_bottom_left, col_bottom_right = st.columns(2)
            
            with col_bottom_left:
                # 3. Jeneratör Dispatçleri
                gen_data = []
                # Slack / Grid ekle
                gen_data.append({
                    "bus_id": "Grid (Bara 1)",
                    "Pg_MW": summary_res["grid_Pg_MW"]
                })
                # DER ve Prosumerler ekle
                for agent_id, agent in mo_res.agents.items():
                    if hasattr(agent, "Pg_dispatched") and not agent.id.startswith("slack_"):
                        gen_data.append({
                            "bus_id": f"Bara {agent.bus_id} ({agent.__class__.__name__.replace('Agent','')})",
                            "Pg_MW": agent.Pg_dispatched
                        })
                df_gen_plot = pd.DataFrame(gen_data)
                
                fig_gen = px.bar(
                    df_gen_plot, x="bus_id", y="Pg_MW",
                    title="Jeneratör Aktif Güç Dağıtımları (Pg MW)",
                    labels={"bus_id": "Jeneratör Konumu", "Pg_MW": "Üretim (MW)"},
                    color="Pg_MW", color_continuous_scale="Viridis",
                    template="plotly_dark"
                )
                st.plotly_chart(fig_gen, use_container_width=True)

            with col_bottom_right:
                # 4. Hat Yüklenmeleri
                branch_data = []
                for idx, line in mo_res.net.line.iterrows():
                    res_line = mo_res.net.res_line.loc[idx]
                    branch_data.append({
                        "Hat": f"{int(line.from_bus)+1} -> {int(line.to_bus)+1}",
                        "Yüklenme %": res_line.loading_percent
                    })
                df_branch_plot = pd.DataFrame(branch_data)
                
                fig_branch = px.bar(
                    df_branch_plot, x="Hat", y="Yüklenme %",
                    title="Hat Yüklenme Yüzdeleri (Branch Loading %)",
                    labels={"Hat": "Hat No", "Yüklenme %": "Yüklenme oranı (%)"},
                    color="Yüklenme %", color_continuous_scale="Reds",
                    template="plotly_dark"
                )
                fig_branch.add_shape(
                    type="line", line=dict(color="red", width=2, dash="dash"),
                    x0=-0.5, x1=len(df_branch_plot)-0.5, y0=100.0, y1=100.0
                )
                st.plotly_chart(fig_branch, use_container_width=True)
        
        # --- Sekme 2: Bara Sonuçları ---
        with tab_bus:
            st.subheader("Detaylı Bara Sonuç Tablosu")
            bus_rows = []
            for agent_id, agent in mo_res.agents.items():
                if not agent_id.startswith("slack_"):
                    bus_rows.append({
                        "Bara No": agent.bus_id,
                        "Ajan Kimliği": agent.id,
                        "Rolü": agent.__class__.__name__.replace("Agent", ""),
                        "Aktif Yük (MW)": getattr(agent, "Pd_total", 0.0),
                        "Reaktif Yük (MVAr)": getattr(agent, "Qd_total", 0.0),
                        "Gerilim (p.u.)": agent.V_actual,
                        "Açı (Derece)": agent.theta_actual,
                        "Aktif DLMP ($/MWh)": agent.DLMP_active,
                        "Reaktif DLMP ($/MVAr)": agent.DLMP_reactive,
                        "Fatura Maliyeti ($/h)": getattr(agent, "C2L", getattr(agent, "C2L_net", 0.0))
                    })
            df_bus_res = pd.DataFrame(bus_rows).sort_values("Bara No")
            st.dataframe(df_bus_res, use_container_width=True, hide_index=True)
            
        # --- Sekme 3: Jeneratör Sonuçları ---
        with tab_gen:
            st.subheader("Detaylı Jeneratör Üretim ve Maliyet Tablosu")
            gen_rows = []
            # Grid / Slack
            gen_rows.append({
                "Jeneratör Konumu": "Bara 1 (Grid)",
                "Pg Üretim (MW)": summary_res["grid_Pg_MW"],
                "Qg Üretim (MVAr)": summary_res["grid_Qg_MVAr"],
                "c2 (quadratic)": mo_res.grid_c2,
                "c1 (linear)": mo_res.grid_c1,
                "c0 (sabit)": mo_res.grid_c0,
                "Toplam Gelir ($/h)": summary_res["grid_Pg_MW"] * mo_res.agents["slack_1"].DLMP_active if "slack_1" in mo_res.agents else 0.0,
                "Net Kâr ($/h)": (summary_res["grid_Pg_MW"] * mo_res.agents["slack_1"].DLMP_active - (mo_res.grid_c2 * (summary_res["grid_Pg_MW"]**2) + mo_res.grid_c1 * summary_res["grid_Pg_MW"])) if "slack_1" in mo_res.agents else 0.0
            })
            # DER ve Prosumerlar
            for agent_id, agent in mo_res.agents.items():
                if hasattr(agent, "Pg_dispatched") and not agent.id.startswith("slack_"):
                    gen_rows.append({
                        "Jeneratör Konumu": f"Bara {agent.bus_id} ({agent.__class__.__name__.replace('Agent','')})",
                        "Pg Üretim (MW)": agent.Pg_dispatched,
                        "Qg Üretim (MVAr)": agent.Qg_dispatched,
                        "c2 (quadratic)": agent.c2,
                        "c1 (linear)": agent.c1,
                        "c0 (sabit)": agent.c0,
                        "Toplam Gelir ($/h)": agent.Revenue,
                        "Net Kâr ($/h)": agent.Profit
                    })
            df_gen_res = pd.DataFrame(gen_rows)
            st.dataframe(df_gen_res, use_container_width=True, hide_index=True)
            
        # --- Sekme 4: Hat Sonuçları ---
        with tab_branch:
            st.subheader("Detaylı Hat Akış ve Yük Tablosu")
            branch_rows = []
            for idx, line in mo_res.net.line.iterrows():
                res_line = mo_res.net.res_line.loc[idx]
                branch_rows.append({
                    "Hat ID": idx + 1,
                    "Gönderici (From Bus)": int(line.from_bus) + 1,
                    "Alıcı (To Bus)": int(line.to_bus) + 1,
                    "Gönderilen P (MW)": res_line.p_from_mw,
                    "Gönderilen Q (MVAr)": res_line.q_from_mvar,
                    "Alınan P (MW)": res_line.p_to_mw,
                    "Alınan Q (MVAr)": res_line.q_to_mvar,
                    "Aktif Güç Kaybı (MW)": res_line.pl_mw,
                    "Reaktif Güç Kaybı (MVAr)": res_line.ql_mvar,
                    "Hat Yüklenmesi (%)": res_line.loading_percent
                })
            df_branch_res = pd.DataFrame(branch_rows)
            st.dataframe(df_branch_res, use_container_width=True, hide_index=True)
else:
    status_container.markdown("""
    <div class="status-box">
        📌 <strong>Sistem Durumu:</strong> Hazır. Bara konfigürasyonlarını düzenleyebilir veya sol menüden 
        dosya yükleyerek <strong>Simülasyonu Başlat</strong> butonuna basabilirsiniz.
    </div>
    """, unsafe_allow_html=True)
