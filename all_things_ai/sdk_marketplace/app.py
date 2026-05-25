"""
SDK Connector Marketplace — Hackathon Demo

Run with:
  FIVETRAN_API_KEY=xxx FIVETRAN_API_SECRET=yyy FIVETRAN_GROUP_ID=zzz \
  python3 -m streamlit run app.py

Clicking "Save & Test Connection" automatically deploys the connector code
and creates the connection in Fivetran — no manual package_id needed.
"""

import json
import os
import re
import subprocess
import tempfile
from base64 import b64encode
from pathlib import Path

import anthropic
import requests
import streamlit as st

# ── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT       = Path(__file__).resolve().parent.parent.parent
CONNECTORS_DIR  = REPO_ROOT / "connectors"
FIVETRAN_API    = "https://api.fivetran.com/v1"
FIVETRAN_BIN    = "/Users/monica.dholwani/Fivetran/fivetran_connector_sdk/connectors/newsapi/myenv/bin/fivetran"

# Startup env vars
ENV = {
    "api_key":    os.environ.get("FIVETRAN_API_KEY", ""),
    "api_secret": os.environ.get("FIVETRAN_API_SECRET", ""),
    "group_id":   os.environ.get("FIVETRAN_GROUP_ID", ""),
    "anthropic_key": os.environ.get("ANTHROPIC_API_KEY", ""),
}

st.set_page_config(
    page_title="Fivetran · Add Connector",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#f7f8fa; }
[data-testid="stHeader"],#MainMenu,footer { display:none!important; }
.block-container { padding:0!important; max-width:100%!important; }

.topbar {
  background:#fff; border-bottom:1.5px solid #e5e7eb;
  padding:0 40px; height:58px;
  display:flex; align-items:center; gap:10px;
}
.topbar-logo { font-size:20px; font-weight:800; color:#0057d9; letter-spacing:-1px; margin-right:6px; }
.topbar-sep  { color:#d1d5db; font-size:18px; }
.topbar-crumb{ font-size:13.5px; color:#6b7280; }
.topbar-crumb b { color:#111827; font-weight:600; }

.shell { max-width:1100px; margin:36px auto; padding:0 28px 80px; }

.hero-title { font-size:26px; font-weight:800; color:#111827; margin-bottom:4px; }
.hero-sub   { font-size:14px; color:#6b7280; margin-bottom:26px; }

.tabs { display:flex; border-bottom:2px solid #e5e7eb; margin-bottom:24px; }
.tab  { padding:10px 22px; font-size:14px; font-weight:500; color:#6b7280;
        border-bottom:2.5px solid transparent; margin-bottom:-2px; }
.tab.on { color:#0057d9; border-bottom-color:#0057d9; }
.tab-pill { background:#f3f4f6; border-radius:99px; padding:1px 8px; font-size:11px; color:#6b7280; margin-left:5px; }
.new-badge{ background:#d1fae5; color:#065f46; border-radius:4px; padding:1px 7px; font-size:11px; font-weight:700; margin-left:5px; }

.card {
  background:#fff; border:1.5px solid #e5e7eb; border-radius:12px;
  padding:18px 18px 14px; height:100%;
  transition:box-shadow .15s,border-color .15s;
}
.card:hover { box-shadow:0 4px 16px rgba(0,0,0,.07); border-color:#93c5fd; }
.card-icon { width:42px;height:42px;background:#eff6ff;border-radius:10px;
  display:flex;align-items:center;justify-content:center;font-size:20px;margin-bottom:10px; }
.card-name { font-weight:700;font-size:14px;color:#111827;margin-bottom:3px; }
.card-desc { font-size:12px;color:#6b7280;line-height:1.5;margin-bottom:10px;min-height:46px; }
.card-tags { display:flex;flex-wrap:wrap;gap:4px; }
.pill      { background:#eff6ff;color:#1d4ed8;border-radius:99px;padding:2px 8px;font-size:11px;font-weight:500; }
.pill-rich { background:#dcfce7;color:#166534; }

.form-wrap { background:#fff;border:1.5px solid #e5e7eb;border-radius:14px;padding:36px 40px; }
.form-head { display:flex;align-items:center;gap:16px;
  padding-bottom:20px;border-bottom:1.5px solid #f3f4f6;margin-bottom:26px; }
.form-head-icon { font-size:30px; }
.form-head-name { font-size:21px;font-weight:800;color:#111827; }
.form-head-desc { font-size:13px;color:#6b7280;margin-top:2px; }
.fsec { font-size:14px;font-weight:700;color:#374151;margin:20px 0 14px; }
.fl   { font-size:13px;font-weight:600;color:#374151;margin-bottom:2px; }
.fl-req { color:#ef4444; }
.fh   { font-size:11.5px;color:#9ca3af;margin-bottom:7px; }
.divider { border:none;border-top:1.5px solid #f3f4f6;margin:18px 0; }

.info-card { background:#fff;border:1.5px solid #e5e7eb;border-radius:12px;padding:22px;font-size:13px; }
.info-title{ font-weight:700;color:#111827;font-size:14px;margin-bottom:10px; }
.info-row  { color:#6b7280;margin-bottom:5px; }
.info-row b{ color:#374151; }
.info-list { padding-left:18px;color:#6b7280;line-height:2.2;margin:6px 0 0; }

.stButton>button {
  border-radius:8px!important;font-weight:600!important;font-size:13px!important;
  border:1.5px solid #d1d5db!important;background:#fff!important;color:#374151!important;
  padding:5px 14px!important;transition:all .12s!important;
}
.stButton>button:hover { border-color:#0057d9!important;color:#0057d9!important;background:#eff6ff!important; }
[data-testid="stFormSubmitButton"]>button {
  background:#0057d9!important;color:#fff!important;border:none!important;
  width:100%!important;padding:11px 20px!important;font-size:14px!important;
  border-radius:8px!important;margin-top:4px!important;
}
[data-testid="stFormSubmitButton"]>button:hover { background:#0041a8!important; }

[data-testid="stTextInput"] input,
[data-testid="stSelectbox"]>div>div {
  border-radius:8px!important;border:1.5px solid #d1d5db!important;
  font-size:13.5px!important;background:#fff!important;
}
[data-testid="stTextInput"] input:focus {
  border-color:#0057d9!important;box-shadow:0 0 0 3px rgba(0,87,217,.1)!important;
}

.success-wrap { background:#fff;border:1.5px solid #e5e7eb;border-radius:14px;padding:48px;max-width:560px; }
.next-steps { background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px 20px;font-size:13px;color:#374151; }
.next-steps ol { padding-left:18px;margin:8px 0 0;line-height:2.2; }

.conn-id-box {
  background:#f8faff;border:1.5px solid #c7d7fc;border-radius:8px;
  padding:12px 16px;font-family:monospace;font-size:13px;color:#1d4ed8;
  margin:12px 0;word-break:break-all;
}

.ba-card  { background:#fff;border:1.5px solid #e5e7eb;border-radius:12px;padding:26px; }
.ba-before{ border-top:3px solid #f87171; }
.ba-after { border-top:3px solid #34d399; }
.kv  { display:flex;gap:8px;margin-bottom:7px;font-size:12px; }
.kv-k{ background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:6px 10px;width:42%;color:#374151;font-family:monospace; }
.kv-v{ background:#fff;border:1px dashed #d1d5db;border-radius:6px;padding:6px 10px;flex:1;color:#9ca3af;font-style:italic; }
.rf        { margin-bottom:12px; }
.rf-label  { font-size:12px;font-weight:700;color:#374151;margin-bottom:2px; }
.rf-hint   { font-size:11px;color:#9ca3af;margin-bottom:3px; }
.rf-input  { background:#fff;border:1.5px solid #d1d5db;border-radius:7px;padding:7px 11px;font-size:12px;color:#374151;width:100%; }
.rf-input.pw { letter-spacing:3px; }

[data-testid="stVerticalBlock"]>[data-testid="stVerticalBlock"] { gap:0.4rem; }
</style>
""", unsafe_allow_html=True)


# ── Fivetran API helpers ──────────────────────────────────────────────────────

def ft_headers() -> dict:
    key    = st.session_state.get("api_key")    or ENV["api_key"]
    secret = st.session_state.get("api_secret") or ENV["api_secret"]
    token  = b64encode(f"{key}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

def api_connected() -> bool:
    key    = st.session_state.get("api_key")    or ENV["api_key"]
    secret = st.session_state.get("api_secret") or ENV["api_secret"]
    group  = st.session_state.get("group_id")   or ENV["group_id"]
    return bool(key and secret and group)

def get_group_name() -> str:
    group_id = st.session_state.get("group_id") or ENV["group_id"]
    try:
        r = requests.get(f"{FIVETRAN_API}/groups/{group_id}", headers=ft_headers(), timeout=8)
        if r.ok:
            return r.json()["data"].get("name", group_id)
    except Exception:
        pass
    return group_id

def deploy_and_connect(connector_id: str, schema: str, secrets: list[dict]) -> dict:
    """Deploy the connector code and create the connection in one step."""
    api_key    = st.session_state.get("api_key")    or ENV["api_key"]
    api_secret = st.session_state.get("api_secret") or ENV["api_secret"]
    api_key_b64 = b64encode(f"{api_key}:{api_secret}".encode()).decode()
    group_name  = st.session_state.get("group_name") or get_group_name()

    connector_dir = CONNECTORS_DIR / connector_id
    config = {s["key"]: s["value"] for s in secrets}

    # Write config to a file inside the connector directory so fivetran deploy
    # can find it with a relative path (same as running manually from that dir)
    config_path = connector_dir / "_deploy_config.json"
    try:
        config_path.write_text(json.dumps(config))

        cmd = [
            FIVETRAN_BIN, "deploy",
            "--api-key",       api_key_b64,
            "--destination",   group_name,
            "--connection",    schema,
            "--configuration", "_deploy_config.json",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(connector_dir),
            env={**os.environ,
                 "PATH": f"/Library/Frameworks/Python.framework/Versions/3.12/bin:{os.environ.get('PATH','')}"},
        )
        output = result.stdout + "\n" + result.stderr
        # Strip ANSI escape codes for clean error messages
        output_clean = re.sub(r"\x1b\[[0-9;]*m", "", output)

        match = re.search(r"connection id:\s*(\S+)", output_clean)
        if not match:
            raise RuntimeError(output_clean.strip())

        connection_id = match.group(1)
        return {"id": connection_id, "schema": schema}
    finally:
        if config_path.exists():
            config_path.unlink()


# ── AI form generation ────────────────────────────────────────────────────────

def generate_form_with_ai(connector_code: str) -> dict:
    client = anthropic.Anthropic(api_key=ENV["anthropic_key"] or os.environ.get("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"""Analyze this Fivetran connector code and produce a setup form definition.

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "fields": [
    {{
      "name": "config_key_exactly_as_in_code",
      "label": "Human Readable Label",
      "description": "One sentence: what is this and where does the user find it?",
      "type": "password|text|dropdown|toggle",
      "required": true,
      "placeholder": "example value"
    }}
  ]
}}

Rules:
- Include only fields actually read from configuration dict in the code
- type="password" for API keys, secrets, tokens, passwords, credentials
- type="text" for URLs, hostnames, usernames, database names, IDs, numeric settings
- Descriptions must tell the user WHERE to get the value (e.g. "Your API key from app.example.com/settings")
- placeholder should be a realistic example value

Connector code:
{connector_code}"""}],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown fences if model adds them anyway
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    return json.loads(raw)


# ── Connector discovery ───────────────────────────────────────────────────────

def load_json_with_comments(text: str) -> dict:
    return json.loads(re.sub(r"//[^\n]*", "", text))

CONNECTOR_ICONS = {
    "neo4j":"🔵","clickhouse":"🟡","sap_hana_sql":"🔶","data_camp":"📊",
    "apache_druid":"🟠","couchbase":"🔴","aws":"☁️","gcp":"☁️","cassandra":"🗄️",
    "firebird":"🔥","ibm":"🔷","sql_server":"🗃️","redshift":"🔴","greenplum":"🐘",
    "hubspot":"🟠","github":"🐙","jenkins":"🔧","rabbit":"🐰","solace":"💬",
    "influx":"📈","timescale":"⏱️","supabase":"⚡","motherduck":"🦆",
    "prefect":"🌊","weights":"⚖️","unity":"🎮","veeva":"💊","teradata":"🗄️",
    "scylla":"🪸","toast":"🍞","vercel":"▲","oktopost":"📣","fleetio":"🚛",
    "harness":"🔧","checkly":"✅","sensor":"📡","slack":"💬","stripe":"💳",
}
CATEGORY_MAP = {
    "database":"Database","db":"Database","sql":"Database","api":"API",
    "aws":"Cloud","gcp":"Cloud","azure":"Cloud","cloud":"Cloud",
    "analytics":"Analytics","crm":"CRM","hubspot":"CRM","marketing":"Marketing",
    "finance":"Finance","camp":"Learning & Development","devops":"DevOps",
    "monitoring":"Monitoring","logs":"Monitoring",
}

def humanize(slug: str) -> str:
    upper = {"aws","gcp","sap","ibm","sql","api","oauth2","s3","csv","sb","bi","crm"}
    return " ".join(p.upper() if p in upper else p.capitalize() for p in slug.replace("_"," ").split())

def get_icon(cid: str) -> str:
    for k, v in CONNECTOR_ICONS.items():
        if k in cid:
            return v
    return "🔌"

def guess_category(name: str) -> str:
    n = name.lower()
    for kw, cat in CATEGORY_MAP.items():
        if kw in n:
            return cat
    return "Other"

def form_from_config(cfg: dict) -> dict:
    fields = []
    for key in cfg:
        lo = key.lower()
        ftype = "password" if any(w in lo for w in ("password","secret","token","key","auth","credential")) else "text"
        fields.append({"name": key, "label": key.replace("_"," ").title(),
                       "type": ftype, "required": True, "description": "", "placeholder": ""})
    return {"fields": fields}

@st.cache_data(ttl=300)
def discover_connectors() -> list[dict]:
    out = []
    for d in sorted(CONNECTORS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        cid = d.name
        form_path = d / "configuration_form.json"
        cfg_path  = d / "configuration.json"
        has_rich  = form_path.exists()

        if has_rich:
            form_def = json.loads(form_path.read_text())
        elif cfg_path.exists():
            try:
                raw = load_json_with_comments(cfg_path.read_text())
                form_def = form_from_config(raw) if raw else None
            except Exception:
                form_def = None
        else:
            form_def = None

        if not form_def or not form_def.get("fields"):
            continue

        # README — first line as short description, full text for setup guide
        desc = ""
        readme_full = ""
        for rname in ("README.md", "readme.md"):
            rp = d / rname
            if rp.exists():
                readme_full = rp.read_text()
                for line in readme_full.splitlines():
                    line = line.strip().lstrip("#").strip()
                    if line:
                        desc = line
                        break
            if desc:
                break
        if not desc:
            desc = f"Sync data from {humanize(cid)} to your destination."

        tags = [w for w in cid.replace("_"," ").split()
                if len(w) > 2 and w not in ("and","using","with","the","for")][:4]

        out.append({
            "id":             cid,
            "connector_name": humanize(cid),
            "description":    desc,
            "readme":         readme_full,
            "category":       guess_category(cid),
            "tags":           tags,
            "has_rich_form":  has_rich,
            "form_def":       form_def,
            "icon":           get_icon(cid),
        })
    return out


# ── Session state ─────────────────────────────────────────────────────────────

for k, v in [("page","marketplace"),("connector",None),("created_connector",None),
              ("api_key", ENV["api_key"]), ("api_secret", ENV["api_secret"]),
              ("group_id", ENV["group_id"]), ("group_name","")]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Nav bar ───────────────────────────────────────────────────────────────────

crumb = {
    "marketplace":  "Add Connector",
    "setup":        f"Add Connector &rsaquo; {st.session_state.connector['connector_name'] if st.session_state.connector else ''}",
    "success":      "Add Connector",
    "before_after": "Before vs After",
}.get(st.session_state.page, "")

st.markdown(f"""
<div class="topbar">
  <span class="topbar-logo">fivetran</span>
  <span class="topbar-sep">|</span>
  <span class="topbar-crumb">{crumb}</span>
</div>""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Demo")
    if st.button("🏪  Marketplace", use_container_width=True):
        st.session_state.page = "marketplace"
        st.session_state.connector = None
        st.rerun()
    if st.button("⚖️  Before vs After", use_container_width=True):
        st.session_state.page = "before_after"
        st.rerun()

    st.markdown("---")
    st.markdown("### 🔐 Fivetran Connection")

    connected = api_connected()
    if connected:
        gname = st.session_state.group_name or (ENV["group_id"][:8] + "…")
        st.success(f"Connected · destination: **{gname}**")
    else:
        st.warning("Not connected — enter credentials below")

    with st.expander("API Credentials", expanded=not connected):
        key = st.text_input("API Key", value=st.session_state.api_key,
                            type="password", key="sb_api_key")
        sec = st.text_input("API Secret", value=st.session_state.api_secret,
                            type="password", key="sb_api_secret")
        grp = st.text_input("Group (Destination) ID", value=st.session_state.group_id,
                            key="sb_group_id")

        if st.button("Connect", use_container_width=True):
            st.session_state.api_key    = key
            st.session_state.api_secret = sec
            st.session_state.group_id   = grp
            with st.spinner("Verifying…"):
                try:
                    name = get_group_name()
                    st.session_state.group_name = name
                    st.success(f"✅ Connected to **{name}**")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")


# ── Pages ─────────────────────────────────────────────────────────────────────

def page_marketplace():
    connectors = discover_connectors()
    st.markdown('<div class="shell">', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">Add a connector</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-sub">Choose a data source to sync into your destination.</div>', unsafe_allow_html=True)

    st.markdown(f"""
<div class="tabs">
  <div class="tab">Standard Connectors <span class="tab-pill">700+</span></div>
  <div class="tab on">SDK Marketplace <span class="new-badge">NEW</span>
    <span class="tab-pill">{len(connectors)}</span></div>
</div>
<p style="font-size:13.5px;color:#6b7280;margin:-4px 0 22px">
  Community-built connectors using the Fivetran Connector SDK —
  set up in one click, no deployment required.
</p>
""", unsafe_allow_html=True)

    c1, c2, c3, _ = st.columns([3, 2, 2, 1])
    with c1:
        search = st.text_input("s", placeholder="🔍  Search connectors…", label_visibility="collapsed")
    with c2:
        cats = ["All categories"] + sorted({c.get("category","Other") for c in connectors})
        cat  = st.selectbox("c", cats, label_visibility="collapsed")
    with c3:
        ffilter = st.selectbox("f", ["All","✨ Rich form","Basic form"], label_visibility="collapsed")

    q = search.strip().lower()
    filtered = [
        c for c in connectors
        if (not q or q in c["connector_name"].lower() or any(q in t for t in c["tags"]))
        and (cat == "All categories" or c["category"] == cat)
        and (ffilter == "All"
             or (ffilter == "✨ Rich form" and c["has_rich_form"])
             or (ffilter == "Basic form"   and not c["has_rich_form"]))
    ]

    rich_n = sum(1 for c in connectors if c["has_rich_form"])
    st.markdown(f'<p style="font-size:12px;color:#9ca3af;margin-bottom:16px">'
                f'{len(filtered)} connector{"s" if len(filtered)!=1 else ""} · {rich_n} with AI-generated rich forms</p>',
                unsafe_allow_html=True)

    for row_start in range(0, len(filtered), 3):
        cols = st.columns(3, gap="medium")
        for col, conn in zip(cols, filtered[row_start:row_start+3]):
            tags_html = "".join(
                f'<span class="pill{" pill-rich" if i==0 and conn["has_rich_form"] else ""}">'
                + (("✨ " if i==0 and conn["has_rich_form"] else "") + t) + "</span>"
                for i, t in enumerate(conn["tags"][:3])
            )
            with col:
                st.markdown(f"""
<div class="card">
  <div class="card-icon">{conn["icon"]}</div>
  <div class="card-name">{conn["connector_name"]}</div>
  <div class="card-desc">{conn["description"][:95]}{"…" if len(conn["description"])>95 else ""}</div>
  <div class="card-tags">{tags_html}</div>
</div>""", unsafe_allow_html=True)
                if st.button("Set up →", key=f"s_{conn['id']}", use_container_width=True):
                    st.session_state.connector = conn
                    st.session_state.page = "setup"
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def page_setup():
    c = st.session_state.connector
    if not c:
        st.session_state.page = "marketplace"
        st.rerun()

    icon     = c["icon"]
    live     = api_connected()

    # Resolve which form to use: pre-built rich → live AI-generated → inferred
    ai_form_key = f"ai_form_{c['id']}"
    ai_form     = st.session_state.get(ai_form_key)
    if c["has_rich_form"]:
        form_def    = c.get("form_def", {})
        form_source = "rich"
    elif ai_form:
        form_def    = ai_form
        form_source = "ai_live"
    else:
        form_def    = c.get("form_def", {})
        form_source = "inferred"

    st.markdown('<div class="shell">', unsafe_allow_html=True)
    if st.button("← Back to marketplace"):
        st.session_state.page = "marketplace"
        st.rerun()
    st.markdown("<br/>", unsafe_allow_html=True)

    left, right = st.columns([3, 1], gap="large")

    with left:
        if form_source == "rich":
            badge = '<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:1px 8px;font-size:11px;font-weight:700;margin-left:8px">✨ AI-generated form</span>'
        elif form_source == "ai_live":
            badge = '<span style="background:#ede9fe;color:#5b21b6;border-radius:4px;padding:1px 8px;font-size:11px;font-weight:700;margin-left:8px">✨ AI-generated live</span>'
        else:
            badge = '<span style="background:#f3f4f6;color:#6b7280;border-radius:4px;padding:1px 8px;font-size:11px">inferred from config</span>'
        st.markdown(f"""
<div class="form-wrap">
  <div class="form-head">
    <span class="form-head-icon">{icon}</span>
    <div>
      <div class="form-head-name">{c["connector_name"]}{badge}</div>
      <div class="form-head-desc">{c["description"]}</div>
    </div>
  </div>
""", unsafe_allow_html=True)

        # "Generate with AI" button — shown for connectors without a rich form
        if form_source == "inferred":
            st.markdown("""
<div style="background:#faf5ff;border:1.5px solid #e9d5ff;border-radius:10px;
     padding:14px 18px;margin-bottom:18px;display:flex;align-items:center;gap:12px">
  <span style="font-size:22px">✨</span>
  <div>
    <div style="font-size:13px;font-weight:700;color:#5b21b6">This connector has a basic form</div>
    <div style="font-size:12px;color:#7c3aed;margin-top:2px">
      Click below to let AI analyze the connector code and generate labeled fields with descriptions.
    </div>
  </div>
</div>""", unsafe_allow_html=True)
            if st.button("✨ Generate setup form with AI", use_container_width=False):
                connector_code = (CONNECTORS_DIR / c["id"] / "connector.py").read_text()
                with st.spinner("Claude is analyzing the connector code…"):
                    try:
                        generated = generate_form_with_ai(connector_code)
                        st.session_state[ai_form_key] = generated
                        st.rerun()
                    except Exception as e:
                        st.error(f"AI generation failed: {e}")

        with st.form("setup_form"):
            st.markdown('<div class="fsec">Connection Details</div>', unsafe_allow_html=True)

            for field in form_def.get("fields", []):
                req_star = ' <span class="fl-req">*</span>' if field.get("required") else ""
                st.markdown(f'<div class="fl">{field["label"]}{req_star}</div>', unsafe_allow_html=True)
                if field.get("description"):
                    st.markdown(f'<div class="fh">{field["description"]}</div>', unsafe_allow_html=True)

                ftype = field.get("type", "text")
                ph    = field.get("placeholder", "")

                if ftype == "password":
                    st.text_input("_", type="password", placeholder="Enter value",
                                  key=f"f_{field['name']}", label_visibility="collapsed")
                elif ftype == "dropdown":
                    opts = field.get("options") or []
                    st.selectbox("_", opts or ["(no options)"],
                                 key=f"f_{field['name']}", label_visibility="collapsed")
                elif ftype == "toggle":
                    st.toggle("_", key=f"f_{field['name']}")
                else:
                    st.text_input("_", placeholder=ph, key=f"f_{field['name']}",
                                  label_visibility="collapsed")

            st.markdown('<hr class="divider"/>', unsafe_allow_html=True)
            st.markdown('<div class="fsec">Sync Settings</div>', unsafe_allow_html=True)

            # Destination schema
            st.markdown('<div class="fl">Destination Schema <span class="fl-req">*</span></div>', unsafe_allow_html=True)
            st.markdown('<div class="fh">Tables land in this schema in your destination warehouse.</div>', unsafe_allow_html=True)
            st.text_input("_", placeholder=c["id"].lower(), key="dest_schema", label_visibility="collapsed")

            btn_label = "Save & Test Connection" if live else "Save & Test Connection (mock — add API key to go live)"
            submitted = st.form_submit_button(btn_label)

            if submitted:
                schema = st.session_state.get("dest_schema") or c["id"].lower()

                # Build secrets list from form field values
                secrets = []
                for field in form_def.get("fields", []):
                    val = st.session_state.get(f"f_{field['name']}", "")
                    if val:
                        secrets.append({"key": field["name"], "value": str(val)})

                if live:
                    with st.spinner("Deploying connector and creating connection in Fivetran…"):
                        try:
                            result = deploy_and_connect(c["id"], schema, secrets)
                            st.session_state.created_connector = result
                            st.session_state.page = "success"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Deploy failed: {e}")
                else:
                    # Mock success for demo without live API key
                    st.session_state.created_connector = {
                        "id": "demo_connector_id",
                        "schema": schema,
                        "_mock": True,
                    }
                    st.session_state.page = "success"
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        group_name = st.session_state.group_name or (ENV["group_id"] or "—")
        live_dot   = "🟢" if live else "🔴"

        # ── Destination card ──────────────────────────────────────────────
        st.markdown(f"""
<div class="info-card" style="margin-bottom:14px">
  <div class="info-title">Destination</div>
  <div class="info-row">{live_dot} <b>{group_name}</b></div>
  <div class="info-row" style="font-size:11px;color:#9ca3af">
    {"Connector will be created live in Fivetran" if live else "Add API key in sidebar to go live"}
  </div>
  <hr class="divider"/>
  <div class="info-title">Fivetran manages</div>
  <ul class="info-list">
    <li>Compute &amp; infrastructure</li>
    <li>Sync scheduling</li>
    <li>Retry &amp; error handling</li>
    <li>Schema management</li>
    <li>Incremental state</li>
  </ul>
</div>""", unsafe_allow_html=True)

        # ── Setup Guide card ──────────────────────────────────────────────
        fields      = form_def.get("fields", [])
        readme_text = c.get("readme", "")

        # Per-field guidance rows
        field_rows = ""
        for f in fields:
            desc  = f.get("description") or f.get("placeholder") or ""
            badge = '<span style="background:#fee2e2;color:#991b1b;border-radius:3px;padding:0 5px;font-size:10px;font-weight:700">required</span>' if f.get("required") else '<span style="background:#f3f4f6;color:#6b7280;border-radius:3px;padding:0 5px;font-size:10px">optional</span>'
            field_rows += f"""
<div style="margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid #f3f4f6">
  <div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:2px">
    {f["label"]} {badge}
  </div>
  {"<div style='font-size:11.5px;color:#6b7280;line-height:1.55'>" + desc + "</div>" if desc else ""}
</div>"""

        st.markdown(f"""
<div class="info-card">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
    <div class="info-title" style="margin:0">Setup Guide</div>
    <span style="font-size:11px;color:#0057d9;cursor:pointer">📖 Docs</span>
  </div>
  <div style="font-size:12.5px;color:#6b7280;line-height:1.6;margin-bottom:14px">{c["description"]}</div>
  <div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px;font-size:10.5px">Fields</div>
  {field_rows if field_rows else '<div style="font-size:12px;color:#9ca3af">Fill in each field above.</div>'}
</div>""", unsafe_allow_html=True)

        # Full README in expander
        if readme_text:
            with st.expander("📄 Full connector documentation"):
                st.markdown(readme_text)

    st.markdown("</div>", unsafe_allow_html=True)


def page_success():
    c    = st.session_state.connector
    data = st.session_state.created_connector or {}
    mock = data.get("_mock", False)
    conn_id = data.get("id", "—")
    schema  = data.get("schema", c["id"].lower() if c else "—")
    group   = st.session_state.group_name or ENV["group_id"] or "your destination"

    st.balloons()
    st.markdown('<div class="shell">', unsafe_allow_html=True)
    st.markdown(f"""
<div class="success-wrap">
  <div style="font-size:40px;margin-bottom:14px">✅</div>
  <div style="font-size:22px;font-weight:800;color:#111827;margin-bottom:8px">
    {c["icon"] if c else ""} {c["connector_name"] if c else ""} connected
  </div>
  <div style="font-size:14px;color:#374151;line-height:1.65;margin-bottom:20px">
    {"Connector created live in Fivetran." if not mock else "Mock success — add API key in sidebar for live creation."}<br/>
    Destination: <strong>{group}</strong> &nbsp;·&nbsp; Schema: <strong>{schema}</strong>
  </div>
""", unsafe_allow_html=True)

    if not mock and conn_id != "—":
        group_id = st.session_state.group_id or ENV["group_id"]
        dashboard_url = f"https://fivetran.com/dashboard/connectors/{group_id}/{conn_id}"
        st.markdown(f"""
  <div style="margin-bottom:16px">
    <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px">Connector ID</div>
    <div class="conn-id-box">{conn_id}</div>
    <a href="{dashboard_url}" target="_blank"
       style="display:inline-block;margin-top:8px;background:#0057d9;color:#fff;
              border-radius:8px;padding:9px 18px;font-size:13.5px;font-weight:600;
              text-decoration:none;">
      Open in Fivetran UI →
    </a>
  </div>
""", unsafe_allow_html=True)

    st.markdown("""
  <div class="next-steps">
    <b>What happens next</b>
    <ol>
      <li>Initial full sync starts automatically</li>
      <li>Future syncs run on your configured schedule</li>
      <li>Fivetran handles compute, retries &amp; schema changes</li>
    </ol>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)
    if st.button("← Add another connector"):
        st.session_state.page = "marketplace"
        st.session_state.connector = None
        st.session_state.created_connector = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def page_before_after():
    st.markdown('<div class="shell">', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">Before vs After</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-sub">SDK Marketplace closes the gap between standard and custom connectors.</div>', unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("""
<div class="ba-card ba-before">
  <div style="font-size:15px;font-weight:700;color:#ef4444;margin-bottom:4px">❌ Today</div>
  <div style="font-size:12px;color:#6b7280;margin-bottom:16px">Customer sets up an SDK connector</div>
  <p style="font-size:12px;font-weight:700;color:#374151;margin-bottom:6px">① Must deploy themselves first</p>
  <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:7px;padding:10px 14px;font-size:11.5px;font-family:monospace;color:#991b1b;margin-bottom:16px;line-height:1.9">
    $ pip install fivetran-connector-sdk<br/>
    $ # write connector.py + configuration.json<br/>
    $ fivetran deploy --api-key … --api-secret …<br/>
    <span style="color:#7f1d1d">✗ Copy the package_id from output…<br/>
    ✗ Paste it into the Fivetran UI form</span>
  </div>
  <p style="font-size:12px;font-weight:700;color:#374151;margin-bottom:8px">② Generic key-value form — no guidance</p>
  <div class="kv"><div class="kv-k">neo4j_uri</div><div class="kv-v">type value…</div></div>
  <div class="kv"><div class="kv-k">username</div><div class="kv-v">type value…</div></div>
  <div class="kv"><div class="kv-k">password</div><div class="kv-v">type value…</div></div>
  <div class="kv"><div class="kv-k">database</div><div class="kv-v">type value…</div></div>
  <p style="font-size:11px;color:#9ca3af;margin-top:10px">Requires package_id · No labels · No descriptions · No password masking</p>
</div>""", unsafe_allow_html=True)

    with right:
        st.markdown("""
<div class="ba-card ba-after">
  <div style="font-size:15px;font-weight:700;color:#059669;margin-bottom:4px">✅ SDK Marketplace</div>
  <div style="font-size:12px;color:#6b7280;margin-bottom:16px">Same as any standard connector</div>
  <p style="font-size:12px;font-weight:700;color:#374151;margin-bottom:8px">① Browse → click Set up → done</p>
  <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:7px;padding:14px 16px;margin-bottom:16px">
    <div class="rf">
      <div class="rf-label">Neo4j Connection URI <span style="color:#ef4444">*</span></div>
      <div class="rf-hint">The Bolt URI for your Neo4j instance</div>
      <div class="rf-input">bolt://localhost:7687</div>
    </div>
    <div class="rf">
      <div class="rf-label">Username <span style="color:#ef4444">*</span></div>
      <div class="rf-hint">Your Neo4j database username</div>
      <div class="rf-input">neo4j</div>
    </div>
    <div class="rf">
      <div class="rf-label">Password <span style="color:#ef4444">*</span></div>
      <div class="rf-hint">Your Neo4j database password</div>
      <div class="rf-input pw">••••••••</div>
    </div>
  </div>
  <p style="font-size:11.5px;color:#059669;font-weight:600">
    Labeled fields · Inline help · Password masking · No deployment needed
  </p>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Router ────────────────────────────────────────────────────────────────────

{
    "marketplace":  page_marketplace,
    "setup":        page_setup,
    "success":      page_success,
    "before_after": page_before_after,
}.get(st.session_state.page, page_marketplace)()
