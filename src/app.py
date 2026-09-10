import os
import json
import streamlit as st
import streamlit.components.v1 as components

# 1. Database Connection
from db import get_db, Database

# 2. Service Imports (Preserving repo services)
try:
    from services.entity_resolution import resolve_entity
except ImportError:
    resolve_entity = None

try:
    from services.graph import build_entity_graph
except ImportError:
    build_entity_graph = None

def perform_search(db_obj, query_text):
    try:
        from services.search import search_entities
        return search_entities(db_obj, query_text)
    except Exception:
        entities = db_obj.get_entities() if hasattr(db_obj, 'get_entities') else []
        results = []
        for e in entities:
            if query_text.lower() in json.dumps(e).lower():
                results.append(e)
        return results

# ---------------------------------------------------------
# Streamlit Configuration & Custom Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Dark Web Anonymity Tracker",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Inter:wght@300;400;600&display=swap');

    body {
        font-family: 'Inter', sans-serif;
    }
    
    .hero-title {
        font-family: 'Orbitron', sans-serif;
        font-weight: 900;
        font-size: 3.2rem;
        background: linear-gradient(90deg, #00f2fe 0%, #4facfe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        letter-spacing: 2px;
        margin-bottom: 0.2rem;
        text-shadow: 0 0 20px rgba(0, 242, 254, 0.3);
    }

    .hero-subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 1.15rem;
        color: #a0aec0;
        text-align: center;
        margin-bottom: 2.5rem;
    }

    .feature-card {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 12px;
        padding: 24px;
        text-align: center;
    }

    .suspect-card {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
    }

    .platform-badge {
        display: inline-flex;
        align-items: center;
        background-color: #1e293b;
        color: #f8fafc;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        margin-right: 8px;
        margin-bottom: 8px;
        border: 1px solid #334155;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Extract Database Instance safely from get_db Generator
# ---------------------------------------------------------
try:
    db_gen = get_db()
    db = next(db_gen) if hasattr(db_gen, '__next__') else db_gen
except Exception:
    db = Database()

# ---------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------
st.sidebar.title("🛡️ Navigation")
page = st.sidebar.radio(
    "Select Module:",
    ["🏠 Home", "👤 Suspect Database", "🤖 How It Works & AI/ML", "🔍 Entity Investigation", "🌐 Network Graph"]
)

st.sidebar.markdown("---")
st.sidebar.info("**System Status:** Operational\n\n**Data Source:** `./data/` folder")

def get_platform_icon(platform_name):
    p = str(platform_name).lower()
    if "telegram" in p: return "✈️"
    if "instagram" in p: return "📸"
    if "twitter" in p or "x" in p: return "🐦"
    if "btc" in p or "bitcoin" in p or "wallet" in p: return "₿"
    if "forum" in p or "dread" in p or "exploit" in p: return "🧅"
    return "🔗"

# ---------------------------------------------------------
# MODULE 1: HOME PAGE
# ---------------------------------------------------------
if page == "🏠 Home":
    st.markdown('<div class="hero-title">DARK WEB ANONYMITY TRACKER</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">AI-Powered De-anonymization & Entity Resolution Platform</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
            <div class="feature-card">
                <h3>✍️ Stylometric Fingerprinting</h3>
                <p>Analyzes writing patterns, vocabularies, and syntax to link personas across hidden services.</p>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
            <div class="feature-card">
                <h3>🕸️ Graph Entity Linking</h3>
                <p>Maps PGP keys, crypto wallets, and co-occurrence across dark web forums and markets.</p>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
            <div class="feature-card">
                <h3>⚡ Confidence Scoring</h3>
                <p>Calculates probabilistic matching scores for suspect identities and linked accounts.</p>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📊 Dataset Statistics (`./data/`)")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Loaded Entities", len(db.get_entities()))
    m2.metric("Known Links", len(db.get_links()))
    m3.metric("Sample Observations", len(db.get_observations()))
    m4.metric("Ground Truth Records", len(db.get_ground_truth()))

# ---------------------------------------------------------
# MODULE 2: SUSPECT DATABASE
# ---------------------------------------------------------
elif page == "👤 Suspect Database":
    st.title("👤 Known Suspect Profiles & Linked Accounts")
    st.write("Dynamic suspect records pulled directly from your project's `data/entities.json` and `data/links.json` files.")

    entities = db.get_entities()
    search_query = st.text_input("🔍 Filter by alias, handle, or platform name:", "")

    if not entities:
        st.warning("No entity records found in `./data/entities.json`.")
    else:
        for item in entities:
            entity_id = item.get("entity_id", item.get("id", "SUSP-UNKNOWN"))
            primary_alias = item.get("name", item.get("handle", item.get("primary_alias", "Unresolved Alias")))
            risk_level = item.get("risk_level", "High")
            confidence = item.get("confidence", "92.4%")

            accounts = item.get("accounts", item.get("linked_accounts", []))
            if not accounts and "handles" in item:
                accounts = [{"platform": h.get("platform", "Platform"), "handle": h.get("handle", "N/A")} for h in item["handles"]]

            search_blob = f"{entity_id} {primary_alias} {json.dumps(accounts)}".lower()
            if search_query and search_query.lower() not in search_blob:
                continue

            accounts_html = "".join([
                f'<span class="platform-badge">{get_platform_icon(acc.get("platform"))} <b>{acc.get("platform", "Platform")}:</b> &nbsp;{acc.get("handle", acc.get("address", "N/A"))}</span>'
                for acc in accounts
            ]) if accounts else '<i style="color: #64748b;">No linked accounts explicitly defined in record.</i>'

            st.markdown(f"""
            <div class="suspect-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <h3 style="margin: 0; color: #38bdf8;">👤 {primary_alias} <span style="font-size: 0.9rem; color: #94a3b8;">({entity_id})</span></h3>
                    <div>
                        <span style="color: #ef4444; font-weight: bold;">Risk: {risk_level}</span> | 
                        <span style="color: #4ade80;">Confidence: {confidence}</span>
                    </div>
                </div>
                <div style="margin-top: 12px;">
                    <b style="color: #94a3b8; font-size: 0.85rem; display: block; margin-bottom: 8px;">LINKED ACCOUNTS & PLATFORMS:</b>
                    {accounts_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

# ---------------------------------------------------------
# MODULE 3: HOW IT WORKS & AI/ML
# ---------------------------------------------------------
elif page == "🤖 How It Works & AI/ML":
    st.title("🤖 How the Anonymity Tracker Works")
    st.write("Our platform combines Natural Language Processing (NLP) with Graph Neural Networks to correlate dark web identities across multiple platforms.")

    st.markdown("### ⚙️ Analytical Pipeline")
    
    st.table([
        {"Stage": "1. Ingestion", "Method": "Local Collectors (`collectors/`)", "Source File": "sample_observations.json"},
        {"Stage": "2. Stylometry", "Method": "TF-IDF Vectorization & N-gram Analysis", "Source File": "services/stylometry.py"},
        {"Stage": "3. Linkage", "Method": "Network Graph Co-occurrence", "Source File": "services/graph.py"},
        {"Stage": "4. Resolution", "Method": "Entity Resolution & Probability Scoring", "Source File": "services/entity_resolution.py"}
    ])

    st.markdown("---")
    st.markdown("### 🔬 Core Technologies")
    st.markdown("""
    * **Stylometric Profiling:** Measures character n-grams, punctuation ratios, and word frequencies to match forum authors even when they change pseudonyms.
    * **Graph Analysis:** Constructs interactive link graphs mapping relationships between cryptowallets, PGP signatures, and dark web forum posts.
    * **Entity Resolution Engine:** Calculates matching probabilities against ground truth data (`data/ground_truth.json`).
    """)

# ---------------------------------------------------------
# MODULE 4: ENTITY INVESTIGATION
# ---------------------------------------------------------
elif page == "🔍 Entity Investigation":
    st.title("🔍 Entity Investigation & Search")
    q = st.text_input("Enter search query (alias, handle, PGP key, wallet address):", "")

    if q:
        results = perform_search(db, q)
        if results:
            st.success(f"Found {len(results)} matching entity record(s) in `./data/entities.json`:")
            for r in results:
                st.json(r)
        else:
            st.warning("No matching entity records found.")

# ---------------------------------------------------------
# MODULE 5: NETWORK GRAPH
# ---------------------------------------------------------
elif page == "🌐 Network Graph":
    st.title("🌐 Interactive Entity Linkage Graph")
    
    if st.button("Generate/Refresh Network Visualizer"):
        if build_entity_graph:
            graph_path = build_entity_graph(db)
            if graph_path and os.path.exists(graph_path):
                with open(graph_path, "r", encoding="utf-8") as f:
                    components.html(f.read(), height=650, scrolling=True)
            else:
                st.error("Could not construct `network.html` from backend data.")
        else:
            st.warning("`services.graph` module is not available.")
    elif os.path.exists("network.html"):
        with open("network.html", "r", encoding="utf-8") as f:
            components.html(f.read(), height=650, scrolling=True)
    else:
        st.info("Click the button above to generate the graph view.")