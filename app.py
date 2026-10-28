import streamlit as st
import pandas as pd
import pulp
import plotly.express as px

# 1. Sayfa Düzeni ve Başlık
st.set_page_config(page_title="Voleybol İdeal Takım Optimizasyonu", layout="wide")

st.title("🏐 Voleybol İdeal Takım Oluşturma Portalı")
st.markdown("""
Bu karar destek sistemi, **Tam Sayılı Programlama (Yöneylem Araştırması)** kullanarak 
belirlediğiniz stratejik ağırlıklara göre **en verimli kadroyu** otomatik oluşturur.
""")

# 2. Sol Panel (Sidebar) - Veri Yükleme ve Katsayı Ayarları
st.sidebar.header("1. Veri Kaynağı")
uploaded_file = st.sidebar.file_uploader("Veri Dosyanızı Yükleyin (CSV veya Excel)", type=["csv", "xlsx", "xls"])

st.sidebar.header("2. Strateji ve Katsayı Ağırlıkları")
st.sidebar.caption("Toplam katsayı etkisini belirlemek için slider'ları kullanın:")

alpha = st.sidebar.slider("Smaç (Spike - α)", 0.0, 1.0, 0.25, 0.05)
beta = st.sidebar.slider("Blok (Block - β)", 0.0, 1.0, 0.20, 0.05)
delta = st.sidebar.slider("Pas (Set - δ)", 0.0, 1.0, 0.15, 0.05)
theta = st.sidebar.slider("Manşet (Receive - θ)", 0.0, 1.0, 0.15, 0.05)
epsilon = st.sidebar.slider("Defans (Dig - ε)", 0.0, 1.0, 0.10, 0.05)
gamma = st.sidebar.slider("Servis (Serve - γ)", 0.0, 1.0, 0.15, 0.05)

# Örnek Veri Seti
@st.cache_data
def load_sample_data():
    return pd.DataFrame({
        "Oyuncu": [f"Oyuncu {i}" for i in range(1, 13)],
        "Pozisyon": ["OP", "OP", "OH", "OH", "OH", "ST", "ST", "MB", "MB", "MB", "L", "L"],
        "Spike": [90, 75, 85, 80, 70, 20, 15, 75, 80, 88, 0, 0],
        "Block": [65, 70, 60, 55, 50, 40, 30, 90, 85, 95, 0, 0],
        "Set": [0, 0, 10, 5, 0, 95, 88, 0, 0, 0, 10, 5],
        "Dig": [60, 65, 75, 80, 70, 60, 50, 30, 40, 25, 95, 90],
        "Receive": [0, 0, 80, 85, 75, 0, 0, 0, 0, 0, 95, 92],
        "Serve": [85, 80, 82, 78, 70, 75, 70, 80, 82, 85, 0, 0]
    })

# Veri Temizleme ve Güvenli Dönüştürme
def process_data(dataframe):
    column_mapping = {
        'player': 'Oyuncu',
        'position': 'Pozisyon',
        'attack': 'Spike',
        'block': 'Block',
        'set': 'Set',
        'dig': 'Dig',
        'receive': 'Receive',
        'serve': 'Serve'
    }
    
    dataframe.columns = [str(c).strip().lower() for c in dataframe.columns]
    dataframe = dataframe.rename(columns=column_mapping)
    
    required_cols = ['Oyuncu', 'Pozisyon', 'Spike', 'Block', 'Set', 'Dig', 'Receive', 'Serve']
    for col in required_cols:
        if col not in dataframe.columns:
            dataframe[col] = 0
            
    df_clean = dataframe[required_cols].copy()
    
    # Oyuncu isimlerini kesinlikle String yapalım ve boşlukları silelim
    df_clean['Oyuncu'] = df_clean['Oyuncu'].fillna("Bilinmeyen").astype(str).str.strip()
    df_clean['Pozisyon'] = df_clean['Pozisyon'].fillna("-").astype(str).str.strip()
    
    # Sayısal değerlerdeki hataları temizleyelim
    num_cols = ['Spike', 'Block', 'Set', 'Dig', 'Receive', 'Serve']
    for col in num_cols:
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
        
    # Yinelenen (Aynı isimdeki) oyuncuları benzersiz yapalım
    df_clean['Oyuncu'] = df_clean['Oyuncu'] + df_clean.groupby('Oyuncu').cumcount().map(lambda x: f"_{x}" if x > 0 else "")
    
    return df_clean

# Dosya Yükleme
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            raw_df = pd.read_csv(uploaded_file)
        else:
            raw_df = pd.read_excel(uploaded_file)
            
        df = process_data(raw_df)
        st.success("Kaggle veri seti başarıyla yüklendi ve modele uyarlandı!")
    except Exception as e:
        st.error(f"Dosya işlenirken hata oluştu: {e}")
        df = load_sample_data()
else:
    st.info("💡 CSV veya Excel yüklemediniz. Örnek veri seti kullanılıyor.")
    df = load_sample_data()

# Sekmeler
tab1, tab2 = st.tabs(["📊 Oyuncu Veri Seti", "⚡ Optimizasyon ve Sonuçlar"])

with tab1:
    st.subheader("Mevcut Oyuncu Havuzu (İşlenmiş Veri)")
    st.dataframe(df, use_container_width=True)

# 3. Optimizasyon Motoru (PuLP) - Güvenli Liste Sözlük Yapısı
def run_optimization(df_input, a, b, d, t, e, g):
    prob = pulp.LpProblem("Voleybol_Ideal_Takim", pulp.LpMaximize)
    
    oyuncular = df_input['Oyuncu'].tolist()
    pozisyonlar = ["Ot", "h1", "h2", "st", "m1", "m2", "lt"]
    
    # Sözlük tanımları
    spike = dict(zip(df_input['Oyuncu'], df_input['Spike']))
    block = dict(zip(df_input['Oyuncu'], df_input['Block']))
    set_stat = dict(zip(df_input['Oyuncu'], df_input['Set']))
    dig = dict(zip(df_input['Oyuncu'], df_input['Dig']))
    receive = dict(zip(df_input['Oyuncu'], df_input['Receive']))
    serve = dict(zip(df_input['Oyuncu'], df_input['Serve']))

    # Değişken Tanimlama (Liste İndeksli Hata Yapmayan Yapı)
    x = pulp.LpVariable.dicts("Atama", (oyuncular, pozisyonlar), cat="Binary")

    # Amaç Fonksiyonu
    prob += pulp.lpSum([
        a * spike[i] * (x[i]["Ot"] + x[i]["h1"] + x[i]["h2"] + x[i]["m1"] + x[i]["m2"]) +
        b * block[i] * (x[i]["m1"] + x[i]["m2"]) +
        d * set_stat[i] * x[i]["st"] +
        e * dig[i] * (x[i]["lt"] + x[i]["h1"] + x[i]["h2"]) +
        t * receive[i] * (x[i]["lt"] + x[i]["h1"] + x[i]["h2"]) +
        g * serve[i] * (x[i]["Ot"] + x[i]["h1"] + x[i]["h2"] + x[i]["st"] + x[i]["m1"] + x[i]["m2"])
        for i in oyuncular
    ])

    # Kısıtlar
    for p in pozisyonlar:
        prob += pulp.lpSum([x[i][p] for i in oyuncular]) == 1

    for i in oyuncular:
        prob += pulp.lpSum([x[i][p] for p in pozisyonlar]) <= 1

    # Solver
    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)

    secilenler = []
    for p in pozisyonlar:
        for i in oyuncular:
            if pulp.value(x[i][p]) == 1:
                secilenler.append({
                    "Atanan Pozisyon": p,
                    "Oyuncu": i,
                    "Mevki": df_input.loc[df_input['Oyuncu'] == i, 'Pozisyon'].values[0] if 'Pozisyon' in df_input.columns else "-",
                    "Spike": spike[i],
                    "Block": block[i],
                    "Set": set_stat[i],
                    "Dig": dig[i],
                    "Receive": receive[i],
                    "Serve": serve[i]
                })
    return pd.DataFrame(secilenler), pulp.value(prob.objective)

# Tab 2
with tab2:
    if st.button("🚀 İdeal Takımı Hesapla", type="primary"):
        res_df, score = run_optimization(df, alpha, beta, delta, theta, epsilon, gamma)
        
        st.metric("Toplam Takım Verimlilik Skoru (Z)", f"{score:.2f}")
        st.subheader("Oluşturulan Sahadaki İlk 6 + Libero")
        
        st.dataframe(res_df[["Atanan Pozisyon", "Oyuncu", "Mevki", "Spike", "Block", "Receive", "Set", "Serve"]], use_container_width=True)
        
        st.subheader("Takım Profil Analizi")
        avg_stats = res_df[["Spike", "Block", "Set", "Dig", "Receive", "Serve"]].mean().reset_index()
        avg_stats.columns = ["İstatistik", "Değer"]
        
        fig = px.line_polar(avg_stats, r='Değer', theta='İstatistik', line_close=True, title="Seçilen Kadronun Ortalama Güç Dağılımı")
        st.plotly_chart(fig, use_container_width=True)
    
