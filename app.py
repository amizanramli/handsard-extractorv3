import streamlit as st
import fitz          # PyMuPDF
import pandas as pd
import io
import re
import json
import os
from typing import Optional

# ============================================================
# Page Configuration
# ============================================================
st.set_page_config(
    page_title="Hansard Curator",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Light Theme + Contrast Accents
# ============================================================
st.markdown("""
<style>
:root {
  --bg:        #f8fafc;
  --surface:   #ffffff;
  --surface-2: #f1f5f9;
  --border:    #e2e8f0;
  --text:      #0f172a;
  --text-mute: #64748b;
  --accent:    #4f46e5;
  --accent-2:  #ec4899;
}
.stApp { background-color: var(--bg); color: var(--text); }
.main  { background-color: var(--bg); }
section[data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border);
}
h1, h2, h3, h4, h5, h6, p, span, label, div { color: var(--text); }
.stMarkdown p, .stCaption, [data-testid="stCaptionContainer"] { color: var(--text-mute); }
h1 { text-align: center; margin-bottom: 0.25rem; font-weight: 700; }
h1 span { background: linear-gradient(135deg, var(--accent), var(--accent-2));
          -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.stAlert { background-color: var(--surface) !important;
           border: 1px solid var(--border) !important;
           color: var(--text) !important;
           border-left: 4px solid var(--accent) !important; }
.stButton>button {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #ffffff; border: none; border-radius: 10px;
    font-weight: 600; padding: 0.55rem 1.2rem;
    transition: transform .15s ease, box-shadow .15s ease;
}
.stButton>button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 18px -6px rgba(79,70,229,.55);
}
.stDownloadButton>button {
    background: var(--surface); color: var(--accent);
    border: 1.5px solid var(--accent); border-radius: 10px; font-weight: 600;
}
.stDownloadButton>button:hover { background: var(--accent); color: #ffffff; }
[data-testid="stMetricValue"] { color: var(--accent) !important; font-weight: 700; }
[data-testid="stMetricLabel"] { color: var(--text-mute) !important; }
div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# Assignments persistence (JSON on disk)
# ============================================================
ASSIGNMENTS_PATH = "speaker_assignments.json"

def load_assignments() -> dict:
    """Load saved speaker→portfolio assignments from disk."""
    if os.path.exists(ASSIGNMENTS_PATH):
        try:
            with open(ASSIGNMENTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_assignments(assignments: dict) -> None:
    """Persist speaker→portfolio assignments to disk."""
    with open(ASSIGNMENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(assignments, f, ensure_ascii=False, indent=2)

# ============================================================
# Name utilities
# ============================================================
_STRIP_TITLES = [
    'YAB ', 'YB ',
    "SENATOR DATO' SERI DIRAJA DR. ", "SENATOR DATO' SERI DIRAJA ",
    "SENATOR DATO\u2019 SERI DIRAJA DR. ", "SENATOR DATO\u2019 SERI DIRAJA ",
    'SENATOR DATUK SERI DR. ', 'SENATOR DATUK SERI ',
    'SENATOR DR. ', 'SENATOR ',
    "DATO' SERI DIRAJA DR. ", "DATO' SERI DIRAJA ",
    "DATO\u2019 SERI DIRAJA DR. ", "DATO\u2019 SERI DIRAJA ",
    "DATO' SERI UTAMA ", "DATO\u2019 SERI UTAMA ",
    'DATUK AMAR HAJI ', 'DATUK AMAR ', 'DATUK TS. ',
    "DATO' WIRA DR. ", "DATO' WIRA ",
    "DATO' SERI DR. ", "DATO' SERI ", "DATO' SRI DR. ", "DATO' SRI ",
    "DATO' DR. ", "DATO' ",
    'DATO\u2019 SERI DR. ', 'DATO\u2019 SERI ', 'DATO\u2019 SRI ', 'DATO\u2019 DR. ', 'DATO\u2019 ',
    'DATO\u2018 SERI DR. ', 'DATO\u2018 SERI ', 'DATO\u2018 SRI ', 'DATO\u2018 DR. ', 'DATO\u2018 ',
    'DATO SERI DR. ', 'DATO SERI ', 'DATO SRI DR. ', 'DATO SRI ',
    'DATUK SERI DR. ', 'DATUK SERI ', 'DATUK DR. ', 'DATUK ',
    'TAN SRI ', 'TUN ', 'DR. ', 'DR ', 'IR. ', 'TS. ',
    'TUAN HAJI ', 'TUAN ', 'PUAN HAJJAH ', 'PUAN ',
    'HAJI ', 'HAJJAH ', 'HAJAH ', 'UTAMA ', 'A/P ', 'A/L ', 'PANGLIMA ',
]

def _strip_titles(name: str) -> str:
    n = name.strip()
    changed = True
    while changed:
        changed = False
        for t in sorted(_STRIP_TITLES, key=len, reverse=True):
            if n.upper().startswith(t.upper()):
                n = n[len(t):].strip()
                changed = True
    return n

def _normalise_key(name: str) -> str:
    k = _strip_titles(name).upper()
    k = re.sub(r"DATO['\u2019\u2018]\s*(?:SERI\s+|SRI\s+)?", '', k)
    k = re.sub(r'\bBINTE\b', 'BINTI', k)
    return re.sub(r'\s+', ' ', k).strip()

# Normalized_Speaker: strip leading honorifics from start only
_NORMALIZE_TITLES = [
    'Yang Berhormat ', 'Yang Amat Berhormat ',
    "Dato' Seri Diraja ", "Dato\u2019 Seri Diraja ",
    "Dato' Seri ", "Dato' Sri ",
    "Dato\u2019 Seri ", "Dato\u2018 Seri ",
    "Dato\u2019 Sri ", "Dato\u2018 Sri ",
    'Datuk Amar Haji ', 'Datuk Amar ',
    'Datuk Seri ', 'Datuk Wira ',
    "Dato' Wira ", "Dato\u2019 Wira ",
    "Dato' Indera ", "Dato\u2019 Indera ",
    "Dato' ", "Dato\u2019 ", "Dato\u2018 ",
    'Datuk ', 'Tan Sri ', 'Tun ',
    'Tuan Haji ', 'Puan Hajjah ', 'Puan Hajah ',
    'Dr. ', 'Ir. ', 'Ts. ',
    'Tuan ', 'Puan ',
    'Haji ', 'Hajjah ', 'Hajah ',
    'Wira ', 'Indera ', 'Panglima ',
]
_TITLE_ONLY_SPEAKERS = {
    'tuan yang di-pertua', 'yang di-pertua', 'setiausaha',
    'beberapa ahli', 'seorang ahli', 'ahli-ahli',
}

def _normalize_speaker(raw: str) -> str:
    if raw.lower().strip() in _TITLE_ONLY_SPEAKERS:
        return raw.strip()
    clean = raw.strip()
    changed = True
    while changed:
        changed = False
        for title in sorted(_NORMALIZE_TITLES, key=len, reverse=True):
            if clean.upper().startswith(title.upper()):
                clean = clean[len(title):].strip()
                changed = True
                break
    return clean if clean else raw.strip()

# ============================================================
# MP Lookup (constituency only)
# ============================================================
@st.cache_data(show_spinner=False)
def build_mp_lookup(excel_bytes: bytes) -> dict:
    df = pd.read_excel(io.BytesIO(excel_bytes))
    name_col  = next(c for c in df.columns if 'NAMA' in c.upper() or 'NAME' in c.upper())
    const_col = next(c for c in df.columns if 'KAWASAN' in c.upper()
                                               or 'CONST' in c.upper()
                                               or 'PARLIMEN' in c.upper())
    lookup = {}
    for _, row in df.iterrows():
        raw   = str(row[name_col]).strip()
        const = str(row[const_col]).strip().title()
        key   = _normalise_key(raw)
        lookup[key] = const
    return lookup

def lookup_constituency(norm_speaker: str, mp_lookup: dict) -> str:
    k = _normalise_key(norm_speaker)
    if k in mp_lookup:
        return mp_lookup[k]
    # binti-normalised fallback
    k_nb = re.sub(r'\bBINTI\b\s*', '', k).strip()
    for lk, const in mp_lookup.items():
        if re.sub(r'\bBINTI\b\s*', '', lk).strip() == k_nb and k_nb:
            return const
    return ''

# ============================================================
# Roster loader (for portfolio suggestions)
# ============================================================
@st.cache_data(show_spinner=False)
def load_roster(excel_bytes: bytes) -> pd.DataFrame:
    """
    Load a minister roster and return a clean DataFrame with columns:
      Nama, Jawatan, Kementerian, Timbalan, Senator, Kawasan Parlimen
    Accepts both Format C (Nama/Jawatan/Kementerian) and Format A/B (Kementerian/Menteri/Timbalan).
    Returns a flat list where each row = one person.
    """
    df = pd.read_excel(io.BytesIO(excel_bytes))
    cols_upper = [c.upper() for c in df.columns]

    rows = []

    # Format C: Nama + Jawatan + Kementerian columns
    if any('NAMA' in c for c in cols_upper) and any('JAWATAN' in c for c in cols_upper):
        nama_col       = next(c for c in df.columns if 'NAMA'        in c.upper())
        jawatan_col    = next(c for c in df.columns if 'JAWATAN'     in c.upper())
        kementerian_col = next((c for c in df.columns if 'KEMENTERIAN' in c.upper()), None)
        kawasan_col    = next((c for c in df.columns if 'KAWASAN'    in c.upper()), None)
        timbalan_col   = next((c for c in df.columns if 'TIMBALAN'   in c.upper()), None)
        senator_col    = next((c for c in df.columns if 'SENATOR'    in c.upper()), None)

        for _, row in df.iterrows():
            raw     = str(row[nama_col]).strip()
            jawatan = str(row[jawatan_col]).strip()
            if raw in ('', 'nan') or jawatan in ('', 'nan'):
                continue
            ministry = str(row.get(kementerian_col, '')).strip() if kementerian_col else jawatan
            kawasan  = str(row.get(kawasan_col, '')).strip()     if kawasan_col    else ''
            timbalan = str(row.get(timbalan_col, '')).strip()    if timbalan_col   else ''
            senator  = str(row.get(senator_col, '')).strip()     if senator_col    else ''
            is_dep   = jawatan.lower().strip() == 'timbalan menteri'
            rows.append({
                'Nama'             : _strip_titles(raw).title(),
                'Jawatan'          : 'Timbalan Menteri' if is_dep else 'Menteri',
                'Kementerian'      : ministry,
                'Timbalan'         : 'Ya' if (timbalan.lower() in ('ya','yes') or is_dep) else '',
                'Senator'          : 'Ya' if senator.lower() in ('ya','yes') else '',
                'Kawasan Parlimen' : kawasan.title() if kawasan not in ('', 'nan', '-') else '',
            })

    # Format A/B: Kementerian | Menteri | Timbalan Menteri
    else:
        ministry_col  = df.columns[0]
        menteri_col   = next((c for c in df.columns if c.strip() == 'Menteri'), None)
        timbalan_col  = next((c for c in df.columns if 'Timbalan' in c), None)

        for _, row in df.iterrows():
            ministry = str(row[ministry_col]).strip()
            if ministry in ('', 'nan'):
                continue
            for col, is_dep in [(menteri_col, False), (timbalan_col, True)]:
                if col is None:
                    continue
                raw = str(row.get(col, '')).strip()
                if raw in ('', 'nan', '-', '\u2014'):
                    continue
                raw = re.sub(r'\(.*?\)', '', raw).strip()
                if not raw:
                    continue
                rows.append({
                    'Nama'             : _strip_titles(raw).title(),
                    'Jawatan'          : 'Timbalan Menteri' if is_dep else 'Menteri',
                    'Kementerian'      : ministry,
                    'Timbalan'         : 'Ya' if is_dep else '',
                    'Senator'          : 'Ya' if 'SENATOR' in raw.upper() else '',
                    'Kawasan Parlimen' : '',
                })

    return pd.DataFrame(rows)

# ============================================================
# PDF Parsing (extraction only — no portfolio matching)
# ============================================================
_CHAR = r"[a-zA-Z\s\(\)@\-\'\u2018\u2019\./]"

SPEAKER_RE = re.compile(
    rf"^([A-Z]{_CHAR}+?)(?:\s*\[([^\]]*)\])?\s*:\s*(.*)",
    re.MULTILINE | re.DOTALL,
)
UNCLOSED_RE = re.compile(
    rf"^([A-Z]{_CHAR}+?)\s*\[([A-Z]{_CHAR}+?)\s*:\s*(.*)",
    re.MULTILINE | re.DOTALL,
)
EMBEDDED_SPEAKER_RE = re.compile(
    rf"(?:^|\n)([A-Z]{_CHAR}+?(?:\s*\[[^\]]*\])?\s*:\s)",
    re.MULTILINE,
)
HEADER_RE   = re.compile(r"DR\.\s*\d+\.\s*\d+\.\s*\d+")
PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*$")
_NAME_SIGNALS = ('bin ', 'binti ', 'Dato', 'Datuk', 'Tan Sri', 'Tun ', 'Dr. ')

def _is_personal_name(text: str) -> bool:
    return any(s in text for s in _NAME_SIGNALS)

def _is_header_only_block(text: str) -> bool:
    s = text.strip()
    if not s or s.startswith('\u25a0'):
        return True
    lines = [l.strip() for l in s.split('\n') if l.strip()]
    for line in lines:
        if PAGE_NUM_RE.match(line):
            continue
        if HEADER_RE.search(line) and len(line) < 30:
            continue
        return False
    return True

def _clean_speech_text(text: str) -> str:
    text = re.sub(r'\n\s*\d{1,3}\s*\n\s*DR\.\s*\d+\.\s*\d+\.\s*\d+\s*', '\n', text)
    text = re.sub(r'\n\s*DR\.\s*\d+\.\s*\d+\.\s*\d+\s*\n\s*\d{1,3}\s*', '\n', text)
    text = re.sub(r'DR\.\s*\d+\.\s*\d+\.\s*\d+', '', text)
    text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()

def _parse_block(text: str):
    m = SPEAKER_RE.match(text)
    if m:
        outer  = m.group(1).replace('\n', ' ').strip()
        bracket = (m.group(2) or '').replace('\n', ' ').strip()
        speech  = (m.group(3) or '').strip()
        if bracket and _is_personal_name(bracket):
            return dict(speaker=bracket, role=outer, constituency='', speech=speech)
        return dict(speaker=outer, role='', constituency=bracket, speech=speech)
    m2 = UNCLOSED_RE.match(text)
    if m2:
        outer  = m2.group(1).replace('\n', ' ').strip()
        bracket = m2.group(2).replace('\n', ' ').strip()
        speech  = (m2.group(3) or '').strip()
        if _is_personal_name(bracket):
            return dict(speaker=bracket, role=outer, constituency='', speech=speech)
        return dict(speaker=outer, role='', constituency=bracket, speech=speech)
    return None

def _split_block_by_speakers(text: str):
    matches = [m for m in EMBEDDED_SPEAKER_RE.finditer(text) if m.start() > 0]
    if not matches:
        return [(text, None)]
    segments = []; last = 0
    for m in matches:
        segments.append(text[last:m.start()])
        new_start = m.start() + 1 if text[m.start()] == '\n' else m.start()
        last = new_start
    segments.append(text[last:])
    result = [(segments[0], None)]
    for seg in segments[1:]:
        result.append((seg, _parse_block(seg)))
    return result

def process_hansard_pdf(file_bytes: bytes, mp_lookup: dict) -> list:
    """
    Extract all speaker turns from a Hansard PDF.
    Returns clean rows with Speaker, Normalized_Speaker, Role, Constituency, Speech, Page.
    Portfolio assignment happens separately in Step 2.
    """
    transcript = []
    pdf_const_lookup: dict[str, str] = {}

    cur_speaker = cur_role = cur_const = ''
    cur_speech: list = []
    cur_page = 1

    def _flush():
        if cur_speaker:
            norm = _normalize_speaker(cur_speaker)
            const = cur_const or pdf_const_lookup.get(cur_speaker, '') \
                               or lookup_constituency(cur_speaker, mp_lookup)
            transcript.append({
                'Speaker'            : cur_speaker,
                'Normalized_Speaker' : norm,
                'Role'               : cur_role,
                'Constituency'       : const,
                'Speech'             : _clean_speech_text('\n'.join(cur_speech)),
                'Page'               : cur_page,
            })

    def _start_new(parsed, page_idx):
        nonlocal cur_speaker, cur_role, cur_const, cur_speech, cur_page
        cur_speaker = parsed['speaker']
        cur_role    = parsed['role']
        cur_page    = page_idx + 1
        pdf_const   = parsed.get('constituency', '')
        if pdf_const:
            cur_const = pdf_const.title()
            pdf_const_lookup[cur_speaker] = cur_const
        else:
            cur_const = ''
        cur_speech = [parsed['speech']] if parsed['speech'] else []

    with fitz.open(stream=file_bytes, filetype='pdf') as doc:
        for i in range(len(doc)):
            for block in doc[i].get_text('dict')['blocks']:
                if block.get('type') != 0:
                    continue
                # Reconstruct text from all spans (bold, italic, normal)
                all_parts = []
                for line in block.get('lines', []):
                    parts = [s['text'] for s in line.get('spans', []) if s['text'].strip()]
                    if parts:
                        all_parts.append(''.join(parts))
                text = '\n'.join(all_parts).strip()
                if not text or _is_header_only_block(text):
                    continue

                for idx, (seg, seg_parsed) in enumerate(_split_block_by_speakers(text)):
                    p = _parse_block(seg) if idx == 0 else seg_parsed
                    if p:
                        _flush()
                        _start_new(p, i)
                    elif cur_speaker:
                        cur_speech.append(seg.replace('\n', ' '))
        _flush()

    # Back-fill constituency from within-document observations
    for entry in transcript:
        if not entry['Constituency'] and entry['Speaker'] in pdf_const_lookup:
            entry['Constituency'] = pdf_const_lookup[entry['Speaker']]

    return transcript

# ============================================================
# Apply assignments to transcript rows
# ============================================================
def apply_assignments(transcript: list, assignments: dict) -> list:
    """
    Merge confirmed speaker→portfolio assignments into transcript rows.
    Keyed on Normalized_Speaker so it's robust across different title variants.
    """
    for row in transcript:
        key = row['Normalized_Speaker']
        if key in assignments:
            a = assignments[key]
            row['Portfolio']    = a.get('portfolio', '')
            row['Jawatan']      = a.get('jawatan', '')
            row['Kementerian']  = a.get('kementerian', '')
            row['Is_Minister']  = 'Yes' if a.get('portfolio') else ''
            row['Is_Deputy']    = 'Ya' if a.get('jawatan') == 'Timbalan Menteri' else ''
            row['Senator']      = a.get('senator', '')
            # Roster constituency overrides only if not already from PDF
            if not row['Constituency'] and a.get('constituency'):
                row['Constituency'] = a['constituency']
        else:
            row.setdefault('Portfolio',   '')
            row.setdefault('Jawatan',     '')
            row.setdefault('Kementerian', '')
            row.setdefault('Is_Minister', '')
            row.setdefault('Is_Deputy',   '')
            row.setdefault('Senator',     '')
    return transcript

# ============================================================
# Excel export
# ============================================================
def dataframe_to_xlsx(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transcript')
    return output.getvalue()

# ============================================================
# UI
# ============================================================
st.markdown("<h1>Hansard <span>Extractor</span></h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:#64748b;margin-bottom:1.5rem;'>"
    "V4 — Extract · Assign · Export</p>",
    unsafe_allow_html=True,
)

# Sidebar: MP roster only (for constituency)
with st.sidebar:
    st.header("MP Roster")
    st.caption("Upload to auto-fill constituencies. Columns: **NAMA PENUH**, **KAWASAN PARLIMEN**.")
    roster_file = st.file_uploader("MP roster (.xlsx)", type=["xlsx"], key="mp_roster")

mp_lookup: dict = {}
if roster_file:
    mp_lookup = build_mp_lookup(roster_file.read())
    st.sidebar.success(f"{len(mp_lookup)} MPs loaded.")

# ── Step tabs ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["① Extract", "② Assign Portfolios", "③ Export"])

# ==============================================================================
# TAB 1 — EXTRACT
# ==============================================================================
with tab1:
    st.subheader("Upload Hansard PDFs")
    st.caption("Upload up to 5 PDFs. All pages are processed automatically.")

    uploaded_files = st.file_uploader(
        "Drag & drop PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_upload",
    )

    if uploaded_files:
        if len(uploaded_files) > 5:
            st.error("Maximum 5 PDFs allowed.")
        else:
            # Show page counts
            file_infos = []
            for f in uploaded_files:
                raw = f.read()
                with fitz.open(stream=raw, filetype="pdf") as doc:
                    n_pages = len(doc)
                file_infos.append({"name": f.name, "stem": f.name.rsplit(".", 1)[0],
                                    "bytes": raw, "pages": n_pages})

            cols = st.columns(len(file_infos))
            for col, fi in zip(cols, file_infos):
                col.metric(
                    fi["name"][:20] + "…" if len(fi["name"]) > 20 else fi["name"],
                    f"{fi['pages']} pages",
                )

            if st.button("🚀 Extract All Documents", width="stretch"):
                with st.spinner("Extracting…"):
                    all_rows = []
                    for fi in file_infos:
                        rows = process_hansard_pdf(fi["bytes"], mp_lookup)
                        for r in rows:
                            r["Document"] = fi["name"]
                        all_rows.extend(rows)

                    if not all_rows:
                        st.warning("No speaker segments found.")
                    else:
                        st.session_state["transcript"] = all_rows
                        df = pd.DataFrame(all_rows)
                        st.success(
                            f"Extracted **{len(df)}** speech turns from "
                            f"**{df['Speaker'].nunique()}** unique speakers."
                        )

    # Show extraction results if available
    if "transcript" in st.session_state:
        df = pd.DataFrame(st.session_state["transcript"])

        c1, c2, c3 = st.columns(3)
        c1.metric("Total turns",      len(df))
        c2.metric("Unique speakers",  df["Speaker"].nunique())
        c3.metric("With constituency",int((df["Constituency"] != "").sum()))

        with st.expander("Preview extracted turns"):
            st.dataframe(
                df[["Speaker", "Normalized_Speaker", "Role", "Constituency", "Speech", "Page", "Document"]],
                width="stretch", height=380,
                column_config={
                    "Speech": st.column_config.TextColumn("Speech", width="large"),
                },
            )

# ==============================================================================
# TAB 2 — ASSIGN PORTFOLIOS
# ==============================================================================

# Officials whose title IS their portfolio
_OFFICIAL_TITLES = {
    'tuan yang di-pertua'  : 'Tuan Yang di-Pertua',
    'yang di-pertua'       : 'Yang di-Pertua',
    'setiausaha'           : 'Setiausaha',
    'beberapa ahli'        : 'Beberapa Ahli',
    'seorang ahli'         : 'Seorang Ahli',
    'ahli-ahli'            : 'Ahli-Ahli',
}

def _auto_assign_from_roster(
    norm_name: str,
    raw_name: str,
    roster_df: pd.DataFrame,
) -> dict | None:
    """
    Match norm_name against the roster and return an assignment dict,
    or None if no match.
    """
    if roster_df.empty:
        return None

    # 1. Exact match on normalized name
    for _, row in roster_df.iterrows():
        roster_norm = _normalize_speaker(str(row['Nama']))
        if roster_norm.upper() == norm_name.upper():
            return {
                'portfolio'   : f"{row['Jawatan']} — {row['Kementerian']}",
                'jawatan'     : row['Jawatan'],
                'kementerian' : row['Kementerian'],
                'senator'     : str(row.get('Senator', '')),
                'constituency': str(row.get('Kawasan Parlimen', '')),
                'confirmed'   : True,
                'source'      : 'roster',
            }

    # 2. Normalise bin/binti and retry
    nb = re.sub(r'\bBINTI?\b\s*', '', norm_name.upper()).strip()
    for _, row in roster_df.iterrows():
        roster_nb = re.sub(
            r'\bBINTI?\b\s*', '',
            _normalize_speaker(str(row['Nama'])).upper()
        ).strip()
        if roster_nb == nb and nb:
            return {
                'portfolio'   : f"{row['Jawatan']} — {row['Kementerian']}",
                'jawatan'     : row['Jawatan'],
                'kementerian' : row['Kementerian'],
                'senator'     : str(row.get('Senator', '')),
                'constituency': str(row.get('Kawasan Parlimen', '')),
                'confirmed'   : True,
                'source'      : 'roster_nobin',
            }

    return None


with tab2:
    if "transcript" not in st.session_state:
        st.info("Complete Step ① first to extract speakers.")
    else:
        df_all = pd.DataFrame(st.session_state["transcript"])

        # Load saved assignments
        if "assignments" not in st.session_state:
            st.session_state["assignments"] = load_assignments()

        assignments: dict = st.session_state["assignments"]

        # ── Roster upload ──────────────────────────────────────────────────
        st.subheader("Upload Minister Roster")
        st.caption(
            "Upload any combination of the three cabinet lists. "
            "Ministers are auto-matched and confirmed. "
            "You can edit any row manually."
        )
        roster_cols = st.columns(3)
        roster_dfs = []
        for col, label, key in zip(
            roster_cols,
            ["Original (19 Dec 2022)", "After First Reshuffle", "After Final Reshuffle"],
            ["r_orig", "r_first", "r_final"],
        ):
            with col:
                f = st.file_uploader(label, type=["xlsx"], key=key)
                if f:
                    roster_dfs.append(load_roster(f.read()))

        roster_combined = (
            pd.concat(roster_dfs, ignore_index=True)
            .drop_duplicates(subset=["Nama"])
            if roster_dfs else pd.DataFrame()
        )

        # ── Auto-assign on roster load ─────────────────────────────────────
        if not roster_combined.empty:
            # Build unique speaker list
            unique_speakers = (
                df_all[["Normalized_Speaker", "Speaker"]]
                .drop_duplicates("Normalized_Speaker")
            )
            newly_assigned = 0
            for _, spk in unique_speakers.iterrows():
                norm = spk["Normalized_Speaker"]
                raw  = spk["Speaker"]

                # Skip if already confirmed
                if assignments.get(norm, {}).get("confirmed"):
                    continue

                # Officials — title becomes portfolio
                official_key = norm.lower().strip()
                if official_key in _OFFICIAL_TITLES:
                    assignments[norm] = {
                        "portfolio"   : _OFFICIAL_TITLES[official_key],
                        "jawatan"     : "",
                        "kementerian" : "",
                        "senator"     : "",
                        "constituency": "",
                        "confirmed"   : True,
                        "source"      : "official",
                        "speaker_raw" : raw,
                    }
                    newly_assigned += 1
                    continue

                # Minister roster match
                result = _auto_assign_from_roster(norm, raw, roster_combined)
                if result:
                    result["speaker_raw"] = raw
                    assignments[norm] = result
                    newly_assigned += 1

            if newly_assigned:
                st.session_state["assignments"] = assignments
                save_assignments(assignments)
                st.success(f"Auto-assigned **{newly_assigned}** speakers from roster.")

        # Also auto-assign officials even without a roster
        else:
            unique_speakers = (
                df_all[["Normalized_Speaker", "Speaker"]]
                .drop_duplicates("Normalized_Speaker")
            )
            for _, spk in unique_speakers.iterrows():
                norm = spk["Normalized_Speaker"]
                raw  = spk["Speaker"]
                official_key = norm.lower().strip()
                if official_key in _OFFICIAL_TITLES and not assignments.get(norm):
                    assignments[norm] = {
                        "portfolio"   : _OFFICIAL_TITLES[official_key],
                        "jawatan"     : "",
                        "kementerian" : "",
                        "senator"     : "",
                        "constituency": "",
                        "confirmed"   : True,
                        "source"      : "official",
                        "speaker_raw" : raw,
                    }

        # Build portfolio options from roster
        portfolio_options: list[str] = [""]
        if not roster_combined.empty:
            for _, row in roster_combined.iterrows():
                opt = f"{row['Jawatan']} — {row['Kementerian']}"
                if opt not in portfolio_options:
                    portfolio_options.append(opt)

        # ── Speaker assignment table ───────────────────────────────────────
        st.subheader("Speaker Assignments")

        # Summary counts
        total_speakers = df_all["Normalized_Speaker"].nunique()
        confirmed_count = sum(
            1 for n, a in assignments.items()
            if a.get("confirmed") and n in df_all["Normalized_Speaker"].values
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Total speakers",     total_speakers)
        m2.metric("Auto-assigned",      confirmed_count)
        m3.metric("Needs review",       total_speakers - confirmed_count)

        # Filter toggle
        show_filter = st.radio(
            "Show",
            ["All speakers", "Needs review only", "Confirmed only"],
            horizontal=True,
        )

        # Build summary
        speaker_summary = (
            df_all.groupby(["Normalized_Speaker", "Speaker"])
            .agg(Turns=("Speech", "count"))
            .reset_index()
            .sort_values("Turns", ascending=False)
        )

        # Apply filter
        def _needs_review(norm):
            a = assignments.get(norm, {})
            return not a.get("confirmed") and not a.get("portfolio")

        if show_filter == "Needs review only":
            speaker_summary = speaker_summary[
                speaker_summary["Normalized_Speaker"].apply(_needs_review)
            ]
        elif show_filter == "Confirmed only":
            speaker_summary = speaker_summary[
                ~speaker_summary["Normalized_Speaker"].apply(_needs_review)
            ]

        st.caption(
            f"Showing **{len(speaker_summary)}** of **{total_speakers}** speakers. "
            "Edit any row and click **Save All Assignments**."
        )

        # Column headers
        h1, h2, h3, h4 = st.columns([3, 1, 5, 1])
        h1.markdown("**Speaker**")
        h2.markdown("**Turns**")
        h3.markdown("**Portfolio**")
        h4.markdown("**✓**")
        st.divider()

        updated_assignments = dict(assignments)

        for row_idx, (_, spk_row) in enumerate(speaker_summary.iterrows()):
            norm  = spk_row["Normalized_Speaker"]
            raw   = spk_row["Speaker"]
            turns = int(spk_row["Turns"])

            current           = assignments.get(norm, {})
            current_portfolio = current.get("portfolio", "")
            current_confirmed = current.get("confirmed", False)
            source            = current.get("source", "")

            # Source badge
            if source == "roster" or source == "roster_nobin":
                badge = "🟢"    # auto-matched from roster
            elif source == "official":
                badge = "🔵"    # official title
            elif current_portfolio:
                badge = "✏️"    # manually set
            else:
                badge = "⬜"    # unassigned

            col_name, col_turns, col_portfolio, col_confirm = st.columns([3, 1, 5, 1])

            with col_name:
                st.markdown(f"{badge} **{norm}**")
                st.caption(f"{turns} turn{'s' if turns != 1 else ''}")

            with col_turns:
                st.write("")  # spacer

            with col_portfolio:
                # Ensure current value is in options
                if current_portfolio and current_portfolio not in portfolio_options:
                    options = portfolio_options + [current_portfolio]
                else:
                    options = portfolio_options

                selected = st.selectbox(
                    "Portfolio",
                    options=options,
                    index=options.index(current_portfolio) if current_portfolio in options else 0,
                    key=f"sel_{row_idx}",
                    label_visibility="collapsed",
                )

                # Free-text override for anything not in roster
                free_text = st.text_input(
                    "Custom",
                    value="" if selected else current_portfolio,
                    key=f"txt_{row_idx}",
                    placeholder="Type if not in dropdown…",
                    label_visibility="collapsed",
                )

                final_portfolio = free_text.strip() if free_text.strip() else selected

            with col_confirm:
                confirmed = st.checkbox(
                    "✓",
                    value=current_confirmed,
                    key=f"chk_{row_idx}",
                )

            # Resolve jawatan/kementerian
            jawatan = kementerian = senator = constituency = ""
            if final_portfolio:
                for _, rrow in roster_combined.iterrows() if not roster_combined.empty else []:
                    if f"{rrow['Jawatan']} — {rrow['Kementerian']}" == final_portfolio:
                        jawatan      = rrow["Jawatan"]
                        kementerian  = rrow["Kementerian"]
                        senator      = str(rrow.get("Senator", ""))
                        constituency = str(rrow.get("Kawasan Parlimen", ""))
                        break
                if not jawatan and " — " in final_portfolio:
                    parts       = final_portfolio.split(" — ", 1)
                    jawatan     = parts[0].strip()
                    kementerian = parts[1].strip()

            new_source = source if final_portfolio == current_portfolio else "manual"
            updated_assignments[norm] = {
                "portfolio"   : final_portfolio,
                "jawatan"     : jawatan,
                "kementerian" : kementerian,
                "senator"     : senator,
                "constituency": constituency,
                "confirmed"   : confirmed,
                "source"      : new_source,
                "speaker_raw" : raw,
            }

            st.divider()

        # Save / Clear
        col_save, col_clear = st.columns([3, 1])
        with col_save:
            if st.button("💾 Save All Assignments", width="stretch"):
                st.session_state["assignments"] = updated_assignments
                save_assignments(updated_assignments)
                confirmed_n = sum(1 for a in updated_assignments.values() if a.get("confirmed"))
                st.success(f"Saved — {confirmed_n} confirmed assignments.")
        with col_clear:
            if st.button("🗑 Clear", width="stretch"):
                st.session_state["assignments"] = {}
                if os.path.exists(ASSIGNMENTS_PATH):
                    os.remove(ASSIGNMENTS_PATH)
                st.rerun()

        st.caption(
            "🟢 Auto-matched from roster  ·  🔵 Official title  ·  "
            "✏️ Manually set  ·  ⬜ Unassigned"
        )

# ==============================================================================
# TAB 3 — EXPORT
# ==============================================================================
with tab3:
    if "transcript" not in st.session_state:
        st.info("Complete Step ① first.")
    else:
        assignments = st.session_state.get("assignments", {})
        transcript  = st.session_state["transcript"]

        confirmed_count = sum(1 for a in assignments.values() if a.get("confirmed"))
        st.metric("Confirmed assignments", confirmed_count)

        if st.button("🔗 Apply Assignments & Preview", width="stretch"):
            enriched = apply_assignments(
                [dict(r) for r in transcript], assignments
            )
            st.session_state["enriched"] = enriched

        if "enriched" in st.session_state:
            df = pd.DataFrame(st.session_state["enriched"])

            DISPLAY_COLS = [
                "Speaker", "Normalized_Speaker", "Role",
                "Portfolio", "Jawatan", "Kementerian",
                "Is_Minister", "Is_Deputy", "Senator",
                "Constituency", "Speech", "Page", "Document",
            ]
            # Only keep columns that exist
            display_cols = [c for c in DISPLAY_COLS if c in df.columns]

            st.dataframe(
                df[display_cols], width="stretch", height=400,
                column_config={
                    "Speech": st.column_config.TextColumn("Speech", width="large"),
                },
            )

            # Per-document exports
            st.subheader("Download")
            docs = df["Document"].unique().tolist()

            if len(docs) == 1:
                stem = docs[0].rsplit(".", 1)[0]
                st.download_button(
                    f"📥 {stem}.xlsx",
                    data=dataframe_to_xlsx(df[display_cols]),
                    file_name=f"{stem}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                )
            else:
                dl_cols = st.columns(min(len(docs), 3))
                for col, doc_name in zip(dl_cols * 10, docs):
                    stem = doc_name.rsplit(".", 1)[0]
                    sub  = df[df["Document"] == doc_name]
                    with col:
                        st.download_button(
                            f"📥 {stem[:18]}",
                            data=dataframe_to_xlsx(sub[display_cols]),
                            file_name=f"{stem}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{stem}",
                        )

            # Combined JSON
            st.download_button(
                "📥 Download combined JSON",
                data=df[display_cols].to_json(orient="records", indent=2, force_ascii=False),
                file_name="hansard_combined.json",
                mime="application/json",
                width="stretch",
            )