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
uploaded_file = st.sidebar.file_uploader(
    "Veri Dosyanızı Yükleyin (CSV veya Excel)", type=["csv", "xlsx", "xls"]
)

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
        "Serve": [85, 80, 82, 78, 70, 75, 70, 80, 82, 85, 0, 0],
    })


# Mevki isimlerini standart kısaltmalara çevirme tablosu
# Kendi veri setinizdeki etiketler farklıysa buraya ekleyin.
POZ_MAP = {
    "OPPOSITE": "OP", "OPPOSITE HITTER": "OP", "OP": "OP",
    "OUTSIDE HITTER": "OH", "OUTSIDE": "OH", "OH": "OH",
    "MIDDLE BLOCKER": "MB", "MIDDLE": "MB", "MB": "MB",
    "SETTER": "ST", "ST": "ST", "S": "ST",
    "LIBERO": "L", "L": "L",
}


# Veri Temizleme ve Uyumlaştırma
def process_data(dataframe):
    column_mapping = {
        'player': 'Oyuncu',
        'position': 'Pozisyon',
        'attack': 'Spike',
        'spike': 'Spike',
        'block': 'Block',
        'set': 'Set',
        'dig': 'Dig',
        'receive': 'Receive',
        'serve': 'Serve',
        'oyuncu': 'Oyuncu',
        'pozisyon': 'Pozisyon',
    }

    dataframe.columns = [str(c).strip().lower() for c in dataframe.columns]
    dataframe = dataframe.rename(columns=column_mapping)

    required_cols = ['Oyuncu', 'Pozisyon', 'Spike', 'Block', 'Set', 'Dig', 'Receive', 'Serve']
    for col in required_cols:
        if col not in dataframe.columns:
            dataframe[col] = 0

    df_clean = dataframe[required_cols].copy()
    df_clean['Oyuncu'] = df_clean['Oyuncu'].fillna("Bilinmeyen").astype(str).str.strip()
    df_clean['Pozisyon'] = df_clean['Pozisyon'].fillna("-").astype(str).str.strip()

    # Mevki etiketlerini standartlaştır (OP, OH, MB, ST, L)
    poz_upper = df_clean['Pozisyon'].str.upper()
    df_clean['Pozisyon'] = poz_upper.map(POZ_MAP).fillna(poz_upper)

    num_cols = ['Spike', 'Block', 'Set', 'Dig', 'Receive', 'Serve']
    for col in num_cols:
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)

    # Aynı isimli oyuncuları benzersiz yap
    df_clean['Oyuncu'] = df_clean['Oyuncu'] + df_clean.groupby('Oyuncu').cumcount().map(
        lambda x: f"_{x}" if x > 0 else ""
    )
    return df_clean


# Dosya Yükleme
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            raw_df = pd.read_csv(uploaded_file)
        else:
            raw_df = pd.read_excel(uploaded_file)

        df = process_data(raw_df)
        st.success("Veri seti başarıyla yüklendi ve modele uyarlandı!")
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


# 3. Optimizasyon Motoru
def run_optimization(df_input, a, b, d, t, e, g):
    prob = pulp.LpProblem("Voleybol_Ideal_Takim", pulp.LpMaximize)

    oyuncular = df_input['Oyuncu'].tolist()
    pozisyonlar = ["Ot", "h1", "h2", "st", "m1", "m2", "lt"]

    spike = dict(zip(df_input['Oyuncu'], df_input['Spike']))
    block = dict(zip(df_input['Oyuncu'], df_input['Block']))
    set_stat = dict(zip(df_input['Oyuncu'], df_input['Set']))
    dig = dict(zip(df_input['Oyuncu'], df_input['Dig']))
    receive = dict(zip(df_input['Oyuncu'], df_input['Receive']))
    serve = dict(zip(df_input['Oyuncu'], df_input['Serve']))
    mevki = dict(zip(
        df_input['Oyuncu'],
        df_input['Pozisyon'].astype(str).str.strip().str.upper()
    ))

    # Karar değişkenleri (0-1 tamsayı). Sıralı argüman: sürümden bağımsız çalışır.
    x = {}
    for idx, i in enumerate(oyuncular):
        for p in pozisyonlar:
            x[i, p] = pulp.LpVariable(f"v_{idx}_{p}", 0, 1, pulp.LpInteger)

    # Amaç Fonksiyonu
    prob += pulp.lpSum([
        a * spike[i] * (x[i, "Ot"] + x[i, "h1"] + x[i, "h2"] + x[i, "m1"] + x[i, "m2"]) +
        b * block[i] * (x[i, "m1"] + x[i, "m2"]) +
        d * set_stat[i] * x[i, "st"] +
        e * dig[i] * (x[i, "lt"] + x[i, "h1"] + x[i, "h2"]) +
        t * receive[i] * (x[i, "lt"] + x[i, "h1"] + x[i, "h2"]) +
        g * serve[i] * (x[i, "Ot"] + x[i, "h1"] + x[i, "h2"] + x[i, "st"] + x[i, "m1"] + x[i, "m2"])
        for i in oyuncular
    ])

    # Kısıt 1: Her slota tam 1 oyuncu
    for p in pozisyonlar:
        prob += pulp.lpSum([x[i, p] for i in oyuncular]) == 1

    # Kısıt 2: Her oyuncu en fazla 1 slotta
    for i in oyuncular:
        prob += pulp.lpSum([x[i, p] for p in pozisyonlar]) <= 1

    # Kısıt 3: Slot -> izin verilen oyuncu mevkileri
    slot_mevki = {
        "Ot": ["OP"],
        "h1": ["OH"],
        "h2": ["OH"],
        "st": ["ST"],
        "m1": ["MB"],
        "m2": ["MB"],
        "lt": ["L"],
    }
    for i in oyuncular:
        for p in pozisyonlar:
            if mevki[i] not in slot_mevki[p]:
                prob += x[i, p] == 0

    # Solver
    solver = pulp.PULP_CBC_CMD(msg=False)
    prob.solve(solver)

    if pulp.LpStatus[prob.status] != "Optimal":
        return pd.DataFrame(), None

    secilenler = []
    for p in pozisyonlar:
        for i in oyuncular:
            val = pulp.value(x[i, p])
            if val is not None and val > 0.5:
                secilenler.append({
                    "Atanan Pozisyon": p,
                    "Oyuncu": i,
                    "Mevki": mevki[i],
                    "Spike": spike[i],
                    "Block": block[i],
                    "Set": set_stat[i],
                    "Dig": dig[i],
                    "Receive": receive[i],
                    "Serve": serve[i],
                })
    return pd.DataFrame(secilenler), pulp.value(prob.objective)


# Tab 2
with tab2:
    if st.button("🚀 İdeal Takımı Hesapla", type="primary"):
        if len(df) < 7:
            st.error("En az 7 oyuncu gerekli (6 saha + 1 libero).")
        else:
            res_df, score = run_optimization(df, alpha, beta, delta, theta, epsilon, gamma)

            if res_df.empty:
                st.error(
                    "Uygun kadro bulunamadı. Her mevkiden yeterli oyuncu olmalı: "
                    "1 OP, 2 OH, 1 ST, 2 MB, 1 L. "
                    "Veri setinizdeki 'Pozisyon' değerlerini 'Oyuncu Veri Seti' sekmesinden kontrol edin."
                )
            else:
                st.metric("Toplam Takım Verimlilik Skoru (Z)", f"{score:.2f}")
                st.subheader("Oluşturulan Sahadaki İlk 6 + Libero")

                st.dataframe(
                    res_df[["Atanan Pozisyon", "Oyuncu", "Mevki", "Spike", "Block", "Receive", "Dig", "Set", "Serve"]],
                    use_container_width=True,
                )

                st.subheader("Takım Profil Analizi")
                avg_stats = res_df[["Spike", "Block", "Set", "Dig", "Receive", "Serve"]].mean().reset_index()
                avg_stats.columns = ["İstatistik", "Değer"]

                fig = px.line_polar(
                    avg_stats, r='Değer', theta='İstatistik', line_close=True,
                    title="Seçilen Kadronun Ortalama Güç Dağılımı",
                )
                st.plotly_chart(fig, use_container_width=True)
